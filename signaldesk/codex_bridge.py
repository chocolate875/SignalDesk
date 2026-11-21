from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
import tomllib
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .calendar import SH
from .models import AnalysisResult, CodexSettings
from .security import safe_child_environment, safe_snapshot
from .storage import Store


def find_codex() -> str | None:
    path = shutil.which("codex.exe" if os.name == "nt" else "codex")
    return path


def model_defaults() -> dict:
    """Read only non-secret model preferences; never load the user's tools/hooks into a job."""
    try:
        data = tomllib.loads((Path.home() / ".codex/config.toml").read_text(encoding="utf-8"))
        return {
            key: data[key] for key in ["model", "model_reasoning_effort"] if isinstance(data.get(key), str)
        }
    except (OSError, ValueError):
        return {}


def command(executable: str, directory: Path, defaults: dict) -> list[str]:
    profile = "signaldesk-analysis"
    # No --sandbox preset: legacy read-only would silently override exact filesystem roots.
    config = {
        "default_permissions": profile,
        "permissions": {
            profile: {
                "filesystem": {":minimal": "read", str(directory): "read"},
                "network": {"enabled": False},
            }
        },
        "project_doc_max_bytes": 0,
        "web_search": "disabled",
        "windows.sandbox": "elevated",
        **defaults,
    }
    args = [
        executable,
        "exec",
        "--ignore-user-config",
        "--ephemeral",
        "--skip-git-repo-check",
        "--color",
        "never",
        "--json",
        "-C",
        str(directory),
        "--output-schema",
        str(directory / "schema.json"),
        "-o",
        str(directory / "result.json"),
    ]
    for feature in [
        "apps",
        "plugins",
        "shell_tool",
        "view_image",
        "multi_agent",
        "memories",
        "hooks",
        "browser_use",
        "computer_use",
        "image_generation",
        "daemon_auto_start",
        "skill_search",
    ]:
        args += ["--disable", feature]
    args += ["--enable", "skip_host_skill_discovery"]
    for key, value in config.items():
        args += ["-c", f"{key}={inline_toml(value)}"]
    return args + ["-"]


def inline_toml(value) -> str:
    # CLI -c splits dotted keys literally; quoted path segments are NOT TOML-decoded there.
    # Pass the complete permissions table as one inline TOML value instead.
    if isinstance(value, dict):
        return (
            "{" + ", ".join(f"{json.dumps(key)} = {inline_toml(item)}" for key, item in value.items()) + "}"
        )
    return json.dumps(value)


