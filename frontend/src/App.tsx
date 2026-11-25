import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  Bell,
  Bot,
  ChevronDown,
  CircleDot,
  Clock3,
  Monitor,
  Moon,
  MoreHorizontal,
  Plus,
  Settings2,
  SlidersHorizontal,
  Star,
  Sun,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-react";
import Chart from "./Chart";
import { ErrorBoundary } from "./ErrorBoundary";
import { MacroStripWithGuide } from "./GuidePopover";
import { MacroRegimeModal, MacroRegimeTrigger } from "./MacroRegimePanel";
import SettingsPanel from "./Settings";
import StockInspector, { type InspectorTab } from "./StockInspector";
import WatchlistRail from "./WatchlistRail";
import {
  api,
  fmt,
  isValidDashboard,
  ticker,
  type AgentProviderId,
  type Dashboard,
  type Detail,
  type EvalMode,
  type LiveEvaluation,
  type ResolvedTheme,
  type Stock,
  type ThemeMode,
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
    (presetStop ?? stock?.long_plan?.stop)?.toString() ?? "",
  );
  const [target, setTarget] = useState(
    (presetTarget ?? stock?.long_plan?.target)?.toString() ?? "",
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

const THEME_OPTIONS: {
  id: ThemeMode;
  label: string;
  title: string;
}[] = [
  { id: "light", label: "浅色", title: "切换为浅色外观" },
  { id: "dark", label: "深色", title: "切换为深色外观" },
  { id: "system", label: "跟随系统", title: "跟随操作系统深浅外观" },
];

function readInitialThemeMode(): ThemeMode {
  const saved = localStorage.getItem("sd-theme-mode");
  if (saved === "light" || saved === "dark" || saved === "system") {
    return saved;
  }
  const legacy = localStorage.getItem("sd-theme-v2");
  if (legacy === "light" || legacy === "dark") {
    return legacy;
  }
  return "light";
}

/** 顶栏外置三态外观切换分段控件（浅色 / 深色 / 跟随系统） */
function ThemeModeSwitch({
  mode,
  resolvedTheme,
  onChange,
}: {
  mode: ThemeMode;
  resolvedTheme: ResolvedTheme;
  onChange: (next: ThemeMode) => void;
}) {
  const btnRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    let nextIdx: number | null = null;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      nextIdx = (index + 1) % THEME_OPTIONS.length;
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      nextIdx = (index - 1 + THEME_OPTIONS.length) % THEME_OPTIONS.length;
    } else if (e.key === "Home") {
      nextIdx = 0;
    } else if (e.key === "End") {
      nextIdx = THEME_OPTIONS.length - 1;
    }
    if (nextIdx !== null) {
      e.preventDefault();
      onChange(THEME_OPTIONS[nextIdx].id);
      btnRefs.current[nextIdx]?.focus();
    }
  };

  return (
    <div
      className="theme-seg-group"
      role="radiogroup"
      aria-label="外观主题模式"
    >
      {THEME_OPTIONS.map((opt, idx) => {
        const active = mode === opt.id;
        const tip =
          opt.id === "system"
            ? `${opt.title}（当前：${resolvedTheme === "dark" ? "深色" : "浅色"}）`
            : opt.title;
        return (
          <button
            key={opt.id}
            ref={(el) => {
              btnRefs.current[idx] = el;
            }}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={tip}
            title={tip}
            tabIndex={active ? 0 : -1}
            className={`theme-seg-btn ${active ? "active" : ""}`}
            onClick={() => onChange(opt.id)}
            onKeyDown={(e) => handleKeyDown(idx, e)}
          >
            {opt.id === "light" && <Sun size={14} aria-hidden="true" />}
            {opt.id === "dark" && <Moon size={14} aria-hidden="true" />}
            {opt.id === "system" && <Monitor size={14} aria-hidden="true" />}
          </button>
        );
      })}
    </div>
  );
}

