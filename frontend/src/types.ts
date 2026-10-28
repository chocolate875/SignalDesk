export type Summary = {
  valid: boolean;
  score: number | null;
  state: string;
  timeframe: string;
  session: string;
  weights?: Record<string, number>;
  dimensions: Record<string, number | null>;
  indicators: Record<string, number | null>;
  risks: string[];
  as_of: string | null;
  evidence: string[];
  rule_version: string;
  opportunity_allowed: boolean;
};
export type Stock = {
  symbol: string;
  name: string;
  sleeves: string[];
  long_quantity: number;
  short_quantity: number;
  broker_quantity: number;
  available_quantity: number;
  watch_only: boolean;
  watch_sleeve: string;
  stop_price: number | null;
  target_price: number | null;
  reconciled: boolean;
  weight_percent: number | null;
  pnl_percent: number | null;
  change_percent: number | null;
  quote: { last?: number; timestamp?: string; spread_ratio?: number };
  primary_key: string;
  primary: Summary;
  summaries: Record<string, Summary>;
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
export type Analysis = {
  id: string;
  symbol: string;
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
export type Dashboard = {
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
  };
  unsupported: string[];
};
export type ChartRow = Record<string, number | string | null> & {
  timestamp: string;
};
export type Detail = {
  stock: Stock;
  rows: ChartRow[];
  summary: Summary | null;
  timeframe: string;
  session: string;
};
export async function api<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    credentials: "same-origin",
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail || "请求失败"),
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
  s
    ? new Date(s).toLocaleString("zh-CN", {
        timeZone: zone,
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
};
