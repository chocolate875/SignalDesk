from __future__ import annotations

import asyncio
import json
import sys
import textwrap

import pytest
from fastapi.testclient import TestClient

from signaldesk.agent_bridge import (
    AntigravityAcpBridge,
    OfficialAgentBridge,
    antigravity_acp_command,
    extract_structured_result,
)
from signaldesk.app import create_app
from signaldesk.models import AntigravitySettings
from signaldesk.storage import Store


def test_extract_structured_result_handles_plain_and_fenced_json():
    payload = {
        "conclusion": "趋势稳健，维持观察",
        "action": "observe",
        "evidence": ["残差动量偏强", "FIP连续慢牛"],
        "risks": ["估值分位偏高"],
        "confirmation_conditions": ["回踩20日趋势中枢企稳"],
        "data_as_of": "2026-11-23T21:00:00+00:00",
    }
    direct = extract_structured_result(json.dumps(payload, ensure_ascii=False))
    assert direct.action == "observe"

    fenced = f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
    parsed_fenced = extract_structured_result(fenced)
    assert parsed_fenced.conclusion == "趋势稳健，维持观察"


@pytest.mark.asyncio
async def test_antigravity_acp_real_stdio_handshake_permission_denial_and_env_isolation(
    tmp_path, monkeypatch
):
    """通过真实子进程 stdio 验证官方 ACP 协议完整生命周期、只读权限拒绝与敏感环境变量隔离。"""
    mock_acp_script = tmp_path / "mock_agy_acp.py"
    audit_file = tmp_path / "acp_audit.json"
    mock_acp_script.write_text(
        textwrap.dedent(
            """
            import json
            import os
            import sys

            sys.stdin.reconfigure(encoding="utf-8")
            sys.stdout.reconfigure(encoding="utf-8")

            # 确保启动参数是官方 `acp` 子命令
            assert sys.argv[1:] == ["acp"], f"unexpected args: {sys.argv[1:]}"
            audit = {
                "has_longport_secret": "LONGPORT_ACCESS_TOKEN" in os.environ,
                "has_qq_secret": "QQ_APP_SECRET" in os.environ,
                "has_gemini_key": os.environ.get("GEMINI_API_KEY") == "PUBLIC_TEST_GEMINI_KEY",
                "requests": [],
                "permission_reply": None,
                "fs_reply": None,
            }

            def send(obj):
                sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\\n")
                sys.stdout.flush()

            while True:
                raw = sys.stdin.readline()
                if not raw:
                    break
                msg = json.loads(raw)
                method = msg.get("method")
                req_id = msg.get("id")
                audit["requests"].append({"method": method, "params": msg.get("params")})

                if method == "initialize":
                    send({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": 1,
                            "agentInfo": {"name": "agy", "version": "1.6.0"},
                            "agentCapabilities": {},
                        },
                    })
                elif method == "session/new":
                    send({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "sessionId": "sess-acp-001",
                            "models": {"currentModelId": "gemini-acp-pro"},
                        },
                    })
                elif method == "session/prompt":
                    sid = msg["params"]["sessionId"]
                    # 1. 发送内部思考分片（不应混入最终 JSON 输出）
                    send({
                        "jsonrpc": "2.0",
                        "method": "session/update",
                        "params": {
                            "sessionId": sid,
                            "update": {
                                "sessionUpdate": "agent_thought_chunk",
                                "content": {"type": "text", "text": "NOT_JSON_THOUGHT"},
                            },
                        },
                    })
                    # 2. 尝试请求副作用工具权限，客户端必须自动选择 reject_once
                    send({
                        "jsonrpc": "2.0",
                        "id": 9001,
                        "method": "session/request_permission",
                        "params": {
                            "sessionId": sid,
                            "toolCall": {"toolCallId": "tc-1", "title": "Run shell"},
                            "options": [
                                {"optionId": "allow_once", "kind": "allow_once", "name": "Allow"},
                                {"optionId": "reject_once", "kind": "reject_once", "name": "Reject"},
                            ],
                        },
                    })
                    perm_resp = json.loads(sys.stdin.readline())
                    audit["permission_reply"] = perm_resp

                    # 3. 尝试调用已被禁用的客户端文件写入能力，客户端必须返回 JSON-RPC error
                    send({
                        "jsonrpc": "2.0",
                        "id": 9002,
                        "method": "fs/write_text_file",
                        "params": {"path": "hacked.txt", "content": "bad"},
                    })
                    fs_resp = json.loads(sys.stdin.readline())
                    audit["fs_reply"] = fs_resp

                    # 4. 流式分片发送结构化复核 JSON
                    ans = {
                        "conclusion": "合成快照复核完成，建议继续观察关键支撑位",
                        "action": "wait",
                        "evidence": ["ACP流式分片1", "ACP流式分片2"],
                        "risks": ["合成演示环境"],
                        "confirmation_conditions": ["放量站稳前高突破位"],
                        "data_as_of": "2026-11-20T21:00:00+00:00",
                    }
                    raw_json = "```json\\n" + json.dumps(ans, ensure_ascii=False) + "\\n```"
                    mid = len(raw_json) // 2
                    for part in (raw_json[:mid], raw_json[mid:]):
                        send({
                            "jsonrpc": "2.0",
                            "method": "session/update",
                            "params": {
                                "sessionId": sid,
                                "update": {
                                    "sessionUpdate": "agent_message_chunk",
                                    "content": {"type": "text", "text": part},
                                },
                            },
                        })
                    path = __import__("pathlib").Path(r"__AUDIT_PATH__")
                    path.write_text(json.dumps(audit, ensure_ascii=False), encoding="utf-8")
                    send({"jsonrpc": "2.0", "id": req_id, "result": {"stopReason": "end_turn"}})
                    break
            """
        ).replace("__AUDIT_PATH__", str(audit_file)),
        encoding="utf-8",
    )

    store = Store(tmp_path / "store")
    bridge = AntigravityAcpBridge(store, AntigravitySettings(timeout_seconds=30))
    bridge.executable = sys.executable

    monkeypatch.setattr(
        "signaldesk.agent_bridge.antigravity_acp_command",
        lambda exe: [exe, str(mock_acp_script), "acp"],
    )
    monkeypatch.setenv("LONGPORT_ACCESS_TOKEN", "SECRET_BROKER_TOKEN")
    monkeypatch.setenv("QQ_APP_SECRET", "SECRET_QQ_TOKEN")
    monkeypatch.setenv("GEMINI_API_KEY", "PUBLIC_TEST_GEMINI_KEY")

    assert antigravity_acp_command("agy") == ["agy", "acp"]

    snapshot = {
        "source": "demo",
        "symbol": "NVDA.US",
        "technical": {"day:regular": {"as_of": "2026-11-23T21:00:00+00:00"}},
    }
    res = await bridge._analyze({"id": "job-acp-1", "snapshot": snapshot})
    assert res.action == "wait"
    assert res.data_as_of == "2026-11-23T21:00:00+00:00"
    assert bridge.last_model == "gemini-acp-pro"
    assert bridge.process is None

    audit = json.loads(audit_file.read_text(encoding="utf-8"))
    assert audit["has_longport_secret"] is False
    assert audit["has_qq_secret"] is False
    assert audit["has_gemini_key"] is True
    methods = [r["method"] for r in audit["requests"]]
    assert methods == ["initialize", "session/new", "session/prompt"]
    init_caps = audit["requests"][0]["params"]["clientCapabilities"]
    assert init_caps == {
        "fs": {"readTextFile": False, "writeTextFile": False},
        "terminal": False,
    }
    assert audit["permission_reply"]["result"] == {
        "outcome": {"outcome": "selected", "optionId": "reject_once"}
    }
    assert audit["fs_reply"]["error"]["code"] == -32601
    store.close()


