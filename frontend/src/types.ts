export type Summary = {
  valid: boolean;
  score: number | null;
  state: string;
  timeframe: string;
  session: string;
  weights?: Record<string, number>;
  contributions?: Record<string, number>;
  contribution_changes?: Record<string, number>;
  close?: number | null;
  dimensions: Record<string, number | null>;
  indicators: Record<string, number | null>;
  risks: string[];
  as_of: string | null;
  evidence: string[];
  rule_version: string;
  opportunity_allowed: boolean;
};
export type VerdictPillar = {
  key: "plan" | "valuation" | "technical" | string;
  label: string;
  status: string;
  tone: "danger" | "warning" | "positive" | "neutral" | "muted" | string;
  detail: string;
};
export type Verdict = {
  action: string;
  action_meaning?: string;
  tone: "danger" | "warning" | "positive" | "neutral" | "muted" | string;
  priority: number;
  headline: string;
  next_step: string;
  pillars: VerdictPillar[];
  dimension_notes: Record<string, string>;
};
export type WatchlistGroup = {
  id: number;
  name: string;
  symbols: string[];
};
export type WatchlistSync = {
  enabled: boolean;
  last_sync: string | null;
  error: string;
  unsupported_count: number;
  unsupported: string[];
};
export type InstrumentInfo = {
  asset_type:
    | "stock"
    | "broad_etf"
    | "sector_etf"
    | "commodity_etf"
    | "leveraged_etf"
    | "fund"
    | string;
  type_label: string;
  benchmark: string;
  is_fund: boolean;
  is_leveraged: boolean;
  is_inverse: boolean;
  leverage: number | null;
  company_valuation_applicable: boolean;
  risk_notice: string;
};
export type FundMetrics = {
  available: boolean;
  window_days: number;
  high_52w: number | null;
  low_52w: number | null;
  drawdown_from_high_pct: number | null;
  range_position_pct: number | null;
  max_drawdown_pct: number | null;
  hv20_pct: number | null;
  hv60_pct: number | null;
  yang_zhang_hv20_pct?: number | null;
  yang_zhang_hv60_pct?: number | null;
  ma200_gap_pct: number | null;
  return_20d_pct: number | null;
  return_60d_pct: number | null;
  return_252d_pct: number | null;
};
export type TugOfWarSummary = {
  available: boolean;
  overnight_20d_pct: number | null;
  intraday_20d_pct: number | null;
  overnight_60d_pct?: number | null;
  intraday_60d_pct?: number | null;
  state: string | null;
  label: string | null;
  warning: string;
};
export type AcademicFactors = {
  available: boolean;
  window_days: number;
  yang_zhang_hv20_pct: number | null;
  yang_zhang_hv60_pct: number | null;
  high_52w: number | null;
  low_52w?: number | null;
  high_52w_ratio: number | null;
  drawdown_52w_pct: number | null;
  residual_mom_z: number | null;
  residual_mom_window: string | null;
  alpha_vs_spy_60d_pct: number | null;
  beta_spy: number | null;
  info_discreteness: number | null;
  id_label: string | null;
  overnight_20d_pct: number | null;
  intraday_20d_pct: number | null;
  overnight_60d_pct?: number | null;
  intraday_60d_pct?: number | null;
  tug_of_war_state: string | null;
  tug_of_war_label: string | null;
  tug_of_war_warning: string;
  max5_21d_pct: number | null;
  lottery_overheated: boolean;
  downside_beta: number | null;
  realized_skew_60d: number | null;
  amihud_20d: number | null;
  avg_dollar_vol_20d?: number | null;
  illiquid_flag: boolean;
  turnover_rate_pct: number | null;
  market_cap: number | null;
  high_turnover_flag: boolean;
};
export type ExtendedSessionQuote = {
  session: "overnight" | "pre" | "post" | string;
  label: string;
  price: number;
  ref_close: number | null;
  gap_pct: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  turnover: number | null;
  turnover_text: string;
  timestamp: string | null;
  liquid: boolean;
  liquidity_label: string;
  is_fresh?: boolean;
};
export type ExtendedHoursSummary = {
  available: boolean;
  is_live_session: boolean;
  rule_version: string;
  source: string;
  active_session: "overnight" | "pre" | "post" | null;
  active_label: string | null;
  price: number | null;
  ref_close: number | null;
  gap_pct: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  turnover: number | null;
  turnover_text: string;
  timestamp: string | null;
  liquid: boolean;
  liquidity_label: string;
  alert_level: "danger" | "warning" | "positive" | "info" | "none" | string;
  badge: string;
  headline: string;
  triggers: string[];
  sessions: Record<string, ExtendedSessionQuote>;
  tug_of_war?: TugOfWarSummary;
  disclaimer: string;
};
export type Stock = {
  symbol: string;
  name: string;
  sleeves: string[];
  instrument?: InstrumentInfo;
  fund_metrics?: FundMetrics;
  academic_factors?: AcademicFactors;
  extended_hours?: ExtendedHoursSummary;
  long_quantity: number;
  short_quantity: number;
  broker_quantity: number;
  available_quantity: number;
  cost_price?: number | null;
  watch_only: boolean;
  watch_sleeve: string;
  stop_price: number | null;
  target_price: number | null;
  long_stop_price?: number | null;
  long_target_price?: number | null;
  favorite: boolean;
  in_watchlist: boolean;
  watchlist_groups: string[];
  manual_watch: boolean;
  reconciled: boolean;
  weight_percent: number | null;
  pnl_percent: number | null;
  change_percent: number | null;
  quote: {
    last?: number;
    prev_close?: number;
    open?: number | null;
    high?: number | null;
    low?: number | null;
    volume?: number | null;
    turnover?: number | null;
    timestamp?: string;
    spread_ratio?: number;
    stale?: boolean;
    seeded?: boolean;
  };
  primary_key: string;
  primary: Summary;
  research: {
    valuation: {
      pe_ttm?: number | null;
      pb?: number | null;
      dividend_yield_pct?: number | null;
      turnover_rate_pct?: number | null;
      market_cap?: number | null;
      fetched_at?: string;
      source: string;
      fresh: boolean;
      refresh_failed?: boolean;
    };
    curve: {
      three_month?: number | null;
      two_year?: number;
      ten_year?: number;
      spread_bp?: number;
      spread_10y_3m_bp?: number | null;
      recession_prob_12m_pct?: number | null;
      ten_change_bp?: number | null;
      prior_date?: string;
      real_ten_year?: number | null;
      as_of?: string;
      source: string;
      fresh: boolean;
      refresh_failed?: boolean;
    };
    earnings_yield_pct: number | null;
    yield_gap_pp: number | null;
    real_ten_year?: number | null;
    real_yield_gap_pp?: number | null;
  };
  long_plan: {
    status: string;
    stop: number | null;
    target: number | null;
    close: number | null;
    as_of: string | null;
    basis?: string;
    watch_only?: boolean;
    stop_distance_percent?: number | null;
    target_distance_percent?: number | null;
  };
  verdict?: Verdict;
  forecast?: StockForecast;
  wave_trend?: WaveTrend;
  summaries: Record<string, Summary>;
};
export type WavePivot = {
  date: string;
  price: number;
  kind: "H" | "L" | string;
  structure: "HH" | "HL" | "LH" | "LL" | "H" | "L" | string;
  wave_label: string;
  confirmed: boolean;
};
export type WaveFibTarget = {
  label: string;
  price: number;
  ratio: number;
};
export type TrendChannel = {
  available: boolean;
  window?: number;
  start_date?: string;
  end_date?: string;
  start_upper?: number;
  end_upper?: number;
  start_mid?: number;
  end_mid?: number;
  start_lower?: number;
  end_lower?: number;
  slope_pct_per_20d?: number;
  position_pct?: number;
};
export type WaveTrend = {
  available: boolean;
  reason: string;
  summary: string;
  action_guide: string;
  trend: {
    direction: "uptrend" | "downtrend" | "sideways" | "unavailable" | string;
    label: string;
    tone: "danger" | "warning" | "positive" | "neutral" | "muted" | string;
    structure: string;
    structure_code: string;
    ma_alignment: string;
    slope_pct_per_20d: number | null;
    channel_position_pct: number | null;
    channel_position_label: string;
    breakout_level: number | null;
    invalidation_level: number | null;
    channel: TrendChannel;
  };
  wave: {
    pattern: "impulse_up" | "impulse_down" | "correction_abc" | "consolidating" | "unavailable" | string;
    pattern_label: string;
    current_wave: string;
    phase_label: string;
    tone: "danger" | "warning" | "positive" | "neutral" | "muted" | string;
    confidence: string;
    rules_passed: string[];
    fib_targets: WaveFibTarget[];
    pivots: WavePivot[];
  };
  disclaimer: string;
};
export type RatingFactor = {
  key: string;
  label: string;
  weight: number;
  score: number | null;
  detail: string;
};
export type StockRating = {
  available: boolean;
  code: "strong_buy" | "buy" | "hold" | "reduce" | "sell" | "unavailable" | string;
  label: string;
  tone: "danger" | "warning" | "positive" | "neutral" | "muted" | string;
  score: number | null;
  stars: number;
  confidence: string;
  summary: string;
  factors: RatingFactor[];
  guardrails: string[];
  disclaimer: string;
};
export type PriceLevels = {
  available: boolean;
  reason: string;
  buy_low: number | null;
  buy_high: number | null;
  ideal_buy: number | null;
  sell_low: number | null;
  sell_high: number | null;
  stop_loss: number | null;
  buy_discount_pct: number | null;
  upside_pct: number | null;
  target_upside_pct: number | null;
  downside_pct: number | null;
  risk_reward_ratio: number | null;
  entry_risk_reward_ratio: number | null;
  position_label: string;
  buy_anchors: string[];
  sell_anchors: string[];
  stop_anchor: string;
};
export type RiskBudget = {
  available: boolean;
  yz_hv_pct: number | null;
  vol_scale: number | null;
  macro_red_count: number | null;
  macro_multiplier: number | null;
  macro_label: string;
  suggested_exposure_ratio: number | null;
  trailing_stop: number | null;
  peak_60d: number | null;
  trailing_drawdown_pct: number | null;
  trailing_breached: boolean;
  note: string;
};
export type StockForecast = {
  levels: PriceLevels;
  rating: StockRating;
  risk_budget?: RiskBudget;
};
export type Signal = {
  id: string;
  symbol: string;
  timeframe: string;
  session: string;
  sleeve: string;
  severity: string;
  title: string;
  message: string;
  data_as_of: string;
  score: number | null;
  evidence: string[];
  historical: boolean;
  source: string;
  kind: string;
};
export type AgentProviderId = "antigravity" | "codex";
export type AgentProviderStatus = {
  id: AgentProviderId;
  label: string;
  protocol: string;
  protocol_label: string;
  official: boolean;
  login_hint: string;
  status: string;
  detail: string;
  configured: boolean;
  model: string;
  automatic: boolean;
  manual_only: boolean;
  enabled: boolean;
  queue_size: number;
  daily_used?: number;
  daily_limit?: number;
};
export type AgentsChannel = {
  default_agent: AgentProviderId;
  manual_only: boolean;
  official_only: boolean;
  providers: Record<AgentProviderId, AgentProviderStatus>;
};
export type Analysis = {
  scope?: string;
  id: string;
  symbol: string;
  agent?: AgentProviderId;
  agent_label?: string;
  protocol?: string;
  model?: string;
  status: string;
  created: number;
  source: string;
  error: string | null;
  result: {
    conclusion: string;
    action: string;
    evidence: string[];
    risks: string[];
    confirmation_conditions: string[];
    data_as_of: string;
  } | null;
};
export type MacroPillar = {
  key: string;
  index: number;
  label: string;
  light: "green" | "yellow" | "red" | "unavailable" | string;
  light_label: string;
  primary_metric: string;
  percentile_10y: number | null;
  direction_13w: string | null;
  change_13w_text: string;
  as_of: string | null;
  released_at: string | null;
  source: string;
  fresh: boolean;
  caveat: string;
  summary: string;
  details: { label: string; value: string }[];
};
export type MacroRegime = {
  available: boolean;
  rule_version: string;
  source: string;
  fetched_at: string | null;
  refresh_failed: boolean;
  partial_errors: Record<string, string>;
  as_of: string | null;
  quadrant: {
    code: "tailwind" | "divergence" | "repair" | "headwind" | "unavailable" | string;
    label: string;
    tone: "positive" | "warning" | "danger" | "neutral" | "muted" | string;
    liquidity_axis: string;
    liquidity_label: string;
    trend_axis: string;
    trend_label: string;
    description: string;
  };
  risk_gauge: {
    red_count: number;
    yellow_count: number;
    green_count: number;
    available_count: number;
    total_count: number;
    label: string;
    tone: "positive" | "warning" | "danger" | "neutral" | "muted" | string;
  };
  alerts: string[];
  real_rate: {
    ten_year_real: number | null;
    as_of: string | null;
    fresh: boolean;
    change_21d_bp: number | null;
  };
  pillars: MacroPillar[];
  disclaimer: string;
};
export type Dashboard = {
  curve: Stock["research"]["curve"];
  macro?: MacroRegime;
  rules?: Record<string, number>;
  mode: string;
  status: string;
  detail: string;
  now: string;
  last_sync: string | null;
  market: {
    session: string;
    label: string;
    new_york: string;
    beijing: string;
    early_close: boolean;
  };
  stocks: Stock[];
  watchlist_groups?: WatchlistGroup[];
  watchlist_sync?: WatchlistSync;
  events: Signal[];
  analyses: Analysis[];
  channels: Record<string, any>;
  summary: {
    count: number;
    strong: number;
    weak: number;
    average: number | null;
    risk_count: number;
    sleeve_weights: Record<string, number>;
    buy_rated?: number;
    hold_rated?: number;
    sell_rated?: number;
  };
  unsupported: string[];
};
export type ChartRow = Record<string, number | string | boolean | null> & {
  timestamp: string;
};
export type EvalMode = "confirmed" | "live";
export type LiveEvaluation = {
  available: boolean;
  reason?: string;
  basis_kind?: string;
  basis_label?: string;
  liquid?: boolean;
  price?: number | null;
  ref_close?: number | null;
  change_pct?: number | null;
  timestamp?: string | null;
  summary?: Summary | null;
  score_delta?: number | null;
  forecast?: Stock["forecast"] | null;
  rating_delta?: number | null;
  rating_changed?: boolean;
  prev_rating_label?: string;
  wave_trend?: WaveTrend | null;
  fund_metrics?: FundMetrics | null;
  academic_factors?: AcademicFactors | null;
  verdict?: Verdict | null;
  long_plan?: Stock["long_plan"] | null;
  live_row?: ChartRow | null;
  disclaimer?: string;
};
export type Detail = {
  mode: string;
  stock: Stock;
  rows: ChartRow[];
  summary: Summary | null;
  live_eval?: LiveEvaluation | null;
  timeframe: string;
  session: string;
};
export function isValidDashboard(value: unknown): value is Dashboard {
  if (!value || typeof value !== "object") return false;
  const obj = value as Record<string, unknown>;
  return (
    Array.isArray(obj.stocks) &&
    typeof obj.mode === "string" &&
    Boolean(obj.market && typeof obj.market === "object")
  );
}
export async function api<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    credentials: "same-origin",
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const text = await response.text();
  let data: any = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      if (!response.ok) {
        throw new Error(`本地服务暂时不可用（HTTP ${response.status}）`);
      }
      throw new Error("本地服务返回了无法解析的响应格式");
    }
  }
  if (!response.ok)
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : JSON.stringify(data?.detail || `请求失败（HTTP ${response.status}）`),
    );
  return data;
}
export const fmt = (n: number | null | undefined, digits = 1) =>
  n == null || !Number.isFinite(n)
    ? "—"
    : n.toLocaleString("en-US", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
export const ticker = (s: string) => s.replace(".US", "");
export const time = (s: string | null | undefined, zone = "Asia/Shanghai") =>
  s && Number.isFinite(Date.parse(s))
    ? new Date(s).toLocaleString("zh-CN", {
        timeZone: zone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "等待数据";
export const labels: Record<string, string> = {
  long: "长期",
  short: "短线",
  unassigned: "未分类",
  regular: "盘中",
  pre: "盘前",
  post: "盘后",
  overnight: "夜盘",
  day: "日线",
  "15m": "15分钟",
  strong: "结构偏强",
  neutral: "中性",
  weak: "结构偏弱",
  unavailable: "待确认",
  observe: "继续观察",
  wait: "等待确认",
  review_entry: "复核入场计划",
  review_exit: "复核退出计划",
  hold: "继续持有",
  review_profit: "复核分批止盈",
  review_stop: "复核止损",
};