class CodexBridge:
    def __init__(self, store: Store, settings: CodexSettings):
        self.store, self.settings = store, settings
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=30)
        self.executable = find_codex()
        self.defaults = model_defaults()
        self.status = "ready" if self.executable else "unavailable"
        self.detail = (
            "手动触发模式 · 点击「生成 Codex 总结」后分析" if self.executable else "未发现Codex CLI"
        )
        self.process = None

    def public_status(self):
        today = datetime.now(SH).date().isoformat()
        return {
            "status": self.status,
            "detail": self.detail,
            "configured": bool(self.executable),
            "model": self.defaults.get("model", "Codex默认模型"),
            "automatic": False,
            "manual_only": True,
            "enabled": self.settings.enabled,
            "daily_used": self.store.get(f"codex-budget:{today}", 0),
            "daily_limit": self.settings.daily_limit,
            "queue_size": self.queue.qsize(),
        }

    async def request(self, stock: dict, source: str, automatic: bool = False, event_id: str | None = None):
        if not self.settings.enabled:
            raise ValueError("Codex分析未启用")
        if not self.executable:
            raise ValueError("未发现Codex CLI，请在本机安装并登录")
        now = time.time()
        if automatic:
            if not self.settings.automatic or source != "live":
                return None
            today = datetime.now(SH).date().isoformat()
            used = self.store.get(f"codex-budget:{today}", 0)
            last = self.store.get(f"codex-last:{source}:{stock['symbol']}", 0)
            if used >= self.settings.daily_limit or now - last < self.settings.cooldown_minutes * 60:
                return None
        if self.queue.full():
            raise ValueError("Codex分析队列已满，行情监控仍继续")
        job = {
            "id": str(uuid4()),
            "symbol": stock["symbol"],
            "created": now,
            "status": "queued",
            "source": source,
            "scope": "long_value",
            "event_id": event_id,
            "automatic": automatic,
            "result": None,
            "error": None,
            "snapshot": safe_snapshot(stock, source),
        }
        if automatic:
            self.store.set(f"codex-budget:{today}", used + 1)
            self.store.set(f"codex-last:{source}:{stock['symbol']}", now)
        self.store.analysis(job)
        self.queue.put_nowait(job)
        return job["id"]

    async def run(self):
        while True:
            job = await self.queue.get()
            self.status, self.detail = "running", f"正在分析 {job['symbol']}"
            job["status"] = "running"
            self.store.analysis(job)
            try:
                result = await self._analyze(job)
                job.update(status="completed", result=result.model_dump(), snapshot=None)
                self.status, self.detail = "ready", "最近一次分析已完成"
            except asyncio.CancelledError:
                job.update(status="failed", error="程序退出，分析已取消", snapshot=None)
                self.store.analysis(job)
                raise
            except Exception as error:
                # CLI stderr can contain local paths and request context: never echo it into logs/UI.
                message = (
                    str(error)
                    if isinstance(error, (TimeoutError, ValueError))
                    else f"分析失败（{type(error).__name__}）"
                )
                job.update(status="failed", error=message[:250], snapshot=None)
                self.status, self.detail = "error", message[:250]
            finally:
                self.store.analysis(job)
                self.queue.task_done()

    async def _analyze(self, job: dict) -> AnalysisResult:
        directory = self.store.directory / "codex-exports" / job["id"]
        directory.mkdir(parents=True)
        (directory / "schema.json").write_text(
            json.dumps(AnalysisResult.model_json_schema()), encoding="utf-8"
        )
        snapshot = json.dumps(job["snapshot"], ensure_ascii=False, allow_nan=False)
        (directory / "snapshot.json").write_text(snapshot, encoding="utf-8")
        prompt = (
            "复核美股长期多头计划，只使用下方脱敏JSON。不要调用工具、读取其他文件、联网或执行交易。"
            "用中文先给出继续持有、观察、等待、复核止损或分批止盈等一项意见，再给支持和反对证据。"
            "区分用户的计划价、已确认日线、券商估值的取数时间、美债观察日期与模型意见。"
            "以市盈率、市净率、盈利收益率和利率环境讨论估值。盈利收益率与国债收益率之差不能充当预期回报或风险溢价。"
            "给出改变意见的具体条件和复核时点。技术分不能单独触发买卖。缺少盈利增长、现金流等依据时说明局限。"
            "fresh=false、输入缺失、持仓未核对时说明暂不能判断。未分配长期持仓或仅观察时不给持仓退出意见。"
            "source=demo须标明合成。不得编造财报、宏观数据或价格；data_as_of使用日线收盘时点，缺少则填未知。\n" + snapshot
        )
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.process = await asyncio.create_subprocess_exec(
            *command(self.executable, directory, self.defaults),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=safe_child_environment(),
            creationflags=flags,
        )
        proc = self.process
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(prompt.encode("utf-8")), self.settings.timeout_seconds
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            proc.kill()
            await proc.wait()
            if asyncio.current_task().cancelling():
                raise
            raise TimeoutError("Codex分析超时，行情和通知继续运行") from None
        finally:
            self.process = None
        if proc.returncode:
            text = stderr.decode("utf-8", errors="replace").lower()
            if any(word in text for word in ["rate limit", "usage limit", "quota"]):
                raise ValueError("Codex额度或调用频率受限，请稍后重试")
            if any(word in text for word in ["login", "unauthorized", "authentication", "401"]):
                raise ValueError("Codex登录不可用，请在本机Codex中重新登录")
            if any(word in text for word in ["sandbox", "permission", "access is denied", "os error 5"]):
                raise ValueError("Codex隔离环境未就绪，请在Codex完成Windows沙箱设置后重试")
            raise ValueError(f"Codex进程退出（{proc.returncode}），请检查CLI兼容性与网络；未降低隔离权限")
        try:
            result = AnalysisResult.model_validate_json(
                (directory / "result.json").read_text(encoding="utf-8")
            )
        except (ValueError, OSError):
            raise ValueError("Codex未返回有效的结构化分析结果") from None
        daily = job["snapshot"].get("technical", {}).get("day:regular")
        if daily:
            result.data_as_of = daily.get("as_of") or "未知"
        usage = []
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
                if item.get("type") == "turn.completed" and item.get("usage"):
                    usage.append(item["usage"])
            except ValueError:
                pass
        if usage:
            self.store.set(f"codex-usage:{job['id']}", usage[-1])
        return result
