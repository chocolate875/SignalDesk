import { useEffect, useState } from "react";
import {
  X,
  ShieldCheck,
  Send,
  Settings2,
  KeyRound,
  Bot,
  SlidersHorizontal,
  CheckCircle2,
  ExternalLink,
  LoaderCircle,
} from "lucide-react";
import { api } from "./types";

type BrokerAuth = {
  method: "oauth" | "apikey" | null;
  pending: boolean;
  message: string;
};

export default function SettingsPanel({
  onClose,
  notify,
  first,
}: {
  onClose: () => void;
  notify: (s: string) => void;
  first: boolean;
}) {
  const [data, setData] = useState<any>(null);
  const [tab, setTab] = useState("general");
  const [busy, setBusy] = useState(false);
  const [qqSecret, setQQSecret] = useState("");
  const [brokerPlatform, setBrokerPlatform] = useState<string | null>(null);
  const [method, setMethod] = useState("oauth");
  const [authorizing, setAuthorizing] = useState(false);
  const [authLink, setAuthLink] = useState("");
  const [broker, setBroker] = useState({
    app_key: "",
    app_secret: "",
    access_token: "",
  });
  useEffect(() => {
    api("/settings")
      .then(setData)
      .catch((e) => notify(e.message));
  }, []);
  const auth: BrokerAuth = data?.broker_auth ?? {
    method: data?.credentials?.longport ? "apikey" : null,
    pending: false,
    message: "请重启 SignalDesk 以启用长桥 OAuth 登录。",
  };
  const { pending } = auth;
  useEffect(() => {
    if (!pending) return;
    let disposed = false;
    async function check() {
      try {
        const status = await api<BrokerAuth>("/broker/oauth/status");
        if (disposed) return;
        setData((old: any) => ({ ...old, broker_auth: status }));
        if (!status.pending) setAuthLink("");
      } catch {
        // A later poll can recover from a temporary local connection failure.
      }
    }
    const timer = window.setInterval(check, 2000);
    window.addEventListener("focus", check);
    return () => {
      disposed = true;
      window.clearInterval(timer);
      window.removeEventListener("focus", check);
    };
  }, [pending]);
  async function login() {
    const page = window.open("about:blank", "_blank");
    if (page) page.opener = null;
    setAuthorizing(true);
    try {
      const { url } = await api("/broker/oauth/start", { method: "POST" });
      setAuthLink(url);
      setData((old: any) =>
        old
          ? {
              ...old,
              broker_auth: { ...old.broker_auth, pending: true, message: "" },
            }
          : old,
      );
      if (page && !page.closed) page.location.replace(url);
    } catch (error: any) {
      page?.close();
      notify(error.message);
    } finally {
      setAuthorizing(false);
    }
  }
  const patch = (section: string | null, field: string, value: any) =>
    setData((old: any) => ({
      ...old,
      settings: section
        ? {
            ...old.settings,
            [section]: { ...old.settings[section], [field]: value },
          }
        : { ...old.settings, [field]: value },
    }));
  async function save() {
    setBusy(true);
    try {
      if (qqSecret) {
        await api("/credentials", {
          method: "POST",
          body: JSON.stringify({ service: "qq", app_secret: qqSecret }),
        });
        setQQSecret("");
      }
      if (
        method === "apikey" &&
        (Object.values(broker).some(Boolean) ||
          (brokerPlatform && brokerPlatform !== data.broker_platform))
      ) {
        await api("/credentials", {
          method: "POST",
          body: JSON.stringify({
            service: "longport",
            platform: brokerPlatform ?? data.broker_platform,
            ...broker,
          }),
        });
        setBroker({ app_key: "", app_secret: "", access_token: "" });
        setBrokerPlatform(null);
      }
      const payloadSettings = {
        ...data.settings,
        default_agent: data.settings.default_agent ?? "codex",
        codex: {
          ...data.settings.codex,
          automatic: false,
        },
        antigravity: {
          enabled: true,
          timeout_seconds: 600,
          ...(data.settings.antigravity ?? {}),
        },
      };
      await api("/settings", {
        method: "PUT",
        body: JSON.stringify(payloadSettings),
      });
      notify("设置已保存。凭据只保存在本机。");
      const refreshed = await api("/settings");
      setData(refreshed);
      return true;
    } catch (e: any) {
      notify(e.message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  const tabs = [
    ["general", "运行方式", Settings2],
    ["broker", "长桥数据", KeyRound],
    ["qq", "QQ官方机器人", Send],
    ["codex", "Agent 复核", Bot],
    ["rules", "融合规则", SlidersHorizontal],
  ] as const;
  return (
    <div
      className="modal-shade"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        className="settings-modal"
        role="dialog"
        aria-modal="true"
        aria-label="设置与接入"
      >
        <header className="modal-header">
          <div>
            <span className="eyebrow">LOCAL PREFERENCES</span>
            <h2>{first ? "欢迎使用 SignalDesk" : "设置与接入"}</h2>
          </div>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="关闭设置"
          >
            <X size={20} />
          </button>
        </header>
        <div className="settings-layout">
          <nav>
            {tabs.map(([id, label, Icon]) => (
              <button
                key={id}
                className={tab === id ? "selected" : ""}
                onClick={() => setTab(id)}
              >
                <Icon size={16} />
                {label}
              </button>
            ))}
            <div className="privacy-note">
              <ShieldCheck size={19} />
              <span>
                原始账户与凭据
                <br />
                只保存在这台电脑
              </span>
            </div>
          </nav>
          <div className="settings-content">
            {!data ? (
              <p>正在加载本机设置…</p>
            ) : (
              <>
                {tab === "general" && (
                  <>
                    <h3>运行与通知</h3>
                    <p className="muted">
                      关闭看板后后台继续运行；从托盘可以完全退出。
                    </p>
                    <div className="setting-row">
                      <div>
                        <b>登录 Windows 后自动启动</b>
                        <small>{data.startup.detail}</small>
                      </div>
                      <input
                        type="checkbox"
                        aria-label="登录后自动启动"
                        checked={data.startup.enabled}
                        disabled={!data.startup.supported}
                        onChange={async (e) => {
                          try {
                            const startup = await api("/startup", {
                              method: "PUT",
                              body: JSON.stringify({
                                enabled: e.target.checked,
                              }),
                            });
                            setData({ ...data, startup });
                            notify("启动方式已更新");
                          } catch (error: any) {
                            notify(error.message);
                          }
                        }}
                      />
                    </div>
                    <div className="setting-row">
                      <div>
                        <b>Windows 本地通知</b>
                        <small>
                          系统勿扰模式可能影响弹窗；记录始终保留在看板。
                        </small>
                      </div>
                      <input
                        type="checkbox"
                        checked={data.settings.desktop_notifications}
                        onChange={(e) =>
                          patch(null, "desktop_notifications", e.target.checked)
                        }
                      />
                    </div>
                    <div className="setting-row">
                      <div>
                        <b>暂停普通提醒</b>
                        <small>重要关键价风险继续提醒。</small>
                      </div>
                      <input
                        type="checkbox"
                        checked={data.settings.pause_ordinary}
                        onChange={(e) =>
                          patch(null, "pause_ordinary", e.target.checked)
                        }
                      />
                    </div>
                    <label className="field">
                      行情模式
                      <select
                        value={data.settings.mode}
                        onChange={(e) => patch(null, "mode", e.target.value)}
                      >
                        <option value="demo">
                          演示 · 完全合成的数据与持仓
                        </option>
                        <option value="live">实盘 · LongPort只读数据</option>
                      </select>
                    </label>
                    <div className="notice">
                      演示模式不会自动向 QQ 或 Codex
                      发送事件。实盘数据与演示数据分开保存。
                    </div>
                  </>
                )}
                {tab === "broker" && (
                  <>
                    <h3>长桥只读连接</h3>
                    <p className="muted">
                      授权 SignalDesk 读取行情、持仓和自选股。OpenAPI
                      行情权限由长桥单独提供。
                    </p>
                    <div className="credential-state" role="status">
                      {auth.method && !auth.message && !pending ? (
                        <CheckCircle2 size={15} />
                      ) : (
                        <KeyRound size={15} />
                      )}
                      {pending
                        ? "等待浏览器授权"
                        : auth.message ||
                          (auth.method === "oauth"
                            ? "已保存长桥 OAuth 授权"
                            : auth.method === "apikey"
                              ? "当前使用 API Key"
                              : "尚未授权")}
                    </div>
                    <label className="field">
                      认证方式
                      <select
                        value={method}
                        onChange={(e) => setMethod(e.target.value)}
                      >
                        <option value="oauth">OAuth 2.0（推荐）</option>
                        <option value="apikey">API Key（兼容）</option>
                      </select>
                    </label>
                    {method === "oauth" ? (
                      <>
                        <p className="muted">
                          在长桥官网确认账户读取和自选股权限，完成后回到这里。
                        </p>
                        <button
                          className="button primary"
                          onClick={login}
                          disabled={busy || authorizing || !data.broker_auth}
                        >
                          {authorizing ? (
                            <LoaderCircle size={15} className="spin" />
                          ) : (
                            <ExternalLink size={15} />
                          )}
                          {authorizing
                            ? "正在连接长桥…"
                            : pending
                              ? "重新发起授权"
                              : auth.method === "oauth"
                                ? "重新登录长桥"
                                : "登录长桥"}
                        </button>
                        {authLink && pending && (
                          <a
                            className="button secondary"
                            href={authLink}
                            target="_blank"
                            rel="noreferrer"
                          >
                            打开本次授权页
                          </a>
                        )}
                      </>
                    ) : (
                      <>
                        <label className="field">
                          凭据签发网站
                          <select
                            value={brokerPlatform ?? data.broker_platform}
                            onChange={(e) => setBrokerPlatform(e.target.value)}
                          >
                            <option value="longbridge">
                              长桥 · open.longbridge.com
                            </option>
                            <option value="longport">
                              LongPort · open.longportapp.com
                            </option>
                          </select>
                        </label>
                        {(
                          ["app_key", "app_secret", "access_token"] as const
                        ).map((key) => (
                          <label className="field" key={key}>
                            {key}
                            <input
                              type="password"
                              autoComplete="off"
                              value={broker[key]}
                              onChange={(e) =>
                                setBroker({ ...broker, [key]: e.target.value })
                              }
                              placeholder={
                                auth.method === "apikey"
                                  ? "留空沿用已保存的值"
                                  : "仅在本机输入"
                              }
                            />
                          </label>
                        ))}
                      </>
                    )}
                    <div className="setting-row">
                      <div>
                        <b>自动同步账号自选股单</b>
                        <small>
                          只读同步长桥自选分组中的美股标的，绝不修改券商自选。
                        </small>
                      </div>
                      <input
                        type="checkbox"
                        aria-label="自动同步账号自选股单"
                        checked={data.settings.sync_watchlist ?? true}
                        onChange={(e) =>
                          patch(null, "sync_watchlist", e.target.checked)
                        }
                      />
                    </div>
                    <div className="notice">
                      完成接入后，在「运行方式」中选择「实盘」并保存，即可开始同步。
                    </div>
                  </>
                )}
                {tab === "qq" && (
                  <>
                    <h3>QQ 官方机器人</h3>
                    <p className="muted">
                      通过 QQ 官方 OpenAPI
                      发送单向技术提醒。默认不包含金额、成本和仓位比例。
                    </p>
                    <div className="setting-row">
                      <div>
                        <b>启用 QQ 通知</b>
                        <small>主动消息须有对应平台权限或订阅授权。</small>
                      </div>
                      <input
                        type="checkbox"
                        checked={data.settings.qq.enabled}
                        onChange={(e) =>
                          patch("qq", "enabled", e.target.checked)
                        }
                      />
                    </div>
                    <label className="field">
                      AppID
                      <input
                        value={data.settings.qq.app_id}
                        onChange={(e) => patch("qq", "app_id", e.target.value)}
                      />
                    </label>
                    <label className="field">
                      AppSecret
                      <input
                        type="password"
                        autoComplete="off"
                        value={qqSecret}
                        onChange={(e) => setQQSecret(e.target.value)}
                        placeholder={
                          data.credentials.qq
                            ? "已加密保存，留空保留"
                            : "仅在本机填写"
                        }
                      />
                    </label>
                    <div className="field-grid">
                      <label className="field">
                        接收目标
                        <select
                          value={data.settings.qq.target_kind}
                          onChange={(e) =>
                            patch("qq", "target_kind", e.target.value)
                          }
                        >
                          <option value="user">本人 QQ 单聊</option>
                          <option value="group">指定 QQ 群</option>
                        </select>
                      </label>
                      <label className="field">
                        目标 OpenID
                        <input
                          value={data.settings.qq.target_openid}
                          onChange={(e) =>
                            patch("qq", "target_openid", e.target.value)
                          }
                          placeholder="不是QQ号或群号"
                        />
                      </label>
                    </div>
                    <div className="notice">
                      OpenID 与当前 AppID
                      绑定，可从已有官方机器人的事件/调试记录取得。首版不公开本机回调端口。目标或主动权限未就绪时，看板会明确显示受限。
                    </div>
                    <button
                      className="button secondary"
                      disabled={busy}
                      onClick={async () => {
                        if (!(await save())) return;
                        try {
                          const r = await api("/channels/qq/test", {
                            method: "POST",
                          });
                          notify(r.detail);
                        } catch (e: any) {
                          notify(e.message);
                        }
                      }}
                    >
                      <Send size={14} />
                      保存并向配置目标发送测试
                    </button>
                  </>
                )}
                {tab === "codex" && (
                  <>
                    <h3>本地官方 Agent 长期复核</h3>
                    <p className="muted">
                      仅通过官方公开协议连接本机已安装的编码智能体 CLI（Google Antigravity 官方{" "}
                      <code>agy acp</code> 与 OpenAI 官方 <code>codex exec</code>
                      ），拒绝任何非官方桥接或包装器。
                    </p>
                    <div className="notice">
                      所有 Agent 均强制为手动触发、只读隔离运行（ACP 关闭客户端文件读写与终端权限），仅发送白名单脱敏快照，绝不传出账户标识、股数、成本与资金流水。
                    </div>
                    <label className="field">
                      默认首选 Agent
                      <select
                        value={data.settings.default_agent ?? "codex"}
                        onChange={(e) =>
                          patch(null, "default_agent", e.target.value)
                        }
                      >
                        <option value="antigravity">
                          Google Antigravity CLI（官方 ACP · agy acp）
                        </option>
                        <option value="codex">
                          OpenAI Codex CLI（官方非交互 · codex exec）
                        </option>
                      </select>
                    </label>

                    <div className="setting-row">
                      <div>
                        <b>启用 Google Antigravity CLI（官方 ACP）</b>
                        <small>
                          使用官方 Agent Client Protocol（<code>agy acp</code> JSON-RPC 2.0 over stdio）；首次登录可执行{" "}
                          <code>agy acp --login</code> 或配置 <code>GEMINI_API_KEY</code>。
                        </small>
                      </div>
                      <input
                        type="checkbox"
                        checked={data.settings.antigravity?.enabled ?? true}
                        onChange={(e) =>
                          patch("antigravity", "enabled", e.target.checked)
                        }
                      />
                    </div>
                    <label className="field">
                      Antigravity 单次超时 / 秒
                      <input
                        type="number"
                        min="15"
                        max="900"
                        value={data.settings.antigravity?.timeout_seconds ?? 600}
                        onChange={(e) =>
                          patch(
                            "antigravity",
                            "timeout_seconds",
                            Number(e.target.value),
                          )
                        }
                      />
                    </label>

                    <div className="setting-row">
                      <div>
                        <b>启用 OpenAI Codex CLI（官方 codex exec）</b>
                        <small>
                          使用官方 <code>codex exec --output-schema</code>{" "}
                          最小只读目录权限运行；首次登录可执行 <code>codex login</code>。
                        </small>
                      </div>
                      <input
                        type="checkbox"
                        checked={data.settings.codex.enabled}
                        onChange={(e) =>
                          patch("codex", "enabled", e.target.checked)
                        }
                      />
                    </div>
                    <label className="field">
                      Codex 单次超时 / 秒
                      <input
                        type="number"
                        min="15"
                        max="900"
                        value={data.settings.codex.timeout_seconds}
                        onChange={(e) =>
                          patch(
                            "codex",
                            "timeout_seconds",
                            Number(e.target.value),
                          )
                        }
                      />
                    </label>
                    <div className="notice">
                      发送脱敏个股估值、美债利率、日线结构、学术因子、风险预算及计划价距离。个股「AI 复核」面板可自由切换引擎或先查看脱敏预览。
                    </div>
                  </>
                )}
                {tab === "rules" && (
                  <>
                    <h3>可解释的融合规则</h3>
                    <p className="muted">
                      分数描述技术结构，不是上涨概率。风险与流动性独立判断。
                    </p>
                    <div className="field-grid">
                      {[
                        ["trend_weight", "趋势权重"],
                        ["momentum_weight", "动量权重"],
                        ["volume_weight", "量价权重"],
                        ["strong_threshold", "偏强阈值"],
                        ["weak_threshold", "偏弱阈值"],
                        ["cooldown_minutes", "普通提醒冷却 / 分钟"],
                      ].map(([key, label]) => (
                        <label className="field" key={key}>
                          {label}
                          <input
                            type="number"
                            step="any"
                            value={data.settings.rules[key]}
                            onChange={(e) =>
                              patch("rules", key, Number(e.target.value))
                            }
                          />
                        </label>
                      ))}
                    </div>
                    <div className="operator-tags">
                      {(data.operators ?? []).map((o: any) => (
                        <span title={o.description} key={o.name}>
                          {o.name}
                        </span>
                      ))}
                    </div>
                    <div className="setting-row">
                      <div>
                        <b>学术升级推荐权重（fusion-2.0.0）</b>
                        <small>
                          趋势 45% + 动量 40% + 10日平滑量价 15%（降低单日成交噪音）
                        </small>
                      </div>
                      <button
                        type="button"
                        className="button secondary"
                        onClick={() => {
                          patch("rules", "trend_weight", 0.45);
                          patch("rules", "momentum_weight", 0.4);
                          patch("rules", "volume_weight", 0.15);
                          notify("已预填推荐权重，请点击右下角「保存设置」生效");
                        }}
                      >
                        恢复推荐权重
                      </button>
                    </div>
                    <p className="muted">
                      权重之和必须为1。指标仅使用已确认K线；缺失值和未完成窗口不会被补零。
                    </p>
                  </>
                )}
              </>
            )}
          </div>
        </div>
        <footer className="modal-footer">
          <span>
            <ShieldCheck size={13} />
            凭据不会回显或进入 Git
          </span>
          <button className="button secondary" onClick={onClose}>
            {first ? "先看看演示" : "关闭"}
          </button>
          <button
            className="button primary"
            disabled={!data || busy}
            onClick={save}
          >
            {busy ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <Settings2 size={15} />
            )}
            保存设置
          </button>
        </footer>
      </section>
    </div>
  );
}
