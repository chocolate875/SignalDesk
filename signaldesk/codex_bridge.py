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
        f'permissions.{profile}.filesystem.":minimal"': "read",
        f"permissions.{profile}.filesystem.{json.dumps(str(directory))}": "read",
        f"permissions.{profile}.network.enabled": False,
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
        args += ["-c", f"{key}={json.dumps(value)}"]
    return args + ["-"]


class CodexBridge:
    def __init__(self, store: Store, settings: CodexSettings):
        self.store, self.settings = store, settings
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=30)
        self.executable = find_codex()
        self.defaults = model_defaults()
        self.status = "ready" if self.executable else "unavailable"
        self.detail = "使用现有Codex登录；等待分析请求" if self.executable else "未发现Codex CLI"
        self.process = None

    def public_status(self):
        today = datetime.now(SH).date().isoformat()
        return {
            "status": self.status,
            "detail": self.detail,
            "configured": bool(self.executable),
            "model": self.defaults.get("model", "Codex默认模型"),
            "automatic": self.settings.automatic,
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
            "你是SignalDesk的技术信号分析师。只基于下面已脱敏、带时点的JSON分析。"
            "不要调用工具、读取其他文件、联网、修改规则或执行交易。所有决策建议由你形成，"
            "评分只描述技术结构而非上涨概率。用户偏保守，仅美股多头，长期仓与2至20交易日短线仓分别判断。"
            "source=demo表示完全合成的数据，不得当成真实市场。缺失、过期或风险信息应优先指出。"
            "不得编造新闻、财报、价格、胜率。解释支持与反对证据、等待条件；用中文回答，符合给定JSON Schema。"
            "data_as_of取technical中最近有效数据时间。\n" + snapshot
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
