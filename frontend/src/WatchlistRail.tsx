import { useMemo, useState } from "react";
import {
  HelpCircle,
  ListFilter,
  Plus,
  RefreshCw,
  Search,
  Star,
  X,
} from "lucide-react";
import {
  fmt,
  pricePrefix,
  ticker,
  time,
  type Stock,
  type WatchlistGroup,
  type WatchlistSync,
} from "./types";

type RailTab = "all" | "favorite" | "held" | "watchlist";
type SortMode = "rating" | "alert" | "extended" | "gainers" | "losers";

const LABEL_LEGEND: { label: string; tone: string; desc: string }[] = [
  { label: "跌破止损", tone: "danger", desc: "收盘价已低于您设定的止损/失效价" },
  { label: "亏损警示", tone: "danger", desc: "仅上市公司：滚动 PE ≤ 0（ETF/基金不按单股 PE 判定）" },
  { label: "触及目标", tone: "warning", desc: "收盘价已达目标价，可评估分批止盈" },
  { label: "对冲观察", tone: "warning", desc: "反向做空杠杆 ETF，仅作短期波段或对冲观察" },
  { label: "弱势观望 / 转弱警惕", tone: "warning", desc: "日线结构偏弱或技术风险提示较多" },
  { label: "关注买点 / 趋势向好", tone: "positive", desc: "日线处于上升偏强结构且风险较少" },
  { label: "震荡观望 / 持有观察", tone: "neutral", desc: "日线走势中性平稳，继续跟踪方向" },
];