@pytest.mark.asyncio
async def test_antigravity_acp_timeout_and_auth_error_handling(tmp_path, monkeypatch):
    store = Store(tmp_path / "store_err")
    bridge = AntigravityAcpBridge(store, AntigravitySettings(timeout_seconds=15))
    bridge.settings.timeout_seconds = 0.05
    bridge.executable = "synthetic-agy"
    killed: list[bool] = []

    class SlowStdin:
        def write(self, data: bytes):
            pass

        async def drain(self):
            pass

        def is_closing(self):
            return False

        def close(self):
            pass

    class SlowStdout:
        async def readline(self):
            await asyncio.sleep(30)
            return b""

    class SlowProc:
        stdin = SlowStdin()
        stdout = SlowStdout()
        stderr = None
        returncode = None

        def kill(self):
            killed.append(True)
            self.returncode = -9

        async def wait(self):
            return -9

    async def spawn_slow(*args, **kwargs):
        return SlowProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_slow)
    with pytest.raises(TimeoutError, match="Antigravity ACP 分析超时"):
        await bridge._analyze({"id": "slow-1", "snapshot": {"source": "demo"}})
    assert killed and bridge.process is None

    # 验证未登录 RPC 错误映射为官方登录指引且不回显敏感路径
    bridge.settings.timeout_seconds = 15

    class UnauthStdout:
        def __init__(self):
            self.sent = False

        async def readline(self):
            if not self.sent:
                self.sent = True
                return (
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "error": {
                                "code": -32001,
                                "message": "Unauthenticated at C:\\Users\\Private\\secret_token",
                            },
                        }
                    ).encode("utf-8")
                    + b"\n"
                )
            return b""

    class UnauthProc(SlowProc):
        def __init__(self):
            self.stdout = UnauthStdout()

    async def spawn_unauth(*args, **kwargs):
        return UnauthProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_unauth)
    with pytest.raises(ValueError) as exc_info:
        await bridge._analyze({"id": "unauth-1", "snapshot": {"source": "demo"}})
    msg = str(exc_info.value)
    assert "agy acp --login" in msg
    assert "C:\\Users\\Private" not in msg
    store.close()


