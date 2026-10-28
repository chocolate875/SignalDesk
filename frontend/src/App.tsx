import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  ArrowRight,
  Bell,
  Bot,
  Check,
  ChevronDown,
  CircleDot,
  Clock3,
  ExternalLink,
  Eye,
  Filter,
  Gauge,
  LayoutDashboard,
  ListFilter,
  LoaderCircle,
  LockKeyhole,
  Moon,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Sun,
  TrendingUp,
  TriangleAlert,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import Chart from "./Chart";
import SettingsPanel from "./Settings";
import {
  api,
  fmt,
  labels,
  ticker,
  time,
  type Analysis,
  type Dashboard,
  type Detail,
  type Stock,
} from "./types";

const dimensionNames: Record<string, string> = {
  trend: "趋势",
  momentum: "动量",
  volume_score: "量价",
};
const dimensionColors: Record<string, string> = {
  trend: "#70c8ba",
  momentum: "#a3a6ed",
  volume_score: "#d8b875",
};
const colorFor = (score: number | null | undefined, state?: string) =>
  state
    ? ({
        strong: "positive",
        weak: "negative",
        neutral: "neutral",
        unavailable: "muted",
      }[state] ?? "muted")
    : score == null
      ? "muted"
      : score >= 70
        ? "positive"
        : score <= 30
          ? "negative"
          : "neutral";

