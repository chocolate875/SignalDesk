import { useMemo, useState } from "react";
import {
  Plus,
  RefreshCw,
  Search,
  Star,
  ListFilter,
} from "lucide-react";
import {
  fmt,
  ticker,
  time,
  type Stock,
  type WatchlistGroup,
  type WatchlistSync,
} from "./types";

type RailTab = "all" | "favorite" | "held" | "watchlist";
type SortMode = "plan" | "favorite" | "change" | "score" | "risk";

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
  const [selectedGroup, setSelectedGroup] = useState<string>("__all__");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortMode>("plan");

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
      if (q && !`${s.symbol} ${s.name}`.toLowerCase().includes(q)) return false;
      return true;
    });

    return [...filtered].sort((a, b) => {
      if (sort === "favorite") {
        const favDiff = Number(b.favorite) - Number(a.favorite);
        if (favDiff !== 0) return favDiff;
        return (a.verdict?.priority ?? 9) - (b.verdict?.priority ?? 9);
      }
      if (sort === "change") {
        return (b.change_percent ?? -999) - (a.change_percent ?? -999);
      }
      if (sort === "score") {
        return (b.primary.score ?? -1) - (a.primary.score ?? -1);
      }
      if (sort === "risk") {
        return (
          (b.primary.risks?.length ?? 0) - (a.primary.risks?.length ?? 0)
        );
      }
      const priDiff = (a.verdict?.priority ?? 9) - (b.verdict?.priority ?? 9);
      if (priDiff !== 0) return priDiff;
      const favDiff = Number(b.favorite) - Number(a.favorite);
      if (favDiff !== 0) return favDiff;
      return b.broker_quantity - a.broker_quantity;
    });
  }, [allStocks, tab, currentGroup, query, sort]);

  const sourceTag = (s: Stock) => {
    if (s.broker_quantity > 0) {
      if (!s.reconciled) return "数量待核对";
      return s.weight_percent != null
        ? `持仓 ${fmt(s.weight_percent, 1)}%`
        : "持仓";
    }
    if (s.in_watchlist) {
      return s.watchlist_groups?.length
        ? `自选·${s.watchlist_groups[0]}`
        : "账号自选";
    }
    return "本地观察";
  };

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
        <span className="rail-count">共 {visibleStocks.length} 只</span>
        <label className="rail-sort">
          <ListFilter size={14} />
          <select
            aria-label="资产排序"
            value={sort}
            onChange={(e) => setSort(e.target.value as SortMode)}
          >
            <option value="plan">待复核优先</option>
            <option value="favorite">收藏优先</option>
            <option value="change">涨跌幅</option>
            <option value="score">技术评分</option>
            <option value="risk">风险优先</option>
          </select>
        </label>
      </div>

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
                ? ` · 已忽略 ${watchlistSync?.unsupported_count} 只非美股`
                : ""}
            </span>
          )}
        </div>
      )}

      <div className="rail-list" role="listbox" aria-label="股票行情列表">
        {visibleStocks.map((s) => {
          const isSelected = selected === s.symbol;
          const tone = s.verdict?.tone ?? "muted";
          const actionText = s.verdict?.action ?? s.long_plan.status;
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
                if (e.key === "Enter" || e.key === " ") {
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
                  <b className="stock-row-ticker">{ticker(s.symbol)}</b>
                  <span className={`verdict-chip tone-${tone}`}>
                    {actionText}
                  </span>
                </div>
                <strong className="stock-row-price">
                  {s.quote.last != null ? "$" + fmt(s.quote.last, 2) : "—"}
                </strong>
              </div>

              <div className="stock-row-line2">
                <div className="stock-row-sub">
                  <span className="stock-row-name">
                    {s.name || "观察股票"}
                  </span>
                  <span className="source-pill">{sourceTag(s)}</span>
                </div>
                <div className="stock-row-nums">
                  <span className={`stock-row-chg ${changeClass}`}>
                    {s.change_percent != null
                      ? (s.change_percent >= 0 ? "+" : "") +
                        fmt(s.change_percent, 2) +
                        "%"
                      : "待更新"}
                  </span>
                  <span className="stock-row-meta">
                    {s.primary.score != null
                      ? `分 ${fmt(s.primary.score, 0)}`
                      : s.research.valuation.pe_ttm != null
                        ? `PE ${fmt(s.research.valuation.pe_ttm, 1)}`
                        : "—"}
                  </span>
                </div>
              </div>
            </div>
          );
        })}

        {!visibleStocks.length && (
          <div className="rail-empty">
            <Star size={24} />
            <b>
              {tab === "favorite"
                ? "还没有收藏股票"
                : tab === "watchlist"
                  ? "暂无账号自选美股"
                  : tab === "held"
                    ? "当前模式暂无持仓"
                    : "没有匹配的股票"}
            </b>
            <p>
              {tab === "favorite"
                ? "点击任意股票左侧的星标即可加入本地收藏，方便集中复核。"
                : tab === "watchlist"
                  ? "连接 LongPort 后会自动同步您的美股自选股单，也可手动添加观察股。"
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