export default function WatchlistRail({
  allStocks,
  watchlistGroups,
  watchlistSync,
  selected,
  onSelect,
  onToggleFavorite,
  onAddWatch,
  onSyncWatchlist,
  syncing,
  onOpenSettings,
  mode,
}: {
  allStocks: Stock[];
  watchlistGroups: WatchlistGroup[];
  watchlistSync?: WatchlistSync;
  selected: string;
  onSelect: (symbol: string) => void;
  onToggleFavorite: (stock: Stock) => void;
  onAddWatch: () => void;
  onSyncWatchlist: () => void;
  syncing: boolean;
  onOpenSettings: () => void;
  mode: string;
}) {
  const [tab, setTab] = useState<RailTab>("all");
  const [market, setMarket] = useState<"all" | Stock["market"]["code"]>("all");
  const [selectedGroup, setSelectedGroup] = useState<string>("__all__");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortMode>("rating");
  const [showLegend, setShowLegend] = useState(false);

  const counts = useMemo(
    () => ({
      all: allStocks.length,
      favorite: allStocks.filter((s) => s.favorite).length,
      held: allStocks.filter((s) => s.broker_quantity > 0).length,
      watchlist: allStocks.filter((s) => s.in_watchlist).length,
    }),
    [allStocks],
  );

  const activeGroups = watchlistGroups.filter((g) => g.symbols.length > 0);
  const currentGroup = activeGroups.some((g) => g.name === selectedGroup)
    ? selectedGroup
    : "__all__";

  const visibleStocks = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = allStocks.filter((s) => {
      if (market !== "all" && s.market.code !== market) return false;
      if (tab === "favorite" && !s.favorite) return false;
      if (tab === "held" && s.broker_quantity <= 0) return false;
      if (tab === "watchlist") {
        if (!s.in_watchlist) return false;
        if (
          currentGroup !== "__all__" &&
          !(s.watchlist_groups ?? []).includes(currentGroup)
        ) {
          return false;
        }
      }
      if (q && !`${s.symbol} ${ticker(s.symbol)} ${s.name}`.toLowerCase().includes(q)) return false;
      return true;
    });

    return [...filtered].sort((a, b) => {
      if (sort === "rating") {
        const scoreA = a.forecast?.rating?.available
          ? (a.forecast.rating.score ?? -1)
          : -1;
        const scoreB = b.forecast?.rating?.available
          ? (b.forecast.rating.score ?? -1)
          : -1;
        if (scoreB !== scoreA) return scoreB - scoreA;
        const techDiff = (b.primary?.score ?? -1) - (a.primary?.score ?? -1);
        if (techDiff !== 0) return techDiff;
        return Number(b.favorite) - Number(a.favorite);
      }
      if (sort === "extended") {
        const extA = a.extended_hours;
        const extB = b.extended_hours;
        const liveA = Boolean(extA?.available && extA.is_live_session && extA.gap_pct != null);
        const liveB = Boolean(extB?.available && extB.is_live_session && extB.gap_pct != null);
        if (liveA !== liveB) return Number(liveB) - Number(liveA);
        const liqA = liveA && extA?.liquid ? 1 : 0;
        const liqB = liveB && extB?.liquid ? 1 : 0;
        if (liqA !== liqB) return liqB - liqA;
        const gapA = liveA ? Math.abs(extA!.gap_pct!) : -1;
        const gapB = liveB ? Math.abs(extB!.gap_pct!) : -1;
        if (gapB !== gapA) return gapB - gapA;
        return (extB?.turnover ?? -1) - (extA?.turnover ?? -1);
      }
      if (sort === "gainers") {
        const chgA = a.change_percent ?? Number.NEGATIVE_INFINITY;
        const chgB = b.change_percent ?? Number.NEGATIVE_INFINITY;
        if (chgB !== chgA) return chgB - chgA;
        return (
          (b.forecast?.rating?.score ?? -1) - (a.forecast?.rating?.score ?? -1)
        );
      }
      if (sort === "losers") {
        const chgA = a.change_percent ?? Number.POSITIVE_INFINITY;
        const chgB = b.change_percent ?? Number.POSITIVE_INFINITY;
        if (chgA !== chgB) return chgA - chgB;
        return (a.verdict?.priority ?? 9) - (b.verdict?.priority ?? 9);
      }
      // "alert": 风险预警（止损/目标/仓位待核/亏损警示/风险数量优先）
      const priDiff = (a.verdict?.priority ?? 9) - (b.verdict?.priority ?? 9);
      if (priDiff !== 0) return priDiff;
      const riskDiff =
        (b.primary?.risks?.length ?? 0) - (a.primary?.risks?.length ?? 0);
      if (riskDiff !== 0) return riskDiff;
      const favDiff = Number(b.favorite) - Number(a.favorite);
      if (favDiff !== 0) return favDiff;
      return b.broker_quantity - a.broker_quantity;
    });
  }, [allStocks, market, tab, currentGroup, query, sort]);

  return (
    <aside className="rail-panel" id="holdings" aria-label="行情与自选列表">
      <div className="rail-top">
        <label className="rail-search">
          <Search size={15} />
          <input
            aria-label="搜索股票"
            placeholder="搜代码或名称…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="rail-action-btn"
          onClick={onSyncWatchlist}
          disabled={syncing}
          title="同步账号自选股单"
          aria-label="同步账号自选股单"
        >
          <RefreshCw size={15} className={syncing ? "spin" : ""} />
          <span>同步自选</span>
        </button>
        <button
          type="button"
          className="rail-icon-btn"
          onClick={onAddWatch}
          title="添加本地观察股票"
          aria-label="添加观察股票"
        >
          <Plus size={17} />
        </button>
      </div>

      <div className="rail-tabs" role="tablist" aria-label="股票列表分组">
        {(
          [
            ["favorite", "★ 收藏", counts.favorite],
            ["held", "持仓", counts.held],
            ["watchlist", "自选股", counts.watchlist],
            ["all", "全部", counts.all],
          ] as const
        ).map(([id, label, count]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
          >
            <span>{label}</span>
            <em>{count}</em>
          </button>
        ))}
      </div>

      <div className="rail-markets" role="group" aria-label="按市场筛选">
        {([["all", "全部市场"], ["US", "美股"], ["HK", "港股"], ["CN", "A股"]] as const).map(([id, label]) => (
          <button key={id} type="button" aria-pressed={market === id} onClick={() => setMarket(id)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "watchlist" && activeGroups.length > 0 && (
        <div className="group-pills" aria-label="自选分组筛选">
          <button
            type="button"
            className={currentGroup === "__all__" ? "active" : ""}
            onClick={() => setSelectedGroup("__all__")}
          >
            全部分组
          </button>
          {activeGroups.map((g) => (
            <button
              key={g.id + g.name}
              type="button"
              className={currentGroup === g.name ? "active" : ""}
              onClick={() => setSelectedGroup(g.name)}
            >
              {g.name} ({g.symbols.length})
            </button>
          ))}
        </div>
      )}

      <div className="rail-subbar">
        <div className="rail-subbar-left">
          <span className="rail-count">共 {visibleStocks.length} 只</span>
          <button
            type="button"
            className={`legend-help-btn ${showLegend ? "active" : ""}`}
            onClick={() => setShowLegend((v) => !v)}
            title="查看状态标签含义"
            aria-label="查看状态标签含义"
            aria-expanded={showLegend}
          >
            <HelpCircle size={13} />
            <span>标签说明</span>
          </button>
        </div>
        <label className="rail-sort" title="切换左侧股票列表排序方式">
          <ListFilter size={14} />
          <select
            aria-label="资产排序"
            value={sort}
            onChange={(e) => setSort(e.target.value as SortMode)}
          >
            <option value="rating">买卖评级</option>
            <option value="alert">风险预警</option>
            <option value="extended">盘外异动</option>
            <option value="gainers">今日涨幅</option>
            <option value="losers">今日跌幅</option>
          </select>
        </label>
      </div>

      {showLegend && (
        <div className="rail-legend-card" role="region" aria-label="状态标签含义说明">
          <div className="rail-legend-head">
            <b>状态标签含义（鼠标悬停各股可看具体原因）</b>
            <button
              type="button"
              className="legend-close-btn"
              onClick={() => setShowLegend(false)}
              aria-label="关闭说明"
            >
              <X size={14} />
            </button>
          </div>
          <ul className="rail-legend-list">
            {LABEL_LEGEND.map((item) => (
              <li key={item.label}>
                <span className={`verdict-chip tone-${item.tone}`}>
                  {item.label}
                </span>
                <span>{item.desc}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(watchlistSync?.error ||
        (mode === "live" &&
          (watchlistSync?.last_sync ||
            (watchlistSync?.unsupported_count ?? 0) > 0))) && (
        <div
          className={`rail-sync-note ${watchlistSync?.error ? "error" : ""}`}
        >
          {watchlistSync?.error ? (
            <span>{watchlistSync.error}</span>
          ) : (
            <span>
              自选同步{" "}
              {watchlistSync?.last_sync
                ? time(watchlistSync.last_sync)
                : "等待首次同步"}
              {(watchlistSync?.unsupported_count ?? 0) > 0
                ? ` · ${watchlistSync?.unsupported_count} 个代码暂不支持`
                : ""}
            </span>
          )}
        </div>
      )}

      <div className="rail-list" role="listbox" aria-label="股票行情列表">
        {visibleStocks.map((s) => {
          const isSelected = selected === s.symbol;
          const tone = s.verdict?.tone ?? "muted";
          const actionText = s.verdict?.action ?? s.long_plan?.status ?? "观察";
          const actionTip =
            s.verdict?.action_meaning || s.verdict?.headline || actionText;
          const changeClass =
            s.change_percent == null
              ? "muted"
              : s.change_percent >= 0
                ? "quote-up"
                : "quote-down";
          return (
            <div
              key={s.symbol}
              role="option"
              aria-selected={isSelected}
              tabIndex={0}
              className={`stock-row ${isSelected ? "selected" : ""}`}
              onClick={() => onSelect(s.symbol)}
              onKeyDown={(e) => {
                if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) {
                  e.preventDefault();
                  onSelect(s.symbol);
                }
              }}
            >
              <div className="stock-row-line1">
                <div className="stock-row-id">
                  <button
                    type="button"
                    className={`star-btn ${s.favorite ? "starred" : ""}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onToggleFavorite(s);
                    }}
                    aria-label={
                      s.favorite
                        ? `取消收藏 ${ticker(s.symbol)}`
                        : `收藏 ${ticker(s.symbol)}`
                    }
                    title={s.favorite ? "取消收藏" : "加入收藏"}
                  >
                    <Star
                      size={15}
                      fill={s.favorite ? "currentColor" : "none"}
                    />
                  </button>
                  <b className="stock-row-ticker" title={ticker(s.symbol)}>{s.market.code === "CN" ? s.symbol.slice(0, -3) : ticker(s.symbol)}</b>
                  {s.market.code !== "US" && s.instrument ? (
                    <span className="market-badge" title={s.instrument.risk_notice || s.instrument.type_label}>
                      {s.instrument.type_label}
                    </span>
                  ) : <span
                    className={`verdict-chip tone-${tone}`}
                    title={`${actionText}：${actionTip}`}
                  >
                    {actionText}
                  </span>}
                </div>
                <strong className="stock-row-price">
                  {s.quote?.last != null ? pricePrefix(s.currency) + fmt(s.quote.last, 2) : "—"}
                </strong>
              </div>

              <div className="stock-row-line2">
                <div className="stock-row-sub">
                  <span className="market-badge" data-market={s.market.code} title={`${s.market.name} · ${s.symbol}`}>
                    {s.market.code === "CN" ? (s.symbol.endsWith(".SH") ? "沪A" : "深A") : s.market.name}
                  </span>
                  <span className="stock-row-name" title={[s.name, s.instrument?.type_label].filter(Boolean).join(" · ")}>
                    {s.name || (s.market.code === "US" ? "观察标的" : "名称待同步")}
                  </span>
                </div>
                <div className="stock-row-nums">
                  <span className={`stock-row-chg ${changeClass}`}>
                    {s.change_percent != null
                      ? (s.change_percent >= 0 ? "+" : "") +
                        fmt(s.change_percent, 2) +
                        "%"
                      : "待更新"}
                  </span>
                  {s.forecast?.rating?.available ? (
                    <span
                      className={`rating-mini tone-text-${s.forecast.rating.tone}`}
                      title={s.forecast.rating.summary}
                    >
                      {s.forecast.rating.label} {fmt(s.forecast.rating.score, 0)}
                    </span>
                  ) : (
                    <span className="stock-row-meta">
                      {s.primary?.score != null
                        ? `分 ${fmt(s.primary.score, 0)}`
                        : s.instrument?.is_fund
                          ? s.instrument.type_label
                          : s.research?.valuation?.pe_ttm != null
                            ? `PE ${fmt(s.research.valuation.pe_ttm, 1)}`
                            : "—"}
                    </span>
                  )}
                </div>
              </div>

              {s.extended_hours?.available &&
                s.extended_hours.is_live_session &&
                s.extended_hours.price != null &&
                (sort === "extended" ||
                  (s.extended_hours.gap_pct != null &&
                    Math.abs(s.extended_hours.gap_pct) >= 1.5) ||
                  s.extended_hours.triggers.length > 0) && (
                  <div
                    className="stock-row-ext"
                    title={s.extended_hours.headline}
                  >
                    <span className="stock-row-ext-left">
                      <span
                        className={`stock-row-ext-tag ${
                          s.extended_hours.liquid ? "" : "thin"
                        }`}
                      >
                        {s.extended_hours.active_label}
                      </span>
                      <span className="stock-row-ext-price">
                        ${fmt(s.extended_hours.price, 2)}
                      </span>
                      {s.extended_hours.gap_pct != null && (
                        <span
                          className={
                            s.extended_hours.gap_pct >= 0
                              ? "quote-up"
                              : "quote-down"
                          }
                        >
                          {s.extended_hours.gap_pct >= 0 ? "+" : ""}
                          {fmt(s.extended_hours.gap_pct, 1)}%
                        </span>
                      )}
                    </span>
                    <span className="stock-row-ext-right">
                      {s.extended_hours.liquid
                        ? s.extended_hours.turnover_text
                        : "偏薄"}
                    </span>
                  </div>
                )}
            </div>
          );
        })}

        {!visibleStocks.length && (
          <div className="rail-empty">
            <Star size={24} />
            <b>
              {market !== "all" || query.trim() ? "没有匹配的股票" : tab === "favorite"
                ? "还没有收藏股票"
                : tab === "watchlist"
                  ? "暂无账号自选股票"
                  : tab === "held"
                    ? "当前模式暂无持仓"
                    : "没有匹配的股票"}
            </b>
            <p>
              {market !== "all" || query.trim() ? "可以切换市场或调整搜索条件。" : tab === "favorite"
                ? "点击任意股票左侧的星标即可加入本地收藏，方便集中复核。"
                : tab === "watchlist"
                  ? "连接 LongPort 后可同步账号自选股，也可手动添加观察股。"
                  : "可以调整筛选条件，或添加本地观察股票。"}
            </p>
            <div className="rail-empty-actions">
              {tab === "watchlist" && (
                <button
                  type="button"
                  className="button secondary"
                  onClick={
                    mode === "live" ? onSyncWatchlist : onOpenSettings
                  }
                >
                  {mode === "live" ? "立即同步自选" : "配置实盘接入"}
                </button>
              )}
              <button
                type="button"
                className="button secondary"
                onClick={onAddWatch}
              >
                <Plus size={14} />
                添加观察
              </button>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
