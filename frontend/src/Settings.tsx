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
  LoaderCircle,
} from "lucide-react";
import { api } from "./types";

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
      if (Object.values(broker).some(Boolean)) {
        await api("/credentials", {
          method: "POST",
          body: JSON.stringify({ service: "longport", ...broker }),
        });
        setBroker({ app_key: "", app_secret: "", access_token: "" });
      }
      await api("/settings", {
        method: "PUT",
        body: JSON.stringify(data.settings),
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
    ["broker", "LongPort数据", KeyRound],
    ["qq", "QQ官方机器人", Send],
    ["codex", "Codex分析", Bot],
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
                    <h3>让监控按你的节奏运行</h3>
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
                    <h3>LongPort 只读连接</h3>
                    <p className="muted">
                      配置官方 OpenAPI 的凭据，行情权限与长桥 App
                      独立。这里没有下单接口。
                    </p>
                    <div className="credential-state">
                      <CheckCircle2 size={15} />
                      {data.credentials.longport
                        ? "已保存加密凭据；留空保留现有值"
                        : "尚未配置，请在本机填写"}
                    </div>
                    {(["app_key", "app_secret", "access_token"] as const).map(
                      (key) => (
                        <label className="field" key={key}>
                          {key}
                          <input
                            type="password"
                            autoComplete="off"
                            value={broker[key]}
                            onChange={(e) =>
                              setBroker({ ...broker, [key]: e.target.value })
                            }
                            placeholder="只在本机输入，保存后不回显"
                          />
                        </label>
                      ),
                    )}
                    <div className="notice">
                      保存凭据后，在运行方式中选择“实盘”。程序将同步持仓，并加载交易日历、历史K线和推送行情。
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
                    <h3>把判断交给 Codex</h3>
                    <p className="muted">
                      使用本机 Codex CLI
                      的登录与模型设置。只有脱敏快照会进入分析输入，分析在
                      OpenAI 服务完成。
                    </p>
                    <div className="setting-row">
                      <div>
                        <b>启用 Codex 分析</b>
                        <small>使用精确读取范围与隔离运行配置。</small>
                      </div>
                      <input
                        type="checkbox"
                        checked={data.settings.codex.enabled}
                        onChange={(e) =>
                          patch("codex", "enabled", e.target.checked)
                        }
                      />
                    </div>
                    <div className="setting-row">
                      <div>
                        <b>关键事件自动分析</b>
                        <small>普通行情计算和风险提醒不等待模型。</small>
                      </div>
                      <input
                        type="checkbox"
                        checked={data.settings.codex.automatic}
                        onChange={(e) =>
                          patch("codex", "automatic", e.target.checked)
                        }
                      />
                    </div>
                    <div className="field-grid">
                      {[
                        ["daily_limit", "每日自动调用上限"],
                        ["cooldown_minutes", "同股冷却 / 分钟"],
                        ["timeout_seconds", "单次超时 / 秒"],
                      ].map(([key, label]) => (
                        <label className="field" key={key}>
                          {label}
                          <input
                            type="number"
                            min="0"
                            value={data.settings.codex[key]}
                            onChange={(e) =>
                              patch("codex", key, Number(e.target.value))
                            }
                          />
                        </label>
                      ))}
                    </div>
                    <div className="notice">
                      可发送股票、长短线分类、仓位和盈亏百分比；不会发送账户标识、持仓数量、金额、成本或流水。个股面板可预览发送内容。
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
                        ["max_extended_spread", "盘外最大价差比例"],
                        ["min_extended_turnover", "盘外最小15分钟成交额 / USD"],
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
                      {data.operators.map((o: any) => (
                        <span title={o.description} key={o.name}>
                          {o.name}
                        </span>
                      ))}
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
