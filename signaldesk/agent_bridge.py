"""多 Agent 长期复核桥接层与 Google Antigravity 官方 ACP 客户端。

设计原则：
1. 仅允许官方公开支持的本地调用协议：
   - Google Antigravity CLI：`agy acp`（Agent Client Protocol，JSON-RPC 2.0 over stdio）
   - OpenAI Codex CLI：`codex exec`（官方非交互结构化输出模式）
   严禁使用任何非官方包装器、伪终端按键注入或未公开私有接口。
2. 零副作用只读安全边界：
   - 所有 Agent 仅接收经 `safe_snapshot()` 白名单过滤的脱敏快照；
   - ACP 握手显式关闭客户端文件系统读写（`readTextFile=False, writeTextFile=False`）与终端（`terminal=False`）能力；
   - 收到任何 `session/request_permission` 工具授权请求时一律按 ACP 规范自动拒绝。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import uuid4

from .models import AgentProviderId, AnalysisResult, AntigravitySettings, Settings
from .security import safe_child_environment, safe_snapshot
from .storage import Store

if TYPE_CHECKING:
    from .codex_bridge import CodexBridge


@runtime_checkable
class OfficialAgentBridge(Protocol):
    """官方本地 Agent CLI 桥接器标准协议契约（所有引擎实现均须满足此结构化接口）。"""

    provider_id: str
    label: str
    protocol: str
    protocol_label: str
    login_hint: str

    def refresh_discovery(self) -> None: ...
    def public_status(self) -> dict: ...
    async def request(
        self,
        stock: dict,
        source: str,
        automatic: bool = False,
        event_id: str | None = None,
        macro: dict | None = None,
        gold: dict | None = None,
    ) -> str | None: ...
    async def run(self) -> None: ...

_STREAM_LINE_LIMIT = 4 * 1024 * 1024
_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


class _AcpRpcError(RuntimeError):
    """封装来自 ACP 服务端返回的 JSON-RPC 错误对象（内部分类用，不直接回显原始堆栈）。"""

    def __init__(self, code: int | None, message: str):
        super().__init__(message)
        self.code = code
        self.rpc_message = message


def find_antigravity() -> str | None:
    """按官方安装约定查找本机 Google Antigravity CLI (`agy`) 可执行文件。"""
    candidates = ["agy.exe", "agy.cmd", "agy"] if os.name == "nt" else ["agy"]
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found
    if os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            official_win = Path(local_app) / "agy" / "bin" / "agy.exe"
            if official_win.is_file():
                return str(official_win)
    else:
        official_unix = Path.home() / ".local" / "bin" / "agy"
        if official_unix.is_file() and os.access(official_unix, os.X_OK):
            return str(official_unix)
    return None


def antigravity_model_defaults() -> dict[str, str]:
    """仅只读解析 `~/.gemini/antigravity-cli/settings.json` 中的非敏感模型偏好。"""
    try:
        cfg_path = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        out: dict[str, str] = {}
        for key in ("model", "modelProvider"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                out[key] = val.strip()
        return out
    except (OSError, ValueError):
        return {}


def antigravity_acp_command(executable: str) -> list[str]:
    """返回官方 Antigravity CLI 启动 ACP stdio 服务的标准参数。"""
    return [executable, "acp"]


def build_analysis_prompt(snapshot_json: str, schema_dict: dict | None = None) -> str:
    """构建统一的中文长期多头计划复核提示词（所有官方 Agent 共用同一套严谨约束）。"""
    instructions = (
        "按证券上市市场复核长期多头计划，只使用下方脱敏JSON。不要调用工具、读取其他文件、联网或执行交易。"
        "用中文先给出继续持有、观察、等待、复核止损或分批止盈等一项意见，再给支持和反对证据。"
        "先检查 instrument.asset_type 与 instrument.is_fund："
        "若是上市公司个股，以市盈率、市净率、盈利收益率和利率环境讨论估值（同时参考名义股债利差 yield_gap_pp 与扣除通胀后的实际利率利差 real_yield_gap_pp；两者均不能单独充当预期回报），缺少盈利增长/现金流依据时说明局限；"
        "若是宽基/行业/商品/杠杆 ETF 或基金，严禁将其当作单一公司讨论财报、净利润或基金主体 PE/PB，应基于追踪基准、近1年高点回撤与价格分位、Yang-Zhang年化波动率、趋势通道与美债利率环境复核，若为杠杆或反向 ETF 须明确指出每日再平衡波动损耗与仅适合波段/对冲的风险。"
        "若快照包含 academic_factors 与 forecast.risk_budget，可结合残差动量（residual_mom_z）、趋势连续度（info_discreteness/id_label）、52周高点比、下行Beta、MAX5过热特征及波动率参考敞口/60日移动保护位辅助论证。"
        "若快照包含 macro_regime，仅将其作为整体市场风险环境底色参考（流动性象限与红灯压力），不可单凭宏观大势替代个股计划或给出指数择时。"
        "若快照包含 extended_hours（夜盘/盘前/盘后及近20日隔夜盘中拉锯 tug_of_war），请结合盘外成交额判断跳空有效性，仅作开盘前预案参考，不可将其混同于已确认常规收盘价或据此改写日线结构结论。"
        "区分用户的计划价、已确认日线、券商估值的取数时间、美债观察日期与模型意见。"
        "给出改变意见的具体条件和复核时点。技术分不能单独触发买卖。"
        "fresh=false、输入缺失、持仓未核对时说明暂不能判断。未分配长期持仓或仅观察时不给持仓退出意见。"
        "source=demo须标明合成。不得编造财报、宏观数据或价格；data_as_of使用日线收盘时点，缺少则填未知。"
    )
    if schema_dict is not None:
        schema_str = json.dumps(schema_dict, ensure_ascii=False)
        instructions += (
            "\n请严格按照以下 JSON Schema 仅输出一个纯 JSON 对象（严禁附加 Markdown 解释文字或多余前后缀）：\n"
            f"{schema_str}"
        )
    return f"{instructions}\n{snapshot_json}"


def extract_structured_result(raw_text: str) -> AnalysisResult:
    """从 Agent 文本输出中严格解析并校验 `AnalysisResult`（兼容纯 JSON 与代码块包裹）。"""
    cleaned = (raw_text or "").strip()
    if not cleaned:
        raise ValueError("Antigravity CLI 未返回任何分析文本")

    try:
        return AnalysisResult.model_validate_json(cleaned)
    except ValueError:
        pass

    for match in _FENCE_RE.finditer(cleaned):
        candidate = match.group(1).strip()
        try:
            return AnalysisResult.model_validate_json(candidate)
        except ValueError:
            continue

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(cleaned):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(cleaned[idx:])
        except ValueError:
            continue
        if isinstance(obj, dict):
            try:
                return AnalysisResult.model_validate(obj)
            except ValueError:
                continue

    raise ValueError("Antigravity CLI 未返回符合结构要求的分析结果")


def _select_reject_outcome(options: object) -> dict:
    """在 ACP `session/request_permission` 选项中挑选拒绝项，确保零副作用。"""
    if isinstance(options, list):
        for opt in options:
            if not isinstance(opt, dict):
                continue
            opt_id = opt.get("optionId")
            kind = str(opt.get("kind") or "").lower()
            if isinstance(opt_id, str) and opt_id and kind in {"reject_once", "reject_always"}:
                return {"outcome": {"outcome": "selected", "optionId": opt_id}}
        for opt in options:
            if not isinstance(opt, dict):
                continue
            opt_id = opt.get("optionId")
            if isinstance(opt_id, str) and any(tok in opt_id.lower() for tok in ("reject", "deny", "cancel")):
                return {"outcome": {"outcome": "selected", "optionId": opt_id}}
    return {"outcome": {"outcome": "cancelled"}}


def _extract_chunk_text(update: dict) -> str:
    """从 ACP `session/update` 的 `agent_message_chunk` 载荷中安全提取文本分片。"""
    if update.get("sessionUpdate") != "agent_message_chunk":
        return ""
    content = update.get("content")
    if isinstance(content, dict):
        ctype = content.get("type")
        text = content.get("text")
        if ctype in (None, "text") and isinstance(text, str):
            return text
    elif isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in (None, "text") and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    if isinstance(update.get("text"), str):
        return update["text"]
    return ""


class AcpStdioClient:
    """标准 Agent Client Protocol (ACP v1) JSON-RPC 2.0 over stdio 轻量客户端。"""

    def __init__(self, proc: asyncio.subprocess.Process):
        assert proc.stdin is not None and proc.stdout is not None
        self.proc = proc
        self.stdin = proc.stdin
        self.stdout = proc.stdout
        self._next_id = 0
        self.chunks: list[str] = []
        self.negotiated_model: str | None = None

    async def _write_json(self, payload: dict) -> None:
        line = json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n"
        self.stdin.write(line.encode("utf-8"))
        await self.stdin.drain()

    async def request(self, method: str, params: dict) -> dict:
        self._next_id += 1
        req_id = self._next_id
        await self._write_json(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params,
            }
        )
        while True:
            raw_line = await self.stdout.readline()
            if not raw_line:
                raise EOFError("ACP 通道意外关闭")
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue

            # 1. Agent -> Client 单向通知 (如 session/update)
            if "method" in msg and "id" not in msg:
                if msg.get("method") == "session/update":
                    params_obj = msg.get("params")
                    if isinstance(params_obj, dict):
                        upd = params_obj.get("update")
                        if isinstance(upd, dict):
                            piece = _extract_chunk_text(upd)
                            if piece:
                                self.chunks.append(piece)
                continue

            # 2. Agent -> Client 反向请求 (如 session/request_permission, fs/*, terminal/*)
            if "method" in msg and "id" in msg:
                incoming_id = msg["id"]
                incoming_method = msg.get("method")
                if incoming_method == "session/request_permission":
                    params_obj = msg.get("params") if isinstance(msg.get("params"), dict) else {}
                    decision = _select_reject_outcome(params_obj.get("options"))
                    await self._write_json({"jsonrpc": "2.0", "id": incoming_id, "result": decision})
                else:
                    await self._write_json(
                        {
                            "jsonrpc": "2.0",
                            "id": incoming_id,
                            "error": {
                                "code": -32601,
                                "message": "Capability disabled by SignalDesk read-only ACP client",
                            },
                        }
                    )
                continue

            # 3. 请求对应的 Response
            if msg.get("id") == req_id:
                if "error" in msg and msg["error"] is not None:
                    err = msg["error"]
                    if isinstance(err, dict):
                        raise _AcpRpcError(err.get("code"), str(err.get("message") or "ACP RPC error"))
                    raise _AcpRpcError(None, str(err))
                res = msg.get("result")
                return res if isinstance(res, dict) else {}

    async def run_single_turn(self, cwd: Path, prompt: str) -> str:
        """完整执行官方 ACP v1 握手 (`initialize` -> `session/new` -> `session/prompt`) 并返回聚合响应。"""
        await self.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientInfo": {"name": "SignalDesk", "version": "0.1.0"},
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                },
            },
        )
        sess = await self.request(
            "session/new",
            {
                "cwd": str(cwd),
                "mcpServers": [],
            },
        )
        session_id = sess.get("sessionId")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("Antigravity ACP 未返回有效会话 ID")
        models_meta = sess.get("models")
        if isinstance(models_meta, dict) and isinstance(models_meta.get("currentModelId"), str):
            self.negotiated_model = models_meta["currentModelId"]

        prompt_res = await self.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": prompt}],
            },
        )
        text = "".join(self.chunks).strip()
        if not text and isinstance(prompt_res.get("text"), str):
            text = prompt_res["text"].strip()
        return text


def _classify_antigravity_failure(detail_text: str, returncode: int | None = None) -> ValueError:
    """将 ACP / CLI 错误映射为不含本机敏感路径的中文可操作提示。"""
    low = (detail_text or "").lower()
    if any(w in low for w in ("rate limit", "quota", "429", "resource_exhausted", "usage limit")):
        return ValueError("Antigravity CLI 额度或调用频率受限，请稍后重试")
    if any(w in low for w in ("login", "unauthenticated", "unauthorized", "auth", "401", "credentials", "sign in")):
        return ValueError("Antigravity CLI 尚未完成登录，请在本机终端执行 `agy acp --login` 后重试")
    if returncode is not None:
        return ValueError(f"Antigravity ACP 进程异常退出（{returncode}），请检查 `agy acp --help` 与登录状态")
    return ValueError("Antigravity ACP 协议通信失败，请检查本机 CLI 版本与登录状态")


class AntigravityAcpBridge:
    """通过官方 `agy acp`（Agent Client Protocol）驱动的本地长期复核桥接器。"""

    provider_id: AgentProviderId = "antigravity"
    label: str = "Antigravity CLI"
    protocol: str = "acp"
    protocol_label: str = "Google Antigravity ACP (agy acp)"
    login_hint: str = "agy acp --login"

    def __init__(self, store: Store, settings: AntigravitySettings):
        self.store = store
        self.settings = settings
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=30)
        self.executable = find_antigravity()
        self.defaults = antigravity_model_defaults()
        self.last_model: str | None = None
        self.status = "ready" if self.executable else "unavailable"
        self.detail = (
            "手动触发模式 · 官方 ACP 协议（agy acp）已就绪"
            if self.executable
            else "未检测到 Antigravity CLI（安装后执行 agy acp --login）"
        )
        self.process: asyncio.subprocess.Process | None = None

    def refresh_discovery(self) -> None:
        """按需探测可执行文件与非敏感模型偏好，不覆盖已配置或测试注入的命令路径。"""
        if not self.executable:
            self.executable = find_antigravity()
            if self.executable and self.status == "unavailable":
                self.status = "ready"
                self.detail = "手动触发模式 · 官方 ACP 协议（agy acp）已就绪"
        self.defaults = antigravity_model_defaults()

    def public_status(self) -> dict:
        self.refresh_discovery()
        model_label = (
            self.last_model
            or self.defaults.get("model")
            or ("Antigravity 默认模型" if self.executable else "未检测到 agy CLI")
        )
        return {
            "id": self.provider_id,
            "label": self.label,
            "protocol": self.protocol,
            "protocol_label": self.protocol_label,
            "official": True,
            "login_hint": self.login_hint,
            "status": self.status if self.settings.enabled else "disabled",
            "detail": self.detail if self.settings.enabled else "已在设置中停用 Antigravity 复核",
            "configured": bool(self.executable),
            "model": model_label,
            "automatic": False,
            "manual_only": True,
            "enabled": self.settings.enabled,
            "queue_size": self.queue.qsize(),
        }

    async def request(
        self,
        stock: dict,
        source: str,
        automatic: bool = False,
        event_id: str | None = None,
        macro: dict | None = None,
        gold: dict | None = None,
    ) -> str | None:
        if automatic:
            # 严格手动触发：ACP 通道绝不在后台事件循环中自动发起请求
            return None
        if not self.settings.enabled:
            raise ValueError("Antigravity CLI 复核未启用，请在「设置 -> Agent 复核」中开启")
        self.refresh_discovery()
        if not self.executable:
            raise ValueError("未检测到 Antigravity CLI（agy），请按官方文档安装后执行 `agy acp --login`")
        if self.queue.full():
            raise ValueError("Antigravity 分析队列已满，行情监控仍继续运行")

        job = {
            "id": str(uuid4()),
            "symbol": stock["symbol"],
            "agent": self.provider_id,
            "agent_label": self.label,
            "protocol": self.protocol,
            "created": time.time(),
            "status": "queued",
            "source": source,
            "scope": "long_value",
            "event_id": event_id,
            "automatic": False,
            "result": None,
            "error": None,
            "snapshot": safe_snapshot(stock, source, macro, gold),
        }
        self.store.analysis(job)
        self.queue.put_nowait(job)
        return job["id"]

    async def run(self) -> None:
        while True:
            job = await self.queue.get()
            self.status, self.detail = "running", f"正在通过 ACP 复核 {job['symbol']}"
            job["status"] = "running"
            self.store.analysis(job)
            try:
                result = await self._analyze(job)
                job.update(status="completed", result=result.model_dump(), snapshot=None)
                if self.last_model:
                    job["model"] = self.last_model
                self.status, self.detail = "ready", "最近一次 ACP 复核已完成"
            except asyncio.CancelledError:
                job.update(status="failed", error="程序退出，分析已取消", snapshot=None)
                self.store.analysis(job)
                raise
            except Exception as error:
                message = (
                    str(error)
                    if isinstance(error, (TimeoutError, ValueError))
                    else f"ACP 分析失败（{type(error).__name__}）"
                )
                job.update(status="failed", error=message[:250], snapshot=None)
                self.status, self.detail = "error", message[:250]
            finally:
                self.store.analysis(job)
                self.queue.task_done()

    async def _terminate_proc(self, proc: asyncio.subprocess.Process) -> None:
        if proc.stdin is not None and not proc.stdin.is_closing():
            try:
                proc.stdin.close()
            except Exception:
                pass
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except Exception:
            pass

    async def _analyze(self, job: dict) -> AnalysisResult:
        assert self.executable is not None
        directory = self.store.directory / "agent-exports" / f"antigravity-{job['id']}"
        directory.mkdir(parents=True, exist_ok=True)
        schema = AnalysisResult.model_json_schema()
        (directory / "schema.json").write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
        snapshot_str = json.dumps(job["snapshot"], ensure_ascii=False, allow_nan=False)
        (directory / "snapshot.json").write_text(snapshot_str, encoding="utf-8")
        prompt = build_analysis_prompt(snapshot_str, schema_dict=schema)

        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.process = await asyncio.create_subprocess_exec(
            *antigravity_acp_command(self.executable),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(directory),
            env=safe_child_environment(),
            limit=_STREAM_LINE_LIMIT,
            creationflags=flags,
        )
        proc = self.process
        client = AcpStdioClient(proc)
        raw_output = ""
        try:
            raw_output = await asyncio.wait_for(
                client.run_single_turn(directory, prompt),
                timeout=self.settings.timeout_seconds,
            )
            if client.negotiated_model:
                self.last_model = client.negotiated_model
        except asyncio.TimeoutError:
            await self._terminate_proc(proc)
            raise TimeoutError("Antigravity ACP 分析超时，行情监控与通知继续运行") from None
        except asyncio.CancelledError:
            await self._terminate_proc(proc)
            raise
        except _AcpRpcError as rpc_err:
            await self._terminate_proc(proc)
            raise _classify_antigravity_failure(rpc_err.rpc_message, proc.returncode) from None
        except EOFError:
            stderr_bytes = b""
            if proc.stderr is not None:
                try:
                    stderr_bytes = await asyncio.wait_for(proc.stderr.read(4096), timeout=1.0)
                except Exception:
                    stderr_bytes = b""
            await self._terminate_proc(proc)
            raise _classify_antigravity_failure(
                stderr_bytes.decode("utf-8", errors="replace"),
                proc.returncode,
            ) from None
        finally:
            await self._terminate_proc(proc)
            self.process = None

        result = extract_structured_result(raw_output)
        daily = job["snapshot"].get("technical", {}).get("day:regular")
        if daily:
            result.data_as_of = daily.get("as_of") or "未知"
        return result


class AgentHub:
    """基于 `OfficialAgentBridge` 协议注册表统一协调多个官方本地 Agent CLI。"""

    def __init__(
        self,
        store: Store,
        settings: Settings,
        codex: CodexBridge,
        antigravity: AntigravityAcpBridge,
    ):
        self.store = store
        self.settings = settings
        self.codex = codex
        self.antigravity = antigravity
        self.providers: dict[AgentProviderId, OfficialAgentBridge] = {
            "antigravity": antigravity,
            "codex": codex,
        }

    def update_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.codex.settings = settings.codex
        self.antigravity.settings = settings.antigravity

    def get_bridge(self, agent: AgentProviderId | None = None) -> OfficialAgentBridge:
        chosen: AgentProviderId = agent or self.settings.default_agent
        bridge = self.providers.get(chosen)
        if bridge is None:
            raise ValueError(f"不支持的 Agent 类型：{chosen}")
        return bridge

    def public_status(self) -> dict:
        return {
            "default_agent": self.settings.default_agent,
            "manual_only": True,
            "official_only": True,
            "providers": {
                agent_id: bridge.public_status()
                for agent_id, bridge in self.providers.items()
            },
        }

    async def request(
        self,
        stock: dict,
        source: str,
        agent: AgentProviderId | None = None,
        automatic: bool = False,
        event_id: str | None = None,
        macro: dict | None = None,
        gold: dict | None = None,
    ) -> tuple[str | None, AgentProviderId]:
        chosen: AgentProviderId = agent or self.settings.default_agent
        bridge = self.get_bridge(chosen)
        job_id = await bridge.request(
            stock,
            source,
            automatic=automatic,
            event_id=event_id,
            macro=macro,
            gold=gold,
        )
        return job_id, chosen
