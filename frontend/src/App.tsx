import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  Bell,
  Bot,
  CircleDot,
  Clock3,
  Moon,
  Plus,
  Settings2,
  SlidersHorizontal,
  Star,
  Sun,
  Trash2,
  TriangleAlert,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import Chart from "./Chart";
import SettingsPanel from "./Settings";
import StockInspector, { type InspectorTab } from "./StockInspector";
import WatchlistRail from "./WatchlistRail";
import {
  api,
  fmt,
  ticker,
  time,
  type Dashboard,
  type Detail,
  type Stock,
} from "./types";

function AllocationEditor({
  stock,
  presetStop,
  presetTarget,
  onClose,
  onSaved,
  notify,
}: {
  stock: Stock | null;
  presetStop?: number | null;
  presetTarget?: number | null;
  onClose: () => void;
  onSaved: () => void;
  notify: (s: string) => void;
}) {
  const [symbol, setSymbol] = useState(stock?.symbol ?? "");
  const [name, setName] = useState(stock?.name ?? "");
  const [long, setLong] = useState(stock?.long_quantity ?? 0);
  const [short, setShort] = useState(stock?.short_quantity ?? 0);
  const [watchSleeve, setWatchSleeve] = useState(stock?.watch_sleeve ?? "long");
  const [stop, setStop] = useState(
    (presetStop ?? stock?.long_plan.stop)?.toString() ?? "",
  );
  const [target, setTarget] = useState(
    (presetTarget ?? stock?.long_plan.target)?.toString() ?? "",
  );
  const [favorite, setFavorite] = useState(stock?.favorite ?? false);
  const [busy, setBusy] = useState(false);
  const held = (stock?.broker_quantity ?? 0) > 0;
  const canDelete = Boolean(
    stock && stock.broker_quantity === 0 && !stock.in_watchlist,
  );

  return (
    <div
      className="modal-shade"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        className="small-modal"
        role="dialog"
        aria-modal="true"
        aria-label="持仓分类与关键价"
      >
        <header className="modal-header">
          <div>
            <h2>{stock ? `${ticker(stock.symbol)} · 计划与分类` : "添加本地观察股票"}</h2>
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="关闭分类"
          >
            <X size={20} />
          </button>
        </header>
        <div className="small-modal-body">
          <div className="field-grid">
            <label className="field">
              美股代码
              <input
                autoFocus
                value={symbol}
                disabled={!!stock}
                onChange={(e) => setSymbol(e.target.value)}
                placeholder="例如 AAPL"
              />
            </label>
            <label className="field">
              显示名称
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </label>
          </div>
          {held ? (
            <>
              <div className="notice">
                券商持仓 {stock?.broker_quantity}{" "}
                股。两类合计应与券商数量一致；差额会标记为待核对。
              </div>
              <div className="field-grid">
                <label className="field">
                  长期底仓 / 股
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={long}
                    onChange={(e) => setLong(Number(e.target.value))}
                  />
                </label>
                <label className="field">
                  其他仓位 / 股（仅核对）
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={short}
                    onChange={(e) => setShort(Number(e.target.value))}
                  />
                </label>
              </div>
            </>
          ) : (
            <label className="field">
              观察策略
              <select
                value={watchSleeve}
                onChange={(e) => setWatchSleeve(e.target.value)}
              >
                {stock?.watch_sleeve === "short" && (
                  <option value="short">历史短线分类</option>
                )}
                <option value="long">长期价值观察</option>
              </select>
            </label>
          )}
          <div className="field-grid">
            <label className="field">
              计划失效观察价（美元）
              <input
                type="number"
                min="0"
                step="any"
                value={stop}
                onChange={(e) => setStop(e.target.value)}
                placeholder="跌破时提醒复核"
              />
            </label>
            <label className="field">
              目标观察价（美元）
              <input
                type="number"
                min="0"
                step="any"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder="达到时提醒复核"
              />
            </label>
          </div>

          <div className="setting-row editor-fav-row">
            <div>
              <b>加入本地收藏 ★</b>
              <small>保存在本机，可直接在左侧「★ 收藏」列表中集中看盘。</small>
            </div>
            <input
              type="checkbox"
              aria-label="加入本地收藏"
              checked={favorite}
              onChange={(e) => setFavorite(e.target.checked)}
            />
          </div>

          <p className="muted">
            以上价格用于长期计划。盘中触价时提醒，收盘后用日线复核。
          </p>
        </div>
        <footer className="modal-footer">
          {canDelete ? (
            <button
              type="button"
              className="button danger-ghost"
              disabled={busy}
              onClick={async () => {
                if (!stock) return;
                setBusy(true);
                try {
                  await api(`/watchlist/${stock.symbol}`, { method: "DELETE" });
                  notify(`已移出本地观察 ${ticker(stock.symbol)}`);
                  onSaved();
                  onClose();
                } catch (e: any) {
                  notify(e.message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <Trash2 size={15} />
              移出本地观察
            </button>
          ) : (
            <span>仅保存在本机</span>
          )}
          <button type="button" className="button secondary" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="button primary"
            disabled={busy || !symbol}
            onClick={async () => {
              setBusy(true);
              try {
                await api("/allocations", {
                  method: "PUT",
                  body: JSON.stringify({
                    symbol,
                    name,
                    long_quantity: long,
                    short_quantity: short,
                    watch_only: !held,
                    watch_sleeve: watchSleeve,
                    stop_price: stock?.stop_price ?? null,
                    target_price: stock?.target_price ?? null,
                    long_stop_price: stop ? Number(stop) : null,
                    long_target_price: target ? Number(target) : null,
                    favorite,
                  }),
                });
                notify("计划与收藏状态已保存");
                onSaved();
                onClose();
              } catch (e: any) {
                notify(e.message);
              } finally {
                setBusy(false);
              }
            }}
          >
            保存计划
          </button>
        </footer>
      </section>
    </div>
  );
}

export default function App() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const [theme, setTheme] = useState(
    localStorage.getItem("sd-theme-v2") ?? "light",
  );
  const [reverse, setReverse] = useState(
    localStorage.getItem("sd-reverse") === "true",
  );
  const [selected, setSelected] = useState("NVDA.US");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [settings, setSettings] = useState(false);
  const [first, setFirst] = useState(!localStorage.getItem("sd-onboarded"));
  const [toast, setToast] = useState("");
  const [editor, setEditor] = useState<
    | {
        stock: Stock | null;
        presetStop?: number | null;
        presetTarget?: number | null;
      }
    | undefined
  >(undefined);
  const [preview, setPreview] = useState<any>(null);
  const [deliveries, setDeliveries] = useState<any[] | null>(null);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("summary");
  const [syncingWatchlist, setSyncingWatchlist] = useState(false);

  const notify = (s: string) => setToast(s);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 6500);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("sd-theme-v2", theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.dataset.reverse = String(reverse);
    localStorage.setItem("sd-reverse", String(reverse));
  }, [reverse]);

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    async function connect() {
      try {
        const snapshot = await api<Dashboard>("/bootstrap");
        if (disposed) return;
        setData(snapshot);
        setError("");
        if (!localStorage.getItem("sd-onboarded")) setSettings(true);
        socket = new WebSocket(
          `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/stream`,
        );
        socket.onopen = () => {
          if (!disposed) setConnected(true);
        };
        socket.onmessage = (e) => {
          if (!disposed) setData(JSON.parse(e.data));
        };
        socket.onclose = () => {
          if (!disposed) {
            setConnected(false);
            retry = setTimeout(connect, 3000);
          }
        };
        socket.onerror = () => socket?.close();
      } catch (e: any) {
        if (!disposed) {
          setError(e.message);
          retry = setTimeout(connect, 3000);
        }
      }
    }
    connect();
    return () => {
      disposed = true;
      clearTimeout(retry);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    if (data?.stocks.length && !data.stocks.some((s) => s.symbol === selected)) {
      setSelected(data.stocks[0].symbol);
    }
  }, [data?.stocks, selected]);

  const stock = data?.stocks.find((s) => s.symbol === selected) ?? null;

  useEffect(() => {
    let disposed = false;
    async function load() {
      if (!stock) return;
      try {
        const value = await api<Detail>(`/stock/${selected}`);
        if (!disposed) setDetail(value);
      } catch {
        if (!disposed) setDetail(null);
      }
    }
    load();
    const timer = setInterval(load, 300000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [
    selected,
    data?.mode,
    !!stock,
    stock?.primary.as_of,
    stock?.primary.score,
    stock?.primary.rule_version,
    stock?.primary.state,
    stock?.long_plan.stop,
    stock?.long_plan.target,
  ]);

  const analysis = data?.analyses.find(
    (a) =>
      a.symbol === selected &&
      a.source === data.mode &&
      a.scope === "long_value",
  );
  const currentDetail =
    stock && detail?.stock.symbol === selected && detail.mode === data?.mode
      ? detail
      : null;
  const summary = currentDetail?.summary ?? null;
  const curve = data?.curve;

  async function refresh() {
    try {
      setData(await api("/dashboard"));
    } catch (e: any) {
      notify(e.message);
    }
  }

  async function toggleFavorite(target: Stock) {
    const next = !target.favorite;
    setData((prev) =>
      prev
        ? {
            ...prev,
            stocks: prev.stocks.map((item) =>
              item.symbol === target.symbol ? { ...item, favorite: next } : item,
            ),
          }
        : prev,
    );
    try {
      await api(`/favorites/${target.symbol}`, {
        method: "PUT",
        body: JSON.stringify({ favorite: next }),
      });
      notify(
        next
          ? `已收藏 ${ticker(target.symbol)}`
          : `已取消收藏 ${ticker(target.symbol)}`,
      );
      refresh();
    } catch (e: any) {
      notify(e.message);
      refresh();
    }
  }

  async function syncWatchlist() {
    setSyncingWatchlist(true);
    try {
      const res = await api<{ ok: boolean; message: string }>(
        "/watchlist/sync",
        { method: "POST" },
      );
      notify(res.message);
      await refresh();
    } catch (e: any) {
      notify(e.message);
    } finally {
      setSyncingWatchlist(false);
    }
  }

  async function removeLocalWatch(target: Stock) {
    try {
      await api(`/watchlist/${target.symbol}`, { method: "DELETE" });
      notify(`已移出本地观察 ${ticker(target.symbol)}`);
      await refresh();
    } catch (e: any) {
      notify(e.message);
    }
  }

  async function analyze() {
    if (!stock) return;
    setInspectorTab("codex");
    try {
      await api(`/analysis/${stock.symbol}`, { method: "POST" });
      notify("已手动提交 Codex 总结任务；行情监控继续运行");
      await refresh();
    } catch (e: any) {
      notify(e.message);
    }
  }

  async function showPreview() {
    if (!stock) return;
    try {
      setPreview(await api(`/analysis/preview/${stock.symbol}`));
    } catch (e: any) {
      notify(e.message);
    }
  }

  const closeSettings = () => {
    setSettings(false);
    setFirst(false);
    localStorage.setItem("sd-onboarded", "1");
    refresh();
  };

  const bjClock = data?.now
    ? new Date(data.now).toLocaleTimeString("zh-CN", {
        timeZone: "Asia/Shanghai",
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
  const nyClock = data?.now
    ? new Date(data.now).toLocaleTimeString("en-US", {
        timeZone: "America/New_York",
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

  const changeClass =
    stock?.change_percent == null
      ? "muted"
      : stock.change_percent >= 0
        ? "quote-up"
        : "quote-down";

  const verdict = stock?.verdict;
  const canDeleteSelected = Boolean(
    stock && stock.broker_quantity === 0 && !stock.in_watchlist,
  );

  return (
    <div className="desk-shell">
      <header className="desk-topbar">
        <div className="topbar-left">
          <div className="brand-mark">
            <span className="brand-badge">
              <Activity size={19} />
            </span>
            <b>SignalDesk</b>
          </div>
          <button
            type="button"
            className={`mode-badge ${data?.mode === "live" ? "live" : "demo"}`}
            onClick={() => setSettings(true)}
            title="点击切换实盘/演示或修改接入设置"
          >
            <i />
            {data?.mode === "live" ? "实盘只读" : "演示工作区"}
          </button>
          <div className="market-status-chip">
            <span
              className={`session-dot ${data?.market.session === "regular" ? "open" : ""}`}
            />
            <span>
              {data?.market.label ?? "连接中"}
              {data?.market.early_close ? " · 提前收盘" : ""}
            </span>
          </div>
          <div className="clock-chip" title="北京时间 / 纽约时间">
            <Clock3 size={14} />
            <span>京 {bjClock}</span>
            <span className="sep">/</span>
            <span>纽 {nyClock}</span>
          </div>
        </div>

        <div
          className="macro-strip"
          title={`来源：${curve?.source ?? "等待数据"} · 观察日期：${curve?.as_of ?? "暂无"}${curve?.as_of && !curve.fresh ? "（已过期）" : ""}`}
        >
          <span>
            美债2Y <b>{fmt(curve?.two_year, 2)}%</b>
          </span>
          <span>
            10Y <b>{fmt(curve?.ten_year, 2)}%</b>
          </span>
          <span>
            10Y-2Y{" "}
            <b>
              {curve?.spread_bp != null && curve.spread_bp >= 0 ? "+" : ""}
              {fmt(curve?.spread_bp, 0)}bp
            </b>
          </span>
          <span>
            10Y近21日{" "}
            <b>
              {curve?.ten_change_bp != null && curve.ten_change_bp >= 0
                ? "+"
                : ""}
              {fmt(curve?.ten_change_bp, 0)}bp
            </b>
          </span>
          {(curve?.refresh_failed || (curve?.as_of && !curve.fresh)) && (
            <em className="macro-warn">
              {curve?.refresh_failed ? "更新失败" : "利率已过期"}
            </em>
          )}
        </div>

        <div className="topbar-right">
          <span
            className={`conn-pill ${connected ? "online" : "offline"}`}
            title={data?.detail}
          >
            {connected ? <Wifi size={14} /> : <WifiOff size={14} />}
            <span>{connected ? "已连接" : "重连中"}</span>
          </span>
          <button
            type="button"
            className="top-btn"
            onClick={async () => {
              try {
                setDeliveries(await api("/deliveries"));
              } catch (e: any) {
                notify(e.message);
              }
            }}
          >
            <Bell size={15} />
            <span>通知记录</span>
          </button>
          <button
            type="button"
            className="top-btn"
            onClick={() => setReverse(!reverse)}
            title="切换涨跌配色习惯"
          >
            <span className="color-swap">
              {reverse ? "红涨绿跌" : "绿涨红跌"}
            </span>
          </button>
          <button
            type="button"
            className="top-icon-btn"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label="切换明暗主题"
            title={theme === "dark" ? "切换浅色主题" : "切换深色主题"}
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <button
            type="button"
            className="button primary top-settings-btn"
            onClick={() => setSettings(true)}
          >
            <Settings2 size={15} />
            <span>设置</span>
          </button>
        </div>
      </header>

      {(error ||
        data?.status === "degraded" ||
        data?.status === "unconfigured") && (
        <div className="alert-strip">
          <TriangleAlert size={16} />
          <span>{error || data?.detail}</span>
          <button type="button" onClick={() => setSettings(true)}>
            检查接入
            <ArrowRight size={14} />
          </button>
        </div>
      )}

      <main className="terminal-grid">
        <WatchlistRail
          allStocks={data?.stocks ?? []}
          watchlistGroups={data?.watchlist_groups ?? []}
          watchlistSync={data?.watchlist_sync}
          selected={selected}
          onSelect={setSelected}
          onToggleFavorite={toggleFavorite}
          onAddWatch={() => setEditor({ stock: null })}
          onSyncWatchlist={syncWatchlist}
          syncing={syncingWatchlist}
          onOpenSettings={() => setSettings(true)}
          mode={data?.mode ?? "demo"}
        />

        <section className="center-stage" aria-label="个股行情与K线主工作区">
          {stock ? (
            <>
              <div className="stock-hero">
                <div className="hero-left">
                  <button
                    type="button"
                    className={`hero-star ${stock.favorite ? "starred" : ""}`}
                    onClick={() => toggleFavorite(stock)}
                    aria-label={
                      stock.favorite ? "取消本地收藏" : "加入本地收藏"
                    }
                    title={stock.favorite ? "取消收藏" : "加入收藏"}
                  >
                    <Star
                      size={20}
                      fill={stock.favorite ? "currentColor" : "none"}
                    />
                  </button>
                  <div className="hero-identity">
                    <div className="hero-title-line">
                      <h1>{ticker(stock.symbol)}</h1>
                      <span className="hero-name">
                        {stock.name || "美股标的"}
                      </span>
                      {stock.broker_quantity > 0 && (
                        <span className="tag-chip held">
                          持仓 {fmt(stock.broker_quantity, 0)} 股
                          {stock.weight_percent != null
                            ? ` · 占比 ${fmt(stock.weight_percent, 1)}%`
                            : ""}
                        </span>
                      )}
                      {stock.pnl_percent != null && (
                        <span
                          className={`tag-chip ${stock.pnl_percent >= 0 ? "up" : "down"}`}
                        >
                          浮盈 {stock.pnl_percent >= 0 ? "+" : ""}
                          {fmt(stock.pnl_percent, 1)}%
                        </span>
                      )}
                      {(() => {
                        const groups = stock.watchlist_groups ?? [];
                        const maxGroups =
                          stock.broker_quantity > 0 || stock.pnl_percent != null
                            ? 1
                            : 2;
                        const shown = groups.slice(0, maxGroups);
                        const hiddenCount = groups.length - shown.length;
                        return (
                          <>
                            {shown.map((g) => (
                              <span className="tag-chip group" key={g}>
                                {g}
                              </span>
                            ))}
                            {hiddenCount > 0 && (
                              <span
                                className="tag-chip group"
                                title={groups.join(" · ")}
                              >
                                +{hiddenCount}
                              </span>
                            )}
                          </>
                        );
                      })()}
                    </div>
                  </div>
                </div>

                <div className="hero-right">
                  <div className="hero-quote">
                    <strong className="hero-price">
                      {stock.quote.last != null
                        ? "$" + fmt(stock.quote.last, 2)
                        : "—"}
                    </strong>
                    <span className={`hero-chg ${changeClass}`}>
                      {stock.change_percent != null
                        ? `${stock.change_percent >= 0 ? "+" : ""}${fmt(stock.change_percent, 2)}%`
                        : "待更新"}
                    </span>
                  </div>

                  <div className="hero-actions">
                    <button
                      type="button"
                      className="button secondary"
                      onClick={() => setEditor({ stock })}
                    >
                      <SlidersHorizontal size={15} />
                      编辑计划
                    </button>
                    <button
                      type="button"
                      className="button primary"
                      onClick={() => setInspectorTab("codex")}
                    >
                      <Bot size={15} />
                      Codex 总结
                    </button>
                    {canDeleteSelected && (
                      <button
                        type="button"
                        className="icon-button"
                        onClick={() => removeLocalWatch(stock)}
                        title="移出本地观察"
                        aria-label="移出本地观察"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {verdict && (
                <div className={`verdict-banner tone-${verdict.tone}`}>
                  <div className="verdict-main">
                    <div className="verdict-badges">
                      <span
                        className={`verdict-badge tone-${verdict.tone}`}
                        title={verdict.action_meaning || verdict.headline}
                      >
                        {verdict.action}
                      </span>
                      {stock.forecast?.rating.available && (
                        <span
                          className={`verdict-badge forecast-rating-badge tone-${stock.forecast.rating.tone}`}
                          title={stock.forecast.rating.summary}
                        >
                          {stock.forecast.rating.label}{" "}
                          {fmt(stock.forecast.rating.score, 0)}分
                        </span>
                      )}
                    </div>
                    <div className="verdict-copy">
                      <p className="verdict-headline">{verdict.headline}</p>
                      <p className="verdict-next">
                        下一步：{verdict.next_step}
                      </p>
                    </div>
                  </div>
                  <div className="verdict-pillars">
                    {verdict.pillars.map((p) => (
                      <div className="pillar-box" key={p.key}>
                        <div className="pillar-top">
                          <span>{p.label}</span>
                          <b className={`tone-text-${p.tone}`}>{p.status}</b>
                        </div>
                        <small>{p.detail}</small>
                      </div>
                    ))}
                  </div>
                  {stock.forecast?.levels.available && (
                    <div className="forecast-strip">
                      <div className="forecast-strip-item">
                        <span>买点</span>
                        <strong className="up">
                          ${fmt(stock.forecast.levels.buy_low, 2)} – $
                          {fmt(stock.forecast.levels.buy_high, 2)}
                        </strong>
                      </div>
                      <div className="forecast-strip-item">
                        <span>卖点</span>
                        <strong className="accent-val">
                          ${fmt(stock.forecast.levels.sell_low, 2)} – $
                          {fmt(stock.forecast.levels.sell_high, 2)}
                        </strong>
                      </div>
                      <div className="forecast-strip-item">
                        <span>止损</span>
                        <strong className="down">
                          ${fmt(stock.forecast.levels.stop_loss, 2)}
                        </strong>
                      </div>
                      <div className="forecast-strip-item">
                        <span>盈亏比</span>
                        <strong>
                          {fmt(stock.forecast.levels.risk_reward_ratio, 2)}:1
                        </strong>
                      </div>
                      {stock.forecast.levels.stop_loss != null &&
                        stock.forecast.levels.sell_low != null && (
                          <button
                            type="button"
                            className="text-btn forecast-strip-apply"
                            title="将参考止损与参考卖点预填到个人计划价"
                            onClick={() =>
                              setEditor({
                                stock,
                                presetStop: stock.forecast!.levels.stop_loss,
                                presetTarget: stock.forecast!.levels.sell_low,
                              })
                            }
                          >
                            采纳计划价
                          </button>
                        )}
                    </div>
                  )}
                </div>
              )}

              <div className="chart-panel-card">
                <Chart
                  detail={currentDetail}
                  theme={theme}
                  reverse={reverse}
                />
              </div>
            </>
          ) : (
            <div className="center-empty">
              <Activity size={36} />
              <h2>欢迎使用 SignalDesk 看盘工作台</h2>
              <p>
                {data?.mode === "live"
                  ? "尚未同步到持仓或自选美股，请点击右上角「设置」接入 LongPort，或手动添加观察标的。"
                  : "正在加载演示数据…"}
              </p>
              <div className="center-empty-actions">
                <button
                  type="button"
                  className="button primary"
                  onClick={() => setSettings(true)}
                >
                  <Settings2 size={15} />
                  配置 LongPort 接入
                </button>
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => setEditor({ stock: null })}
                >
                  <Plus size={15} />
                  添加本地观察股
                </button>
              </div>
            </div>
          )}
        </section>

        <StockInspector
          tab={inspectorTab}
          onTabChange={setInspectorTab}
          stock={stock}
          summary={summary}
          analysis={analysis}
          events={data?.events ?? []}
          channels={data?.channels}
          mode={data?.mode ?? "demo"}
          status={data?.status ?? "starting"}
          cooldownMinutes={data?.rules?.cooldown_minutes ?? 30}
          onEditPlan={() => stock && setEditor({ stock })}
          onApplyForecastLevels={(stopLoss, sellLow) =>
            stock &&
            setEditor({
              stock,
              presetStop: stopLoss,
              presetTarget: sellLow,
            })
          }
          onAnalyze={analyze}
          onPreview={showPreview}
          onSelectSymbol={setSelected}
          onOpenDeliveries={async () => {
            try {
              setDeliveries(await api("/deliveries"));
            } catch (e: any) {
              notify(e.message);
            }
          }}
          onOpenSettings={() => setSettings(true)}
        />
      </main>

      {settings && (
        <SettingsPanel onClose={closeSettings} notify={notify} first={first} />
      )}

      {editor !== undefined && (
        <AllocationEditor
          stock={editor.stock}
          presetStop={editor.presetStop}
          presetTarget={editor.presetTarget}
          onClose={() => setEditor(undefined)}
          onSaved={refresh}
          notify={notify}
        />
      )}

      {preview && (
        <div
          className="modal-shade"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setPreview(null);
          }}
        >
          <section
            className="small-modal preview-modal"
            role="dialog"
            aria-label="Codex脱敏发送预览"
          >
            <header className="modal-header">
              <div>
                <h2>Codex 脱敏发送预览</h2>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={() => setPreview(null)}
                aria-label="关闭预览"
              >
                <X size={20} />
              </button>
            </header>
            <p className="notice preview-notice">
              以下内容会交给 Codex；不包含账户标识、股数、金额、成本或流水。
            </p>
            <pre>{JSON.stringify(preview, null, 2)}</pre>
            <footer className="modal-footer">
              <span>当前股票 {ticker(selected)}</span>
              <button
                type="button"
                className="button secondary"
                onClick={() => setPreview(null)}
              >
                关闭
              </button>
              <button
                type="button"
                className="button primary"
                onClick={() => {
                  setPreview(null);
                  analyze();
                }}
              >
                立即生成 Codex 总结
                <ArrowRight size={15} />
              </button>
            </footer>
          </section>
        </div>
      )}

      {deliveries && (
        <div
          className="modal-shade"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setDeliveries(null);
          }}
        >
          <section
            className="small-modal"
            role="dialog"
            aria-label="通知投递记录"
          >
            <header className="modal-header">
              <h2>通知投递记录</h2>
              <button
                type="button"
                className="icon-button"
                onClick={() => setDeliveries(null)}
                aria-label="关闭通知记录"
              >
                <X size={20} />
              </button>
            </header>
            <div className="delivery-list">
              {deliveries.length ? (
                deliveries.map((d) => (
                  <div key={d.id}>
                    <b>
                      {d.channel} · {d.status}
                    </b>
                    <p>{d.result}</p>
                    <small>
                      尝试 {d.attempts} 次 · 事件 {d.event_id.slice(0, 8)}
                    </small>
                  </div>
                ))
              ) : (
                <div className="empty-state">
                  <Bell size={26} />
                  <b>还没有对外投递记录</b>
                  <p>演示回放只在看板展示，不会自动向机器人发送。</p>
                </div>
              )}
            </div>
          </section>
        </div>
      )}

      {toast && (
        <div className="toast" role="status">
          <CircleDot size={17} />
          <span>{toast}</span>
          <button
            type="button"
            onClick={() => setToast("")}
            aria-label="关闭提示"
          >
            <X size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