/** 顶栏右侧「更多」二级菜单：仅保留无重复的低频偏好与辅助项（双时钟、涨跌配色、通知记录） */
function TopbarMoreMenu({
  bjClock,
  nyClock,
  reverse,
  onToggleReverse,
  onOpenDeliveries,
}: {
  bjClock: string;
  nyClock: string;
  reverse: boolean;
  onToggleReverse: () => void;
  onOpenDeliveries: () => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="topbar-menu-wrap" ref={wrapRef}>
      <button
        type="button"
        className={`top-btn top-more-btn ${open ? "active" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        title="双时钟、涨跌配色与通知记录"
      >
        <MoreHorizontal size={16} aria-hidden="true" />
        <span>更多</span>
        <ChevronDown size={13} aria-hidden="true" />
      </button>

      {open && (
        <div className="topbar-dropdown" role="menu" aria-label="顶栏偏好与辅助菜单">
          <div className="topbar-dd-status">
            <div className="topbar-dd-clocks">
              <Clock3 size={13} aria-hidden="true" />
              <span>北京 {bjClock}</span>
              <span className="sep">/</span>
              <span>纽约 {nyClock}</span>
            </div>
          </div>

          <div className="topbar-dd-sep" />

          <button
            type="button"
            role="menuitem"
            className="topbar-dd-item"
            onClick={() => {
              onToggleReverse();
              setOpen(false);
            }}
          >
            <span>涨跌配色</span>
            <em>{reverse ? "红涨绿跌" : "绿涨红跌"}</em>
          </button>

          <button
            type="button"
            role="menuitem"
            className="topbar-dd-item"
            onClick={() => {
              setOpen(false);
              onOpenDeliveries();
            }}
          >
            <span className="topbar-dd-ico">
              <Bell size={14} aria-hidden="true" />
              通知投递记录
            </span>
            <em>查看</em>
          </button>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const [themeMode, setThemeMode] = useState<ThemeMode>(readInitialThemeMode);
  const [systemDark, setSystemDark] = useState<boolean>(() =>
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
      : false,
  );
  const resolvedTheme: ResolvedTheme =
    themeMode === "system" ? (systemDark ? "dark" : "light") : themeMode;
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
  const [macroOpen, setMacroOpen] = useState(false);
  const [evalMode, setEvalMode] = useState<EvalMode>("confirmed");
  const [liveEval, setLiveEval] = useState<LiveEvaluation | null>(null);
  const [liveEvalBusy, setLiveEvalBusy] = useState(false);
  const [verdictExpanded, setVerdictExpanded] = useState(false);
  const lastLiveEvalAtRef = useRef<number>(0);

  useEffect(() => {
    setVerdictExpanded(false);
  }, [selected]);

  const notify = (s: string) => setToast(s);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 6500);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    if (
      typeof window === "undefined" ||
      typeof window.matchMedia !== "function"
    ) {
      return;
    }
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    setSystemDark(mq.matches);
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    }
    mq.addListener(onChange);
    return () => mq.removeListener(onChange);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.dataset.themeMode = themeMode;
    document.documentElement.style.colorScheme = resolvedTheme;
    localStorage.setItem("sd-theme-mode", themeMode);
    localStorage.setItem("sd-theme-v2", resolvedTheme);
    const metaTheme = document.querySelector<HTMLMetaElement>(
      'meta[name="theme-color"]',
    );
    if (metaTheme) {
      metaTheme.content = resolvedTheme === "dark" ? "#0b0f14" : "#f8fafc";
    }
  }, [themeMode, resolvedTheme]);

  useEffect(() => {
    document.documentElement.dataset.reverse = String(reverse);
    localStorage.setItem("sd-reverse", String(reverse));
  }, [reverse]);

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    async function connect() {
      if (socket) {
        try {
          socket.onclose = null;
          socket.onerror = null;
          socket.onmessage = null;
          socket.close();
        } catch {
          // 忽略关闭旧连接异常
        }
        socket = undefined;
      }
      try {
        const snapshot = await api<Dashboard>("/bootstrap");
        if (disposed) return;
        if (!isValidDashboard(snapshot)) {
          throw new Error("本机看板返回数据不完整，正在重试");
        }
        setData(snapshot);
        setError("");
        if (!localStorage.getItem("sd-onboarded")) setSettings(true);
        const ws = new WebSocket(
          `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/stream`,
        );
        socket = ws;
        ws.onopen = () => {
          if (!disposed) setConnected(true);
        };
        ws.onmessage = (e) => {
          if (disposed) return;
          try {
            const parsed = JSON.parse(e.data);
            if (isValidDashboard(parsed)) {
              setData(parsed);
            }
          } catch {
            // 忽略异常帧，保留上一次有效快照避免白屏
          }
        };
        ws.onclose = () => {
          if (!disposed && socket === ws) {
            setConnected(false);
            clearTimeout(retry);
            retry = setTimeout(connect, 3000);
          }
        };
        ws.onerror = () => {
          try {
            ws.close();
          } catch {
            // 忽略关闭错误
          }
        };
      } catch (e: any) {
        if (!disposed) {
          setError(e?.message || "正在重新连接本地服务");
          clearTimeout(retry);
          retry = setTimeout(connect, 3000);
        }
      }
    }
    connect();
    return () => {
      disposed = true;
      clearTimeout(retry);
      if (socket) {
        socket.onclose = null;
        socket.onerror = null;
        socket.onmessage = null;
        socket.close();
      }
    };
  }, []);

  useEffect(() => {
    if (
      data?.stocks?.length &&
      !data.stocks.some((s) => s.symbol === selected)
    ) {
      setSelected(data.stocks[0].symbol);
    }
  }, [data?.stocks, selected]);

  const stock = data?.stocks?.find((s) => s.symbol === selected) ?? null;

  useEffect(() => {
    let disposed = false;
    setLiveEval(null);
    async function load() {
      if (!stock) return;
      try {
        const value = await api<Detail>(`/stock/${selected}`);
        if (!disposed && value && Array.isArray(value.rows)) {
          setDetail(value);
          setLiveEval(value.live_eval ?? null);
          lastLiveEvalAtRef.current = Date.now();
        }
      } catch {
        if (!disposed) {
          setDetail(null);
          setLiveEval(null);
        }
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
    stock?.primary?.as_of,
    stock?.primary?.score,
    stock?.primary?.rule_version,
    stock?.primary?.state,
    stock?.long_plan?.stop,
    stock?.long_plan?.target,
  ]);

  const refreshLiveEval = useCallback(async () => {
    if (!stock || data?.mode !== "live") return;
    setLiveEvalBusy(true);
    try {
      const value = await api<LiveEvaluation>(`/stock/${selected}/live-eval`);
      setLiveEval(value ?? null);
      lastLiveEvalAtRef.current = Date.now();
    } catch {
      // 保留上一次有效试算结果
    } finally {
      setLiveEvalBusy(false);
    }
  }, [selected, data?.mode, Boolean(stock)]);

  const activeQuoteSig = `${stock?.quote?.last ?? ""}:${stock?.quote?.high ?? ""}:${stock?.quote?.low ?? ""}:${stock?.extended_hours?.price ?? ""}`;
  useEffect(() => {
    if (evalMode !== "live" || data?.mode !== "live" || !stock) return;
    const elapsed = Date.now() - lastLiveEvalAtRef.current;
    const wait = elapsed >= 4000 ? 300 : 4000 - elapsed;
    const timer = setTimeout(() => {
      refreshLiveEval();
    }, wait);
    return () => clearTimeout(timer);
  }, [evalMode, data?.mode, selected, activeQuoteSig, refreshLiveEval]);

  const [selectedAgent, setSelectedAgent] = useState<AgentProviderId | null>(
    null,
  );
  const effectiveAgent = useMemo<AgentProviderId>(() => {
    if (selectedAgent) return selectedAgent;
    const hub = data?.channels?.agents;
    const def: AgentProviderId =
      hub?.default_agent === "antigravity" ? "antigravity" : "codex";
    const providers = hub?.providers;
    if (providers) {
      if (providers[def]?.configured) return def;
      const alt: AgentProviderId =
        def === "antigravity" ? "codex" : "antigravity";
      if (providers[alt]?.configured) return alt;
    }
    return def;
  }, [selectedAgent, data?.channels]);

  const stockAnalyses = useMemo(
    () =>
      (data?.analyses ?? []).filter(
        (a) =>
          a.symbol === selected &&
          a.source === data?.mode &&
          a.scope === "long_value",
      ),
    [data?.analyses, selected, data?.mode],
  );
  const analysis = useMemo(
    () => stockAnalyses.find((a) => (a.agent ?? "codex") === effectiveAgent),
    [stockAnalyses, effectiveAgent],
  );
  const currentDetail =
    stock && detail?.stock?.symbol === selected && detail.mode === data?.mode
      ? detail
      : null;
  const activeLiveEval =
    currentDetail && liveEval ? liveEval : currentDetail?.live_eval ?? null;
  const isLiveEvalActive = Boolean(
    data?.mode === "live" && evalMode === "live" && activeLiveEval?.available,
  );

  // 单一真相源派生：开启「最新行情试算」时，整页中栏结论、K线参考线/波浪与右侧卡片无缝联动，零污染后端收盘确认基线
  const effectiveStock = useMemo<Stock | null>(() => {
    if (!stock) return null;
    if (!isLiveEvalActive || !activeLiveEval) return stock;
    return {
      ...stock,
      primary: activeLiveEval.summary ?? stock.primary,
      forecast: activeLiveEval.forecast ?? stock.forecast,
      wave_trend: activeLiveEval.wave_trend ?? stock.wave_trend,
      fund_metrics: activeLiveEval.fund_metrics ?? stock.fund_metrics,
      academic_factors: activeLiveEval.academic_factors ?? stock.academic_factors,
      verdict: activeLiveEval.verdict ?? stock.verdict,
      long_plan: activeLiveEval.long_plan ?? stock.long_plan,
    };
  }, [stock, isLiveEvalActive, activeLiveEval]);

  const effectiveDetail = useMemo<Detail | null>(() => {
    if (!currentDetail) return null;
    if (!isLiveEvalActive || !effectiveStock) return currentDetail;
    return {
      ...currentDetail,
      stock: effectiveStock,
      summary: activeLiveEval?.summary ?? currentDetail.summary,
    };
  }, [currentDetail, isLiveEvalActive, effectiveStock, activeLiveEval]);

  const summary = effectiveDetail?.summary ?? null;
  const curve = data?.curve;

  async function refresh() {
    try {
      const next = await api<Dashboard>("/dashboard");
      if (isValidDashboard(next)) {
        setData(next);
      }
    } catch (e: any) {
      notify(e?.message || "刷新数据失败");
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

  async function analyze(agentOverride?: AgentProviderId) {
    if (!stock) return;
    const targetAgent = agentOverride ?? effectiveAgent;
    setSelectedAgent(targetAgent);
    setInspectorTab("codex");
    const agentName =
      targetAgent === "antigravity" ? "Antigravity CLI (ACP)" : "Codex CLI";
    try {
      await api(`/analysis/${stock.symbol}`, {
        method: "POST",
        body: JSON.stringify({ agent: targetAgent }),
      });
      notify(`已手动提交 ${agentName} 复核任务；行情监控继续运行`);
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

  const verdict = effectiveStock?.verdict ?? stock?.verdict;
  const activeForecast = effectiveStock?.forecast ?? stock?.forecast;
  const canDeleteSelected = Boolean(
    stock && stock.broker_quantity === 0 && !stock.in_watchlist,
  );

  return (
    <div className="desk-shell">
      <header className="desk-topbar">
        <div className="topbar-left">
          <div className="brand-mark">
            <span className="brand-badge">
              <Activity size={17} />
            </span>
            <b>SignalDesk</b>
          </div>
          <button
            type="button"
            className={`status-pill-merged ${
              !connected
                ? "offline"
                : data?.mode === "live"
                  ? "live"
                  : "demo"
            }`}
            onClick={() => setSettings(true)}
            title={`北京 ${bjClock} / 纽约 ${nyClock}${data?.detail ? ` · ${data.detail}` : ""}（点击修改接入设置）`}
          >
            <span
              className={`session-dot ${
                !connected
                  ? "offline"
                  : data?.market?.session === "regular"
                    ? "open"
                    : ""
              }`}
            />
            <span>
              {!connected
                ? "重连中"
                : data?.mode === "live"
                  ? `实盘 · ${data?.market?.label ?? "同步中"}`
                  : "演示工作区"}
              {connected && data?.market?.early_close ? " · 提前收" : ""}
            </span>
          </button>
        </div>

        <div className="topbar-macro-group">
          <MacroRegimeTrigger
            macro={data?.macro}
            open={macroOpen}
            onOpen={() => setMacroOpen(true)}
          />
          <MacroStripWithGuide
            curve={curve}
            gold={data?.gold}
            onOpenMacroPanel={() => setMacroOpen(true)}
          />
        </div>

        <div className="topbar-right">
          <ThemeModeSwitch
            mode={themeMode}
            resolvedTheme={resolvedTheme}
            onChange={setThemeMode}
          />
          <TopbarMoreMenu
            bjClock={bjClock}
            nyClock={nyClock}
            reverse={reverse}
            onToggleReverse={() => setReverse(!reverse)}
            onOpenDeliveries={async () => {
              try {
                setDeliveries(await api("/deliveries"));
              } catch (e: any) {
                notify(e.message);
              }
            }}
          />
          <button
            type="button"
            className="button primary top-settings-btn"
            onClick={() => setSettings(true)}
          >
            <Settings2 size={15} aria-hidden="true" />
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
        <ErrorBoundary compact title="左侧行情列表暂时异常">
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
        </ErrorBoundary>

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
                      size={18}
                      fill={stock.favorite ? "currentColor" : "none"}
                    />
                  </button>
                  <div className="hero-identity">
                    <div className="hero-title-line">
                      <h1>{ticker(stock.symbol)}</h1>
                      <span className="hero-name" title={stock.name || "美股标的"}>
                        {stock.name || "美股标的"}
                      </span>
                      {stock.instrument?.is_fund && (
                        <span
                          className={`tag-chip asset-type ${
                            stock.instrument.is_leveraged ? "leveraged" : "etf"
                          }`}
                          title={
                            [
                              stock.instrument.benchmark,
                              stock.instrument.risk_notice,
                            ]
                              .filter(Boolean)
                              .join(" · ")
                          }
                        >
                          {stock.instrument.type_label}
                        </span>
                      )}
                      {stock.broker_quantity > 0 && (
                        <span
                          className="tag-chip held"
                          title={
                            stock.weight_percent != null
                              ? `持仓 ${fmt(stock.broker_quantity, 0)} 股 · 仓位占比 ${fmt(stock.weight_percent, 1)}%`
                              : `持仓 ${fmt(stock.broker_quantity, 0)} 股`
                          }
                        >
                          持仓 {fmt(stock.broker_quantity, 0)}
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
                        const hiddenGroups = new Set([
                          "all",
                          "us",
                          "全部",
                          "全部自选",
                          "all stocks",
                          "美股",
                        ]);
                        const groups = (stock.watchlist_groups ?? []).filter(
                          (g) =>
                            typeof g === "string" &&
                            !hiddenGroups.has(g.trim().toLowerCase()),
                        );
                        const hasExtraBadge =
                          stock.broker_quantity > 0 ||
                          stock.pnl_percent != null ||
                          Boolean(stock.instrument?.is_fund);
                        if (hasExtraBadge || !groups.length) return null;
                        const shown = groups.slice(0, 1);
                        const hiddenCount = groups.length - shown.length;
                        return (
                          <>
                            {shown.map((g) => (
                              <span
                                className="tag-chip group"
                                key={g}
                                title={groups.join(" · ")}
                              >
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
                      {stock.quote?.last != null
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
                      <SlidersHorizontal size={14} />
                      计划
                    </button>
                    <button
                      type="button"
                      className="button primary"
                      onClick={() => setInspectorTab("codex")}
                      title="打开本地官方 Agent 长期复核面板（Antigravity ACP / Codex）"
                    >
                      <Bot size={14} />
                      AI 复核
                    </button>
                    {canDeleteSelected && (
                      <button
                        type="button"
                        className="icon-button"
                        onClick={() => removeLocalWatch(stock)}
                        title="移出本地观察"
                        aria-label="移出本地观察"
                      >
                        <Trash2 size={15} />
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {verdict && (
                <div
                  className={`verdict-banner compact tone-${verdict.tone} ${verdictExpanded ? "expanded" : ""}`}
                >
                  <div className="verdict-main">
                    <div className="verdict-badges">
                      <span
                        className={`verdict-badge tone-${verdict.tone}`}
                        title={verdict.action_meaning || verdict.headline}
                      >
                        {verdict.action}
                      </span>
                      {activeForecast?.rating?.available && (
                        <span
                          className={`verdict-badge forecast-rating-badge tone-${activeForecast.rating.tone}`}
                          title={activeForecast.rating.summary}
                        >
                          {activeForecast.rating.label}{" "}
                          {fmt(activeForecast.rating.score, 0)}分
                        </span>
                      )}
                      {isLiveEvalActive && (
                        <span
                          className="verdict-live-tag"
                          title="当前结论、点位、评级与波浪已按最新未收盘行情临时试算预览"
                        >
                          实时试算
                        </span>
                      )}
                    </div>
                    <p
                      className="verdict-headline single-line"
                      title={`${verdict.headline} 下一步：${verdict.next_step}`}
                    >
                      {verdict.headline}
                    </p>
                    <button
                      type="button"
                      className={`verdict-expand-btn ${verdictExpanded ? "open" : ""}`}
                      onClick={() => setVerdictExpanded((v) => !v)}
                      aria-expanded={verdictExpanded}
                      title="展开或收起完整研判建议与三维度支柱详情"
                    >
                      <span>{verdictExpanded ? "收起" : "详情"}</span>
                      <ChevronDown size={13} />
                    </button>
                  </div>

                  {verdictExpanded && (
                    <div className="verdict-drawer">
                      <p className="verdict-headline">{verdict.headline}</p>
                      <p className="verdict-next">
                        下一步：{verdict.next_step}
                      </p>
                      <div className="verdict-pillars">
                        {(verdict.pillars ?? []).map((p) => (
                          <div className="pillar-box" key={p.key}>
                            <div className="pillar-top">
                              <span>{p.label}</span>
                              <b className={`tone-text-${p.tone}`}>{p.status}</b>
                            </div>
                            <small>{p.detail}</small>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {activeForecast?.levels?.available && (
                    <div className="forecast-strip">
                      {activeForecast.levels.breakout_level != null && (
                        <div
                          className="forecast-strip-item"
                          title={
                            activeForecast.levels.breakout_anchor ||
                            "综合波浪前高与筹码密集区上沿测算的主要突破位"
                          }
                        >
                          <span>
                            {activeForecast.levels.breakout_confluence
                              ? "共振突破"
                              : "突破位"}
                          </span>
                          <strong className="accent-val">
                            ${fmt(activeForecast.levels.breakout_level, 2)}
                          </strong>
                        </div>
                      )}
                      {activeForecast.levels.defense_level != null && (
                        <div
                          className="forecast-strip-item"
                          title={
                            activeForecast.levels.defense_anchor ||
                            "综合筹码价值区下沿、波浪前低与移动保护位测算的主要防守位"
                          }
                        >
                          <span>
                            {activeForecast.levels.defense_confluence
                              ? "共振防守"
                              : "防守位"}
                          </span>
                          <strong className="down">
                            ${fmt(activeForecast.levels.defense_level, 2)}
                          </strong>
                        </div>
                      )}
                      <div className="forecast-strip-item">
                        <span>买区</span>
                        <strong className="up">
                          ${fmt(activeForecast.levels.buy_low, 2)}–$
                          {fmt(activeForecast.levels.buy_high, 2)}
                        </strong>
                      </div>
                      {activeForecast.volume_profile?.available &&
                        activeForecast.volume_profile.poc != null && (
                          <div
                            className="forecast-strip-item forecast-strip-chip"
                            title={`近${activeForecast.volume_profile.window_days}日筹码分布 · 70%价值区 $${fmt(activeForecast.volume_profile.val, 2)}–$${fmt(activeForecast.volume_profile.vah, 2)} · ${activeForecast.volume_profile.position_label}`}
                          >
                            <span>筹码峰</span>
                            <strong className="amber-text">
                              ${fmt(activeForecast.volume_profile.poc, 2)}
                              {activeForecast.volume_profile.profit_ratio_pct !=
                                null &&
                                ` (${fmt(activeForecast.volume_profile.profit_ratio_pct, 0)}%获利)`}
                            </strong>
                          </div>
                        )}
                      <div className="forecast-strip-item">
                        <span>盈亏比</span>
                        <strong>
                          {fmt(activeForecast.levels.risk_reward_ratio, 2)}:1
                        </strong>
                      </div>
                      {(activeForecast.levels.defense_level ??
                        activeForecast.levels.stop_loss) != null &&
                        (activeForecast.levels.breakout_level ??
                          activeForecast.levels.sell_low) != null && (
                          <button
                            type="button"
                            className="text-btn forecast-strip-apply"
                            title="将主要防守位与参考卖点预填到个人计划价"
                            onClick={() =>
                              setEditor({
                                stock,
                                presetStop:
                                  activeForecast.levels.defense_level ??
                                  activeForecast.levels.stop_loss,
                                presetTarget:
                                  activeForecast.levels.sell_low ??
                                  activeForecast.levels.breakout_level,
                              })
                            }
                          >
                            采纳计划价
                          </button>
                        )}
                    </div>
                  )}
                  {stock.extended_hours?.available &&
                    stock.extended_hours.is_live_session &&
                    stock.extended_hours.price != null && (
                      <div
                        className={`ext-hours-strip level-${stock.extended_hours.alert_level}`}
                        title={[
                          stock.extended_hours.headline,
                          ...stock.extended_hours.triggers.slice(1),
                          stock.extended_hours.disclaimer,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      >
                        <div className="ext-strip-main">
                          <span className="ext-session-pill">
                            <i />
                            {stock.extended_hours.active_label}
                          </span>
                          <strong className="ext-strip-price">
                            ${fmt(stock.extended_hours.price, 2)}
                          </strong>
                          {stock.extended_hours.gap_pct != null && (
                            <span
                              className={`ext-strip-gap ${
                                stock.extended_hours.gap_pct >= 0
                                  ? "quote-up"
                                  : "quote-down"
                              }`}
                            >
                              {stock.extended_hours.gap_pct >= 0 ? "+" : ""}
                              {fmt(stock.extended_hours.gap_pct, 2)}%
                            </span>
                          )}
                          {stock.extended_hours.low != null &&
                            stock.extended_hours.high != null && (
                              <span className="ext-strip-meta">
                                区间 ${fmt(stock.extended_hours.low, 2)}–$
                                {fmt(stock.extended_hours.high, 2)}
                              </span>
                            )}
                          <span
                            className={`ext-strip-liq ${
                              stock.extended_hours.liquid ? "ok" : "thin"
                            }`}
                          >
                            额 {stock.extended_hours.turnover_text} ·{" "}
                            {stock.extended_hours.liquidity_label}
                          </span>
                          {stock.extended_hours.active_session === "pre" &&
                            stock.extended_hours.sessions?.overnight?.is_fresh && (
                              <span className="ext-strip-prev-sess">
                                夜盘 $
                                {fmt(
                                  stock.extended_hours.sessions.overnight.price,
                                  2,
                                )}
                                {stock.extended_hours.sessions.overnight
                                  .gap_pct != null
                                  ? ` (${
                                      stock.extended_hours.sessions.overnight
                                        .gap_pct >= 0
                                        ? "+"
                                        : ""
                                    }${fmt(
                                      stock.extended_hours.sessions.overnight
                                        .gap_pct,
                                      1,
                                    )}%)`
                                  : ""}
                              </span>
                            )}
                        </div>
                        {stock.extended_hours.triggers.length > 0 && (
                          <button
                            type="button"
                            className={`ext-strip-alert level-${stock.extended_hours.alert_level}`}
                            onClick={() => setInspectorTab("summary")}
                            title={stock.extended_hours.triggers.join("；")}
                          >
                            {stock.extended_hours.liquid
                              ? `${stock.extended_hours.active_label}异动 · ${stock.extended_hours.triggers.length}条`
                              : "偏薄参考"}
                          </button>
                        )}
                      </div>
                    )}
                </div>
              )}

              <div className="chart-panel-card">
                <ErrorBoundary
                  compact
                  title="K 线图表暂时异常"
                  resetKey={`${selected}:${data?.mode ?? ""}`}
                >
                  <Chart
                    detail={effectiveDetail}
                    liveQuote={stock?.quote}
                    marketSession={data?.market?.session}
                    evalMode={isLiveEvalActive ? "live" : "confirmed"}
                    liveEvalRow={isLiveEvalActive ? (activeLiveEval?.live_row ?? null) : null}
                    theme={resolvedTheme}
                    reverse={reverse}
                  />
                </ErrorBoundary>
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

        <ErrorBoundary
          compact
          title="右侧研判面板暂时异常"
          resetKey={`${selected}:${inspectorTab}`}
        >
          <StockInspector
            tab={inspectorTab}
            onTabChange={setInspectorTab}
            stock={effectiveStock}
            summary={summary}
            evalMode={evalMode}
            liveEval={activeLiveEval}
            liveEvalBusy={liveEvalBusy}
            onEvalModeChange={(nextMode) => {
              setEvalMode(nextMode);
              if (nextMode === "live") {
                refreshLiveEval();
              }
            }}
            onRefreshLiveEval={refreshLiveEval}
            activeAgent={effectiveAgent}
            onSelectAgent={setSelectedAgent}
            analysis={analysis}
            stockAnalyses={stockAnalyses}
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
                presetTarget: sellLow ?? undefined,
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
        </ErrorBoundary>
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
            aria-label="Agent脱敏发送预览"
          >
            <header className="modal-header">
              <div>
                <h2>Agent 脱敏发送预览</h2>
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
              以下白名单脱敏内容将通过官方本地协议发送给当前所选 Agent（
              {effectiveAgent === "antigravity"
                ? "Antigravity CLI · ACP"
                : "Codex CLI · exec"}
              ）；不包含账户标识、股数、金额、成本或成交流水。
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
                  analyze(effectiveAgent);
                }}
              >
                {effectiveAgent === "antigravity"
                  ? "立即用 Antigravity 复核"
                  : "立即用 Codex 复核"}
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
                      尝试 {d.attempts ?? 0} 次 · 事件{" "}
                      {String(d.event_id ?? "—").slice(0, 8)}
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

      {macroOpen && (
        <MacroRegimeModal
          macro={data?.macro}
          onClose={() => setMacroOpen(false)}
        />
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