function MiniBars({ stock }: { stock: Stock }) {
  return (
    <div className="mini-bars">
      {Object.entries(dimensionNames).map(([key, label]) => (
        <div
          key={key}
          title={`${label} ${fmt(stock.primary.dimensions?.[key])}`}
        >
          <span>{label}</span>
          <div className="bar-track">
            <i
              style={{
                width: `${stock.primary.dimensions?.[key] ?? 0}%`,
                background: dimensionColors[key],
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function Score({
  value,
  large = false,
  state,
}: {
  value: number | null | undefined;
  large?: boolean;
  state?: string;
}) {
  return (
    <span className={`score ${colorFor(value, state)} ${large ? "large" : ""}`}>
      {fmt(value)}
      {large && <small>/100</small>}
    </span>
  );
}

function AllocationEditor({
  stock,
  onClose,
  onSaved,
  notify,
}: {
  stock: Stock | null;
  onClose: () => void;
  onSaved: () => void;
  notify: (s: string) => void;
}) {
  const [symbol, setSymbol] = useState(stock?.symbol ?? "");
  const [name, setName] = useState(stock?.name ?? "");
  const [long, setLong] = useState(stock?.long_quantity ?? 0);
  const [short, setShort] = useState(stock?.short_quantity ?? 0);
  const [watchSleeve, setWatchSleeve] = useState(
    stock?.watch_sleeve ?? "short",
  );
  const [stop, setStop] = useState(stock?.stop_price?.toString() ?? "");
  const [target, setTarget] = useState(stock?.target_price?.toString() ?? "");
  const [busy, setBusy] = useState(false);
  const held = (stock?.broker_quantity ?? 0) > 0;
  return (
    <div className="modal-shade">
      <section
        className="small-modal"
        role="dialog"
        aria-modal="true"
        aria-label="持仓分类与关键价"
      >
        <header className="modal-header">
          <div>
            <span className="eyebrow">POSITION PLAN</span>
            <h2>{stock ? "分类与关键价" : "添加观察股票"}</h2>
          </div>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="关闭分类"
          >
            <X size={18} />
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
                  短线仓位 / 股
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
                <option value="short">短线 · 2–20交易日</option>
                <option value="long">长期 · 日线结构</option>
              </select>
            </label>
          )}
          <div className="field-grid">
            <label className="field">
              计划失效观察价
              <input
                type="number"
                min="0"
                step="any"
                value={stop}
                onChange={(e) => setStop(e.target.value)}
                placeholder="可选"
              />
            </label>
            <label className="field">
              目标观察价
              <input
                type="number"
                min="0"
                step="any"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder="可选"
              />
            </label>
          </div>
          <p className="muted">
            同股分仓时，关键价格优先关联短线部分。这里只记录计划并提醒，不会向券商提交订单。
          </p>
        </div>
        <footer className="modal-footer">
          <span>仅保存在本机</span>
          <button className="button secondary" onClick={onClose}>
            取消
          </button>
          <button
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
                    stop_price: stop ? Number(stop) : null,
                    target_price: target ? Number(target) : null,
                  }),
                });
                notify("分类与关键价已保存");
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

function AnalysisCard({
  analysis,
  stock,
  onAnalyze,
  preview,
}: {
  analysis: Analysis | undefined;
  stock: Stock | null;
  onAnalyze: () => void;
  preview: () => void;
}) {
  return (
    <section className="panel analysis-panel">
      <div className="panel-heading">
        <div className="section-title">
          <Bot size={17} />
          <h3>Codex 判断</h3>
          <span className="tiny-tag">人工智能分析</span>
        </div>
        <button className="text-button" onClick={preview} disabled={!stock}>
          <Eye size={13} />
          发送预览
        </button>
      </div>
      {analysis?.status === "completed" && analysis.result ? (
        <div className="analysis-result">
          <div className="analysis-verdict">
            <Sparkles size={16} />
            <b>{labels[analysis.result.action]}</b>
            <span>{time(analysis.result.data_as_of)}</span>
          </div>
          <p>{analysis.result.conclusion}</p>
          <div className="analysis-columns">
            <div>
              <small>支持与反对证据</small>
              {analysis.result.evidence.map((s, i) => (
                <p key={i}>· {s}</p>
              ))}
            </div>
            <div>
              <small>风险与待确认</small>
              {[
                ...analysis.result.risks,
                ...analysis.result.confirmation_conditions,
              ].map((s, i) => (
                <p key={i}>· {s}</p>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="analysis-placeholder">
          <div className="agent-orb">
            {analysis?.status === "running" || analysis?.status === "queued" ? (
              <LoaderCircle size={23} className="spin" />
            ) : (
              <Sparkles size={24} />
            )}
          </div>
          <div>
            <b>
              {analysis?.status === "running"
                ? "Codex 正在复核技术结构"
                : analysis?.status === "queued"
                  ? "分析已加入队列"
                  : analysis?.status === "failed"
                    ? "本次分析未完成"
                    : "让数据先说话，让 Codex 做判断"}
            </b>
            <p>
              {analysis?.error ??
                "发送脱敏技术快照，综合趋势、量价与风险，形成可复核的观察建议。"}
            </p>
          </div>
          <button
            className="button secondary"
            disabled={
              !stock ||
              analysis?.status === "running" ||
              analysis?.status === "queued"
            }
            onClick={onAnalyze}
          >
            <Sparkles size={14} />
            分析此股
          </button>
        </div>
      )}
      <footer className="analysis-foot">
        <LockKeyhole size={12} />
        账户标识、实际金额与交易流水不进入分析输入；分析失败不影响监控。
      </footer>
    </section>
  );
}

export default function App() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const [theme, setTheme] = useState(
    localStorage.getItem("sd-theme") ?? "dark",
  );
  const [reverse, setReverse] = useState(
    localStorage.getItem("sd-reverse") === "true",
  );
  const [selected, setSelected] = useState("NVDA.US");
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("default");
  const [timeframe, setTimeframe] = useState("15m");
  const [session, setSession] = useState("regular");
  const [overlay, setOverlay] = useState("MA");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [settings, setSettings] = useState(false);
  const [first, setFirst] = useState(!localStorage.getItem("sd-onboarded"));
  const [toast, setToast] = useState("");
  const [editor, setEditor] = useState<Stock | null | undefined>(undefined);
  const [preview, setPreview] = useState<any>(null);
  const [deliveries, setDeliveries] = useState<any[] | null>(null);
  const [signalFilter, setSignalFilter] = useState("all");
  const [nav, setNav] = useState("overview");

  const notify = (s: string) => setToast(s);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 6500);
    return () => clearTimeout(t);
  }, [toast]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("sd-theme", theme);
  }, [theme]);
  useEffect(() => {
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
    if (data?.stocks.length && !data.stocks.some((s) => s.symbol === selected))
      setSelected(data.stocks[0].symbol);
  }, [data?.mode, data?.stocks.length, selected]);
  useEffect(() => {
    let disposed = false;
    async function load() {
      if (!selected || !data) return;
      try {
        const value = await api<Detail>(
          `/stock/${selected}?timeframe=${timeframe}&session=${session}`,
        );
        if (!disposed) setDetail(value);
      } catch {
        if (!disposed) setDetail(null);
      }
    }
    setDetail(null);
    load();
    const timer = setInterval(load, 10000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [selected, timeframe, session, data?.mode]);
  const stocks = useMemo(() => {
    let values = (data?.stocks ?? []).filter(
      (s) =>
        (filter === "all" || s.sleeves.includes(filter)) &&
        `${s.symbol} ${s.name}`.toLowerCase().includes(query.toLowerCase()),
    );
    if (sort === "score")
      values = [...values].sort(
        (a, b) => (b.primary.score ?? -1) - (a.primary.score ?? -1),
      );
    if (sort === "risk")
      values = [...values].sort(
        (a, b) =>
          (b.primary.risks?.length ?? 0) - (a.primary.risks?.length ?? 0),
      );
    return values;
  }, [data?.stocks, filter, query, sort]);
  const stock = data?.stocks.find((s) => s.symbol === selected) ?? null;
  const analysis = data?.analyses.find(
    (a) => a.symbol === selected && a.source === data.mode,
  );
  const summary = detail?.summary ?? null;
  const signals = (data?.events ?? []).filter(
    (e) => signalFilter !== "risk" || e.severity !== "info",
  );
  const jobs =
    data?.analyses.filter(
      (a) => a.status === "queued" || a.status === "running",
    ).length ?? 0;
  async function analyze() {
    if (!stock) return;
    try {
      await api(`/analysis/${stock.symbol}`, { method: "POST" });
      notify("已交给 Codex 分析；指标监控继续运行");
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
  async function refresh() {
    try {
      setData(await api("/dashboard"));
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

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="SignalDesk首页">
          <span className="brand-icon">
            <Activity size={24} />
          </span>
          <span>
            Signal<span className="brand-light">Desk</span>
            <small>YOUR MARKET, IN FOCUS</small>
          </span>
        </a>
        <div className="workspace-tag">
          <span className="status-dot" />
          个人投资工作台
          <ChevronDown size={13} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav className="main-nav">
          <button
            className={nav === "overview" ? "active" : ""}
            onClick={() => {
              setNav("overview");
              document
                .getElementById("holdings")
                ?.scrollIntoView({ behavior: "smooth" });
            }}
          >
            <LayoutDashboard size={17} />
            组合概览<span>{data?.summary.count ?? "—"}</span>
          </button>
          <button
            className={nav === "signals" ? "active" : ""}
            onClick={() => {
              setNav("signals");
              document
                .getElementById("signal-queue")
                ?.scrollIntoView({ behavior: "smooth" });
            }}
          >
            <Activity size={17} />
            信号中心
            <i className="nav-dot" />
          </button>
          <button
            onClick={() => {
              document
                .getElementById("analysis")
                ?.scrollIntoView({ behavior: "smooth" });
            }}
          >
            <Bot size={17} />
            Codex 分析<span>{jobs || ""}</span>
          </button>
          <button
            onClick={async () => {
              try {
                setDeliveries(await api("/deliveries"));
              } catch (e: any) {
                notify(e.message);
              }
            }}
          >
            <Bell size={17} />
            通知记录
          </button>
        </nav>
        <div className="nav-label second">PREFERENCES</div>
        <nav className="main-nav">
          <button onClick={() => setSettings(true)}>
            <SlidersHorizontal size={17} />
            规则与接入
          </button>
          <button onClick={() => setSettings(true)}>
            <Settings2 size={17} />
            运行设置
          </button>
        </nav>
        <div className="sidebar-bottom">
          <div className="local-card">
            <ShieldCheck size={22} />
            <b>本机优先，边界清晰</b>
            <p>
              数据本机保存
              <br />
              Codex 使用脱敏快照
            </p>
            <span>
              <i />
              LOCAL WORKSPACE
            </span>
          </div>
          <div className="sidebar-foot">
            <span className="avatar">C</span>
            <div>
              <b>个人监控空间</b>
              <small>SignalDesk v0.1.0</small>
            </div>
            <button
              className="icon-button"
              aria-label="打开设置"
              onClick={() => setSettings(true)}
            >
              <Settings2 size={16} />
            </button>
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">
            工作台<span>/</span>
            <b>组合概览</b>
          </div>
          <div className="topbar-actions">
            <span className={`connection ${connected ? "" : "offline"}`}>
              {connected ? <Wifi size={13} /> : <WifiOff size={13} />}本机服务
              {connected ? "已连接" : "重连中"}
            </span>
            <button
              className="icon-button"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              aria-label="切换明暗主题"
            >
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <button
              className="icon-button"
              onClick={() => setReverse(!reverse)}
              title="切换涨跌配色"
              aria-label="切换涨跌配色"
            >
              <ArrowUpRight size={18} />
            </button>
            <button
              className="icon-button"
              onClick={() => setSettings(true)}
              aria-label="连接设置"
            >
              <Settings2 size={17} />
            </button>
          </div>
        </header>
        <div className="content">
          <section className="page-heading">
            <div>
              <div className="eyebrow">MARKET INTELLIGENCE</div>
              <h1>
                看清信号，保持纪律
                <span
                  className={`mode-pill ${data?.mode === "live" ? "live" : ""}`}
                >
                  <i />
                  {data?.mode === "live" ? "实盘只读" : "演示工作区"}
                </span>
              </h1>
              <p>聚焦技术结构与风险，让每一次关注都有依据。</p>
            </div>
            <div className="market-clock">
              <div>
                <Clock3 size={14} />
                <span>北京时间</span>
                <b>
                  {data?.now
                    ? new Date(data.now).toLocaleTimeString("zh-CN", {
                        timeZone: "Asia/Shanghai",
                        hour12: false,
                      })
                    : "—"}
                </b>
              </div>
              <small>
                NEW YORK ·{" "}
                {data?.now
                  ? new Date(data.now).toLocaleTimeString("en-US", {
                      timeZone: "America/New_York",
                      hour12: false,
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : "—"}
              </small>
            </div>
          </section>
          <div className="session-strip">
            <div className="session-pills">
              {[
                ["overnight", "夜盘"],
                ["pre", "盘前"],
                ["regular", "盘中"],
                ["post", "盘后"],
              ].map(([id, label]) => (
                <span
                  key={id}
                  className={data?.market.session === id ? "current" : ""}
                >
                  <i />
                  {label}
                </span>
              ))}
              <span className="session-label">
                {data?.market.label ?? "连接中"}
                {data?.market.early_close ? " · 提前收盘日" : ""}
              </span>
            </div>
            <span className="data-note">
              <span
                className={`status-dot ${data?.mode === "live" ? "" : "amber"}`}
              />
              {data?.mode === "live"
                ? data.detail
                : "合成历史与示例持仓 · 不代表真实行情"}
            </span>
          </div>
          {(error ||
            data?.status === "degraded" ||
            data?.status === "unconfigured") && (
            <div className="banner warning">
              <TriangleAlert size={16} />
              <span>{error || data?.detail}</span>
              <button onClick={() => setSettings(true)}>
                检查接入
                <ArrowRight size={13} />
              </button>
            </div>
          )}
          <section className="stat-grid">
            <article className="stat-card">
              <div className="stat-label">
                监控资产
                <span>
                  <Eye size={15} />
                </span>
              </div>
              <div className="stat-number">
                {data?.summary.count ?? "—"}
                <small>只</small>
              </div>
              <div className="stat-meta">
                <span className="tiny-dot teal" />
                长期与短线独立追踪
              </div>
              <div className="stat-bottom">
                <span>长期 {fmt(data?.summary.sleeve_weights.long)}%</span>
                <span>短线 {fmt(data?.summary.sleeve_weights.short)}%</span>
              </div>
              <div className="allocation-strip">
                <i
                  style={{
                    width: `${data?.summary.sleeve_weights.long ?? 0}%`,
                  }}
                />
                <i
                  style={{
                    width: `${data?.summary.sleeve_weights.short ?? 0}%`,
                  }}
                />
              </div>
            </article>
            <article className="stat-card">
              <div className="stat-label">
                技术结构均值
                <span>
                  <Gauge size={15} />
                </span>
              </div>
              <div className="stat-number">
                <Score value={data?.summary.average} />
                <small>/100</small>
              </div>
              <div className="stat-meta">三维因子融合，独立风险约束</div>
              <div className="stat-bottom">
                <span>
                  趋势 {fmt((data?.rules?.trend_weight ?? 0.4) * 100, 0)}%
                </span>
                <span>
                  动量 {fmt((data?.rules?.momentum_weight ?? 0.3) * 100, 0)}% ·
                  量价 {fmt((data?.rules?.volume_weight ?? 0.3) * 100, 0)}%
                </span>
              </div>
            </article>
            <article className="stat-card">
              <div className="stat-label">
                结构偏强
                <span>
                  <TrendingUp size={15} />
                </span>
              </div>
              <div className="stat-number positive">
                {data?.summary.strong ?? "—"}
                <small>只</small>
                <span className="small-tag positive">
                  ≥{data?.rules?.strong_threshold ?? 70}分
                </span>
              </div>
              <div className="stat-meta">关注共振，不把强势当作买入指令</div>
              <div className="stat-bottom">
                <span className="muted">结构偏弱</span>
                <b className="negative">{data?.summary.weak ?? "—"} 只</b>
              </div>
            </article>
            <article className="stat-card">
              <div className="stat-label">
                风险关注
                <span>
                  <ShieldCheck size={15} />
                </span>
              </div>
              <div className="stat-number amber-text">
                {data?.summary.risk_count ?? "—"}
                <small>项资产</small>
              </div>
              <div className="stat-meta">波动、流动性与数据质量独立显示</div>
              <div className="stat-bottom">
                <span>Codex 自动分析</span>
                <b>
                  {data?.channels.codex.daily_used ?? 0}
                  <em> / {data?.channels.codex.daily_limit ?? 24}</em>
                </b>
              </div>
            </article>
          </section>
          <div className="workspace-grid">
            <div className="workspace-primary">
              <section className="panel holdings-panel" id="holdings">
                <div className="panel-heading">
                  <div className="section-title">
                    <h2>持仓与观察</h2>
                    <span className="count-tag">{stocks.length}</span>
                  </div>
                  <div className="panel-controls">
                    <label className="search">
                      <Search size={13} />
                      <input
                        aria-label="搜索股票"
                        placeholder="搜索股票"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </label>
                    <button
                      className="icon-button"
                      onClick={() => setEditor(null)}
                      aria-label="添加观察股票"
                      title="添加观察股票"
                    >
                      <Plus size={17} />
                    </button>
                  </div>
                </div>
                <div className="table-toolbar">
                  <div className="segmented">
                    {[
                      ["all", "全部资产"],
                      ["long", "长期价值"],
                      ["short", "短线交易"],
                    ].map(([id, label]) => (
                      <button
                        key={id}
                        className={filter === id ? "selected" : ""}
                        onClick={() => setFilter(id)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <label className="sort-control">
                    <ListFilter size={13} />
                    <select
                      aria-label="资产排序"
                      value={sort}
                      onChange={(e) => setSort(e.target.value)}
                    >
                      <option value="default">默认排序</option>
                      <option value="score">结构评分</option>
                      <option value="risk">风险优先</option>
                    </select>
                  </label>
                </div>
                <div className="table-scroll">
                  <table className="holdings-table">
                    <thead>
                      <tr>
                        <th>资产</th>
                        <th>仓位策略</th>
                        <th>结构评分</th>
                        <th>维度分布</th>
                        <th className="align-right">最新价 / 涨跌</th>
                        <th>风险提示</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {stocks.map((s, index) => (
                        <tr
                          key={s.symbol}
                          className={selected === s.symbol ? "selected" : ""}
                          onClick={() => {
                            setSelected(s.symbol);
                            setTimeframe(
                              s.sleeves.length === 1 && s.sleeves[0] === "long"
                                ? "day"
                                : "15m",
                            );
                          }}
                        >
                          <td>
                            <div className="asset">
                              <span className={`asset-logo asset-${index % 5}`}>
                                {ticker(s.symbol).slice(0, 1)}
                              </span>
                              <div>
                                <b>{ticker(s.symbol)}</b>
                                <small>{s.name || "观察股票"}</small>
                              </div>
                            </div>
                          </td>
                          <td>
                            <div className="sleeves">
                              {s.sleeves.map((sl) => (
                                <span className={`sleeve ${sl}`} key={sl}>
                                  {labels[sl]}
                                </span>
                              ))}
                            </div>
                            <small className="weight">
                              {s.watch_only
                                ? "观察列表"
                                : s.reconciled
                                  ? `占比 ${fmt(s.weight_percent)}%`
                                  : "数量待核对"}
                            </small>
                          </td>
                          <td>
                            <Score
                              value={s.primary.score}
                              state={s.primary.state}
                            />
                            <small
                              className={`regime ${colorFor(s.primary.score, s.primary.state)}`}
                            >
                              {labels[s.primary.state] ?? "等待数据"}
                            </small>
                          </td>
                          <td>
                            <MiniBars stock={s} />
                          </td>
                          <td className="align-right">
                            <b
                              className="price"
                              title={time(s.quote.timestamp)}
                            >
                              {s.quote.last != null
                                ? "$" + fmt(s.quote.last, 2)
                                : "—"}
                            </b>
                            <small
                              className={
                                (s.change_percent ?? 0) >= 0
                                  ? "positive"
                                  : "negative"
                              }
                            >
                              {s.change_percent != null
                                ? (s.change_percent >= 0 ? "+" : "") +
                                  fmt(s.change_percent, 2) +
                                  "%"
                                : "待更新"}
                            </small>
                          </td>
                          <td>
                            <span
                              className={`risk-pill ${s.primary.risks?.length ? "risk" : ""}`}
                            >
                              {s.primary.risks?.length ? (
                                <TriangleAlert size={10} />
                              ) : (
                                <Check size={10} />
                              )}
                              <span>{s.primary.risks?.[0] ?? "结构正常"}</span>
                            </span>
                          </td>
                          <td>
                            <button
                              className="row-edit"
                              aria-label={`编辑${ticker(s.symbol)}分类`}
                              title="分类与关键价"
                              onClick={(e) => {
                                e.stopPropagation();
                                setEditor(s);
                              }}
                            >
                              <SlidersHorizontal size={13} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!stocks.length && (
                    <div className="empty-state">
                      <Search size={23} />
                      <b>
                        {data?.stocks.length
                          ? "没有匹配的资产"
                          : "尚未添加监控资产"}
                      </b>
                      <p>可以添加观察股票，或在设置中接入LongPort持仓。</p>
                      <button
                        className="button secondary"
                        onClick={() => setEditor(null)}
                      >
                        <Plus size={14} />
                        添加观察
                      </button>
                    </div>
                  )}
                </div>
                <div className="table-foot">
                  <CircleDot size={11} />
                  <span>评分仅描述技术结构，不代表上涨概率</span>
                  <span className="table-foot-right">FUSION 1.0.0</span>
                </div>
              </section>
              <section className="panel chart-panel">
                <div className="panel-heading chart-heading">
                  <div className="chart-title">
                    <span className="eyebrow">TECHNICAL STRUCTURE</span>
                    <h2>
                      {ticker(selected)}
                      <span>{stock?.name}</span>
                      <b>${fmt(stock?.quote.last, 2)}</b>
                    </h2>
                  </div>
                  <div className="chart-options">
                    <div className="segmented compact">
                      {["15m", "day"].map((tf) => (
                        <button
                          className={timeframe === tf ? "selected" : ""}
                          key={tf}
                          onClick={() => setTimeframe(tf)}
                        >
                          {labels[tf]}
                        </button>
                      ))}
                    </div>
                    <select
                      aria-label="图表交易时段"
                      value={session}
                      disabled={timeframe === "day"}
                      onChange={(e) => setSession(e.target.value)}
                    >
                      {["regular", "pre", "post", "overnight"].map((s) => (
                        <option key={s} value={s}>
                          {labels[s]}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="chart-subhead">
                  <div className="chart-legend">
                    <span className="legend-dot gold" />
                    {overlay === "MA"
                      ? "MA20"
                      : overlay === "BOLL"
                        ? "布林中轨"
                        : "VWAP"}
                    {overlay !== "VWAP" && (
                      <>
                        <span className="legend-dot purple" />
                        {overlay === "MA" ? "MA50" : "布林上下轨"}
                      </>
                    )}
                    <span className="muted">
                      {overlay === "VWAP" && timeframe === "day"
                        ? "VWAP仅适用于分时"
                        : "纽约时间 · 已确认K线"}
                    </span>
                  </div>
                  <div className="overlay-switch">
                    {["MA", "BOLL", "VWAP"].map((o) => (
                      <button
                        key={o}
                        className={overlay === o ? "active" : ""}
                        onClick={() => setOverlay(o)}
                      >
                        {o}
                      </button>
                    ))}
                  </div>
                </div>
                <Chart
                  detail={detail}
                  overlay={overlay}
                  theme={theme}
                  reverse={reverse}
                />
                <div className="chart-bottom">
                  <span>
                    <Clock3 size={12} />
                    数据截至 {time(summary?.as_of)}
                  </span>
                  <span>
                    {summary?.valid ? "有效窗口已完成" : "指标窗口未就绪"} ·
                    风险独立评估
                  </span>
                </div>
              </section>
              <div id="analysis">
                <AnalysisCard
                  stock={stock}
                  analysis={analysis}
                  onAnalyze={analyze}
                  preview={showPreview}
                />
              </div>
            </div>
            <aside className="workspace-secondary">
              <section className="panel signal-panel" id="signal-queue">
                <div className="panel-heading">
                  <div className="section-title">
                    <span className="live-pulse" />
                    <h2>信号队列</h2>
                  </div>
                  <span className="tiny-tag">{signals.length} EVENTS</span>
                </div>
                <div className="signal-tabs">
                  <button
                    className={signalFilter === "all" ? "selected" : ""}
                    onClick={() => setSignalFilter("all")}
                  >
                    全部事件
                  </button>
                  <button
                    className={signalFilter === "risk" ? "selected" : ""}
                    onClick={() => setSignalFilter("risk")}
                  >
                    风险优先
                  </button>
                  <Filter size={12} />
                </div>
                <div className="signal-list">
                  {signals.slice(0, 9).map((e) => (
                    <button
                      className={`signal-item ${e.severity}`}
                      key={e.id}
                      onClick={() => {
                        if (e.symbol !== "PORTFOLIO") setSelected(e.symbol);
                      }}
                    >
                      <span className="signal-icon">
                        {e.severity === "critical" ? (
                          <TriangleAlert size={15} />
                        ) : e.kind.includes("weak") ? (
                          <ArrowDownRight size={16} />
                        ) : (
                          <ArrowUpRight size={16} />
                        )}
                      </span>
                      <div>
                        <div className="signal-line">
                          <b>{ticker(e.symbol)}</b>
                          <small>{time(e.data_as_of)}</small>
                        </div>
                        <strong>{e.title}</strong>
                        <p>{e.message}</p>
                        <div className="signal-meta">
                          <span>{labels[e.timeframe] ?? e.timeframe}</span>
                          <span>{labels[e.sleeve] ?? e.sleeve}</span>
                          {e.score != null && <span>{fmt(e.score)}分</span>}
                          {e.historical && <em>历史回放</em>}
                        </div>
                      </div>
                    </button>
                  ))}
                  {!signals.length && (
                    <div className="empty-state">
                      <Activity size={25} />
                      <b>等待有效的共振事件</b>
                      <p>
                        只有结构变化才进入通知队列，持续满足条件不会重复提醒。
                      </p>
                    </div>
                  )}
                </div>
                <div className="signal-panel-foot">
                  <span className="tiny-dot teal" />
                  普通信号冷却{data?.rules?.cooldown_minutes ?? 30}分钟 ·
                  关键价实时监控
                </div>
              </section>
              <section className="panel fusion-panel">
                <div className="panel-heading">
                  <div className="section-title">
                    <Gauge size={16} />
                    <h3>融合透视</h3>
                  </div>
                  <span className="tiny-tag">{ticker(selected)}</span>
                </div>
                <div className="fusion-score">
                  <Score value={summary?.score} state={summary?.state} large />
                  <span
                    className={`fusion-state ${colorFor(summary?.score, summary?.state)}`}
                  >
                    {labels[summary?.state ?? "unavailable"]}
                  </span>
                </div>
                {Object.entries(dimensionNames).map(([key, label]) => (
                  <div className="dimension" key={key}>
                    <div>
                      <span>
                        <i style={{ background: dimensionColors[key] }} />
                        {label}
                      </span>
                      <b>
                        {fmt(summary?.dimensions[key])}
                        <small>
                          {" "}
                          /{" "}
                          {fmt(
                            (summary?.weights?.[key] ??
                              (key === "trend" ? 0.4 : 0.3)) * 100,
                            0,
                          )}
                          %
                        </small>
                      </b>
                    </div>
                    <div className="dimension-track">
                      <i
                        style={{
                          width: `${summary?.dimensions[key] ?? 0}%`,
                          background: dimensionColors[key],
                        }}
                      />
                    </div>
                  </div>
                ))}
                <div className="risk-section">
                  <h4>
                    <ShieldCheck size={13} />
                    独立风险检查
                  </h4>
                  {summary?.risks.length ? (
                    summary.risks.map((r) => (
                      <span className="risk-line" key={r}>
                        <TriangleAlert size={12} />
                        {r}
                      </span>
                    ))
                  ) : (
                    <span className="risk-line clear">
                      <Check size={12} />
                      当前规则未发现额外风险标记
                    </span>
                  )}
                  <small>风险不会被高分抵消</small>
                </div>
                <details className="operator-details">
                  <summary>
                    查看指标与算子结果
                    <ChevronDown size={12} />
                  </summary>
                  <dl>
                    {[
                      ["RSI14", "rsi"],
                      ["ATR14", "atr"],
                      ["RVOL", "rvol"],
                      ["Z-score20", "zscore20"],
                      ["时序排名20", "rank20"],
                      ["量价相关20", "corr20"],
                    ].map(([label, key]) => (
                      <div key={key}>
                        <dt>{label}</dt>
                        <dd>{fmt(summary?.indicators[key], 3)}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
              </section>
              <section className="panel channels-panel">
                <div className="section-title">
                  <CircleDot size={15} />
                  <h3>连接状态</h3>
                </div>
                {[
                  [
                    "LongPort",
                    data?.mode === "live" ? data.status : "demo",
                    data?.mode === "live" ? "官方只读行情" : "合成行情",
                  ],
                  [
                    "Codex",
                    data?.channels.codex.status ?? "unavailable",
                    data?.channels.codex.model ?? "未发现CLI",
                  ],
                  [
                    "QQ 官方机器人",
                    data?.channels.qq.status ?? "disabled",
                    data?.channels.qq.detail ?? "未配置",
                  ],
                ].map(([name, status, desc]) => (
                  <div className="channel-row" key={name}>
                    <span
                      className={`channel-dot ${["live", "ready", "delivered"].includes(status) ? "ok" : status === "demo" ? "demo" : ""}`}
                    />
                    <div>
                      <b>{name}</b>
                      <small>{desc}</small>
                    </div>
                    <span className="channel-state">{status}</span>
                  </div>
                ))}
                <button
                  className="text-button"
                  onClick={() => setSettings(true)}
                >
                  管理接入与通知
                  <ArrowRight size={13} />
                </button>
              </section>
            </aside>
          </div>
          <footer className="page-footer">
            <span>
              <LockKeyhole size={11} />
              本机工作区 · 原始数据不上传
            </span>
            <span>规则可追溯 · 只读监控 · 判断由 Codex 形成</span>
            <span>WINDOWS / LOCAL FIRST</span>
          </footer>
        </div>
      </main>
      {settings && (
        <SettingsPanel onClose={closeSettings} notify={notify} first={first} />
      )}
      {editor !== undefined && (
        <AllocationEditor
          stock={editor}
          onClose={() => setEditor(undefined)}
          onSaved={refresh}
          notify={notify}
        />
      )}
      {preview && (
        <div className="modal-shade">
          <section
            className="small-modal preview-modal"
            role="dialog"
            aria-label="Codex脱敏发送预览"
          >
            <header className="modal-header">
              <div>
                <span className="eyebrow">OUTBOUND SNAPSHOT</span>
                <h2>Codex 脱敏发送预览</h2>
              </div>
              <button
                className="icon-button"
                onClick={() => setPreview(null)}
                aria-label="关闭预览"
              >
                <X size={18} />
              </button>
            </header>
            <p className="notice">
              以下内容会交给 Codex；不包含账户标识、股数、金额、成本或流水。
            </p>
            <pre>{JSON.stringify(preview, null, 2)}</pre>
            <footer className="modal-footer">
              <span>当前股票 {ticker(selected)}</span>
              <button
                className="button primary"
                onClick={() => {
                  setPreview(null);
                  analyze();
                }}
              >
                交给 Codex 分析
                <ArrowRight size={14} />
              </button>
            </footer>
          </section>
        </div>
      )}
      {deliveries && (
        <div className="modal-shade">
          <section
            className="small-modal"
            role="dialog"
            aria-label="通知投递记录"
          >
            <header className="modal-header">
              <h2>通知投递记录</h2>
              <button
                className="icon-button"
                onClick={() => setDeliveries(null)}
                aria-label="关闭通知记录"
              >
                <X size={18} />
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
                  <Bell size={24} />
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
          <CircleDot size={16} />
          <span>{toast}</span>
          <button onClick={() => setToast("")} aria-label="关闭提示">
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}