def test_multi_agent_endpoints_and_unofficial_agent_rejection(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNALDESK_DATA_DIR", str(tmp_path))
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        client.get("/")
        monitor = app.state.monitor
        assert isinstance(monitor.antigravity, OfficialAgentBridge)
        assert isinstance(monitor.codex, OfficialAgentBridge)
        monitor.antigravity.executable = "synthetic-agy"
        monitor.codex.executable = "synthetic-codex"

        boot = client.get("/api/bootstrap").json()
        agents_ch = boot["channels"]["agents"]
        assert agents_ch["official_only"] is True
        assert agents_ch["manual_only"] is True
        assert agents_ch["providers"]["antigravity"]["protocol"] == "acp"
        assert agents_ch["providers"]["codex"]["protocol"] == "codex-exec"

        # 拒绝任何非官方 Agent 标识
        bad_body = client.post("/api/analysis/NVDA.US", json={"agent": "unofficial_wrapper"})
        assert bad_body.status_code == 422
        bad_query = client.post("/api/analysis/NVDA.US?agent=unofficial_wrapper")
        assert bad_query.status_code == 422

        # 正常分发至官方 Antigravity ACP 队列与官方 Codex 队列
        # 先暂停消费以便断言入队归属与元数据
        r_agy = client.post("/api/analysis/NVDA.US", json={"agent": "antigravity"})
        assert r_agy.status_code == 200
        assert r_agy.json()["agent"] == "antigravity"

        r_cdx = client.post("/api/analysis/NVDA.US", json={"agent": "codex"})
        assert r_cdx.status_code == 200
        assert r_cdx.json()["agent"] == "codex"

        recorded = {a["agent"]: a["protocol"] for a in monitor.store.analyses(source="demo")}
        assert recorded["antigravity"] == "acp"
        assert recorded["codex"] == "codex-exec"

        # 验证设置页切换默认 Agent 为 antigravity
        cur_settings = client.get("/api/settings").json()["settings"]
        cur_settings["default_agent"] = "antigravity"
        cur_settings["antigravity"]["timeout_seconds"] = 300
        saved = client.put("/api/settings", json=cur_settings)
        assert saved.status_code == 200
        updated = client.get("/api/settings").json()["settings"]
        assert updated["default_agent"] == "antigravity"
        assert updated["antigravity"]["timeout_seconds"] == 300
