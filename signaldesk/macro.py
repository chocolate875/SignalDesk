"""宏观水位、流动性与「市场大势」严格因果引擎（P0 数据底座 + P1 六分项与四象限）。

定位为市场整体风险环境底色：
- 严格按真实发布时间（release_at <= now）对齐数据，禁止按观察日偷看未发布数据；
- 历史分位仅使用截至当日的滚动窗口（禁止全样本分位），缺失值不前向填充；
- 不输出 0–100 黑箱大势总分，不做择时信号或点位预测，第一阶段只展示、不干预个股评级。
"""

from __future__ import annotations

import asyncio
import math
from bisect import bisect_right
from datetime import date, datetime, time, timedelta
from typing import Any

import httpx
import numpy as np
import pandas as pd

from .calendar import NY
from .forecast import _contiguous_regular_tail
from .indicators import finite
from .research import nyfed_recession_prob_pct

MACRO_RULE_VERSION = "macro-1.0.0"
MACRO_DISCLAIMER = (
    "宏观水位与市场大势仅刻画市场整体风险环境底色，不预测指数涨跌点位，不构成择时或投资建议；当前阶段仅展示，不自动干预个股评级。"
)

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# 经 2026-11-23 实测验证免 Key 可用的 FRED 公开序列清单
FRED_SERIES_IDS: tuple[str, ...] = (
    "WALCL",         # 联储总资产（百万美元，H.4.1 周三观测 / 周四 16:30 ET 发布）
    "WTREGEN",       # 财政部 TGA 一般账户（百万美元，H.4.1 周三观测 / 周四 16:30 ET 发布）
    "RRPONTSYD",     # 隔夜逆回购 ON RRP（十亿美元，日频）
    "WRESBAL",       # 银行准备金余额（百万美元，H.4.1 周三观测 / 周四 16:30 ET 发布）
    "SOFR",          # 担保隔夜融资利率（%，日频，滞后1工作日）
    "IORB",          # 准备金余额利率（%，日频）
    "NFCI",          # 芝加哥联储全国金融条件指数（周频，周五观测 / 次周周三发布）
    "ANFCI",         # 调整后金融条件指数（周频，周五观测 / 次周周三发布）
    "BAMLH0A0HYM2",  # ICE BofA 美国高收益债 OAS（%，FRED 授权约近3年）
    "BAA10Y",        # Moody's Baa 企债 − 10Y 美债利差（%，40年完整历史）
    "VIXCLS",        # CBOE 波动率指数 VIX（日频，滞后1日）
    "DTWEXBGS",      # 广义贸易加权美元指数（日频）
    "DFII10",        # 10 年期 TIPS 实际利率（%，日频）
    "T10Y3M",        # 10Y − 3M 美债利差（%，日频，用于核对近6个月倒挂解除状态）
)

# 全市场趋势与广度只读基准 ETF（独立缓存分区，不混入用户自选列表）
MACRO_BENCHMARK_SYMBOLS: tuple[str, ...] = (
    "SPY.US",
    "QQQ.US",
    "RSP.US",
    "IWM.US",
    "HYG.US",
    "IEF.US",
)

# 仅保留近 11.5 年原始观测用于 10 年滚动分位与 13 周变化，控制 SQLite 缓存体积
_KEEP_YEARS = 11.5


def parse_fred_csv(text: str, min_date: date | None = None) -> list[list[Any]]:
    """解析 FRED fredgraph CSV，剔除 '.' 等缺失行，绝不前向填充。"""
    rows: dict[str, float] = {}
    lines = text.splitlines()
    for line in lines[1:]:
        parts = line.strip().split(",")
        if len(parts) < 2:
            continue
        day_str, raw_val = parts[0].strip(), parts[1].strip()
        if not day_str or not raw_val or raw_val == ".":
            continue
        val = finite(raw_val)
        if val is None:
            continue
        try:
            obs_day = date.fromisoformat(day_str)
        except ValueError:
            continue
        if min_date is not None and obs_day < min_date:
            continue
        rows[day_str] = val
    return [[d, rows[d]] for d in sorted(rows)]


def release_datetime(series_id: str, obs_day: date) -> datetime:
    """按各宏观序列真实官方发布时间返回带纽约时区的最早可用时刻。"""
    sid = series_id.upper()
    if sid in {"WALCL", "WTREGEN", "WRESBAL"}:
        # Fed H.4.1：每周四 16:30 ET 发布截至周三的数据
        days_to_thu = (3 - obs_day.weekday()) % 7
        if days_to_thu == 0:
            days_to_thu = 1
        rel_day = obs_day + timedelta(days=days_to_thu)
        return datetime.combine(rel_day, time(16, 30), tzinfo=NY)
    if sid in {"NFCI", "ANFCI"}:
        # Chicago Fed NFCI：每周三 08:30 CT (09:30 ET) 发布截至上周五的数据
        days_to_wed = (2 - obs_day.weekday()) % 7
        if days_to_wed == 0:
            days_to_wed = 5
        rel_day = obs_day + timedelta(days=days_to_wed)
        return datetime.combine(rel_day, time(9, 30), tzinfo=NY)
    if sid == "IORB":
        # 联储政策利率生效当日美东 09:00 可用
        return datetime.combine(obs_day, time(9, 0), tzinfo=NY)
    # 其余日频市场/信用/利差/逆回购序列：次日美东 09:00 后作为已发布观测
    return datetime.combine(obs_day + timedelta(days=1), time(9, 0), tzinfo=NY)


def published_series(
    series_id: str,
    raw_pairs: list[list[Any]] | list[tuple[str, float]] | None,
    now: datetime,
) -> list[tuple[str, float, datetime]]:
    """严格过滤出发布时刻 <= now 的已发布序列，消除未来数据泄露。"""
    if not raw_pairs:
        return []
    now_ny = now.astimezone(NY)
    result: list[tuple[str, float, datetime]] = []
    for item in raw_pairs:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        day_str, raw_val = item[0], item[1]
        val = finite(raw_val)
        if not isinstance(day_str, str) or val is None:
            continue
        try:
            obs_day = date.fromisoformat(day_str)
        except ValueError:
            continue
        rel = release_datetime(series_id, obs_day)
        if rel <= now_ny:
            result.append((day_str, val, rel))
    result.sort(key=lambda x: x[0])
    return result


def causal_percentile(values: list[float], lookback: int, min_samples: int) -> float | None:
    """严格因果滚动历史分位（0–100）：仅使用截至当前点的历史窗口，样本不足返回 None。"""
    clean = [v for v in values if v is not None and math.isfinite(v)]
    if len(clean) < min_samples:
        return None
    window = clean[-lookback:]
    current = window[-1]
    less = sum(1 for x in window if x < current)
    equal = sum(1 for x in window if x == current)
    rank = (less + 0.5 * equal) / len(window)
    return round(rank * 100.0, 1)


def _lookup_prior_by_days(
    series: list[tuple[str, float, datetime]],
    target_days: int,
    max_slack_days: int = 14,
) -> tuple[str, float] | None:
    """在已发布序列中查找目标日历天数之前的最近一条观测（不跨越过大缺口）。"""
    if len(series) < 2:
        return None
    latest_day = date.fromisoformat(series[-1][0])
    target_day = latest_day - timedelta(days=target_days)
    dates = [item[0] for item in series[:-1]]
    idx = bisect_right(dates, target_day.isoformat()) - 1
    if idx < 0:
        return None
    found_day = date.fromisoformat(series[idx][0])
    if (target_day - found_day).days > max_slack_days:
        return None
    return series[idx][0], series[idx][1]


def _fresh_within(obs_day_str: str | None, now: datetime, max_days: int) -> bool:
    if not obs_day_str:
        return False
    try:
        obs_day = date.fromisoformat(obs_day_str)
    except ValueError:
        return False
    delta = (now.astimezone(NY).date() - obs_day).days
    return 0 <= delta <= max_days


async def fetch_fred_bundle(now: datetime, existing: dict | None = None) -> dict:
    """并行抓取 FRED 公开 CSV 序列；单项失败时保留该序列已有缓存并记录失败状态。"""
    min_date = now.astimezone(NY).date() - timedelta(days=int(_KEEP_YEARS * 365.25))
    old_series = (existing or {}).get("series") or {}
    fetched_at = now.isoformat()

    async def fetch_one(client: httpx.AsyncClient, sid: str) -> tuple[str, list[list[Any]] | None, str | None]:
        try:
            resp = await client.get(FRED_CSV_URL, params={"id": sid})
            resp.raise_for_status()
            parsed = parse_fred_csv(resp.text, min_date=min_date)
            if not parsed:
                return sid, None, "空序列"
            return sid, parsed, None
        except Exception as exc:
            return sid, None, type(exc).__name__

    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        results = await asyncio.gather(*(fetch_one(client, sid) for sid in FRED_SERIES_IDS))

    series_out: dict[str, list[list[Any]]] = {}
    errors: dict[str, str] = {}
    ok_count = 0
    for sid, parsed, err in results:
        if parsed is not None:
            series_out[sid] = parsed
            ok_count += 1
        else:
            errors[sid] = err or "fetch_failed"
            if sid in old_series:
                series_out[sid] = old_series[sid]

    return {
        "source": "FRED",
        "fetched_at": fetched_at,
        "series": series_out,
        "errors": errors,
        "ok_count": ok_count,
        "total_count": len(FRED_SERIES_IDS),
        "refresh_failed": ok_count == 0,
    }


def _net_liquidity_series(
    walcl: list[tuple[str, float, datetime]],
    wtregen: list[tuple[str, float, datetime]],
    rrp: list[tuple[str, float, datetime]],
) -> list[tuple[str, float, datetime]]:
    """按周三 H.4.1 观测日合成美联储净流动性（十亿美元 Billions USD）。

    单位经实测验证：WALCL / WTREGEN 为百万美元（÷1000），RRPONTSYD 为十亿美元（×1）。
    仅当三项在对应周内均有有效观测时生成，绝不跨周前向填充。
    """
    if not walcl or not wtregen or not rrp:
        return []
    tga_map = {d: v for d, v, _ in wtregen}
    rrp_dates = [d for d, _, _ in rrp]
    rrp_vals = [v for _, v, _ in rrp]

    out: list[tuple[str, float, datetime]] = []
    for wed_str, walcl_m, rel in walcl:
        tga_m = tga_map.get(wed_str)
        if tga_m is None:
            continue
        pos = bisect_right(rrp_dates, wed_str) - 1
        if pos < 0:
            continue
        rrp_day = date.fromisoformat(rrp_dates[pos])
        wed_day = date.fromisoformat(wed_str)
        if (wed_day - rrp_day).days > 5:
            continue
        net_b = round(walcl_m / 1000.0 - tga_m / 1000.0 - rrp_vals[pos], 2)
        out.append((wed_str, net_b, rel))
    return out


def _light_label(light: str) -> str:
    return {
        "green": "宽松/健康",
        "yellow": "偏谨/分化",
        "red": "压力/警惕",
        "unavailable": "待补齐",
    }.get(light, "待补齐")


def _extract_etf_close_map(frame: pd.DataFrame | None) -> tuple[list[str], list[float]]:
    """提取已确认连续常规日线的 (纽约日期, 收盘价) 序列。"""
    tail = _contiguous_regular_tail(frame)
    if tail.empty:
        return [], []
    dates = [ts.to_pydatetime().astimezone(NY).date().isoformat() for ts in tail["timestamp"]]
    closes = [float(x) for x in tail["close"].to_numpy(dtype=float)]
    return dates, closes


def _compute_spy_hv20(closes: list[float]) -> float | None:
    if len(closes) < 21:
        return None
    arr = np.asarray(closes[-21:], dtype=float)
    if np.any(arr <= 0):
        return None
    log_ret = np.diff(np.log(arr))
    val = finite(float(np.std(log_ret, ddof=1) * math.sqrt(252.0) * 100.0))
    return round(val, 2) if val is not None else None


def _compute_ratio_change_63d(
    dates_a: list[str], closes_a: list[float], dates_b: list[str], closes_b: list[float]
) -> dict[str, Any]:
    """严格按两只 ETF 的共同交易日交集计算比值及 63 日（约 13 周）变化%，不前向填充。"""
    map_b = dict(zip(dates_b, closes_b))
    ratios: list[tuple[str, float]] = []
    for d, ca in zip(dates_a, closes_a):
        cb = map_b.get(d)
        if cb is not None and cb > 0 and ca > 0:
            ratios.append((d, ca / cb))
    if len(ratios) < 64:
        return {"available": False, "latest": None, "change_63d_pct": None, "as_of": ratios[-1][0] if ratios else None}
    latest_d, latest_r = ratios[-1]
    prior_r = ratios[-64][1]
    chg = round((latest_r / prior_r - 1.0) * 100.0, 2)
    return {"available": True, "latest": round(latest_r, 4), "change_63d_pct": chg, "as_of": latest_d}


def compute_macro_regime(
    fred_bundle: dict | None,
    curve: dict | None,
    benchmark_frames: dict[str, pd.DataFrame] | None,
    now: datetime,
    demo: bool = False,
) -> dict:
    """严格因果合成六分项指示灯、四象限大势环境与红灯下行风险水位。"""
    series_raw = (fred_bundle or {}).get("series") or {}
    errors = (fred_bundle or {}).get("errors") or {}
    source_label = "合成宏观数据" if demo else "FRED + 美国财政部 + LongPort"

    def get_pub(sid: str) -> list[tuple[str, float, datetime]]:
        return published_series(sid, series_raw.get(sid), now)

    walcl = get_pub("WALCL")
    wtregen = get_pub("WTREGEN")
    rrp = get_pub("RRPONTSYD")
    wresbal = get_pub("WRESBAL")
    sofr = get_pub("SOFR")
    iorb = get_pub("IORB")
    nfci = get_pub("NFCI")
    anfci = get_pub("ANFCI")
    hy_oas = get_pub("BAMLH0A0HYM2")
    baa10y = get_pub("BAA10Y")
    vix = get_pub("VIXCLS")
    dxy = get_pub("DTWEXBGS")
    dfii10 = get_pub("DFII10")
    t10y3m = get_pub("T10Y3M")

    # ================= ① 央行与财政水位 =================
    net_liq = _net_liquidity_series(walcl, wtregen, rrp)
    sofr_iorb_bp: float | None = None
    sofr_as_of: str | None = None
    if sofr and iorb:
        iorb_map = {d: v for d, v, _ in iorb}
        for d, sv, _ in reversed(sofr):
            iv = iorb_map.get(d)
            if iv is not None:
                sofr_iorb_bp = round((sv - iv) * 100.0, 1)
                sofr_as_of = d
                break

    if net_liq:
        nl_date, nl_now, nl_rel = net_liq[-1]
        nl_fresh = _fresh_within(nl_date, now, 14)
        nl_pct = causal_percentile([v for _, v, _ in net_liq], lookback=520, min_samples=104)
        nl_chg_13w = round(nl_now - net_liq[-14][1], 1) if len(net_liq) >= 14 else None
        # 严格因果：基于过去最多 10 年（520 周）的 13 周滚动变化计算标准差 σ
        nl_diffs = [net_liq[i][1] - net_liq[i - 13][1] for i in range(13, len(net_liq))]
        nl_sigma = (
            float(np.std(nl_diffs[-520:], ddof=0))
            if len(nl_diffs) >= 52
            else None
        )
        res_now_b = round(wresbal[-1][1] / 1000.0, 1) if wresbal else None
        res_chg_13w = round((wresbal[-1][1] - wresbal[-14][1]) / 1000.0, 1) if len(wresbal) >= 14 else None
        pipe_stress = sofr_iorb_bp is not None and sofr_iorb_bp > 0.0

        if pipe_stress or (nl_chg_13w is not None and nl_sigma is not None and nl_chg_13w < -nl_sigma):
            liq_light = "red"
            liq_reason = (
                f"资金管道出现紧绷（SOFR−IORB {sofr_iorb_bp:+.1f}bp > 0）"
                if pipe_stress
                else f"净流动性 13 周收缩 {nl_chg_13w:+.0f}B（超 −1σ={-nl_sigma:.0f}B 警戒）"
            )
        elif nl_chg_13w is not None and nl_chg_13w > 0:
            liq_light = "green"
            liq_reason = f"净流动性 13 周回升 {nl_chg_13w:+.0f}B，隔夜资金管道平稳"
        else:
            liq_light = "yellow"
            liq_reason = (
                f"净流动性 13 周小幅回落 {nl_chg_13w:+.0f}B，未触发 −1σ 警报"
                if nl_chg_13w is not None
                else "净流动性周度样本尚在积累"
            )
        dir_13w = "上行" if (nl_chg_13w or 0) > 10 else ("下行" if (nl_chg_13w or 0) < -10 else "平稳")
        p1 = {
            "key": "liquidity",
            "index": 1,
            "label": "央行与财政水位",
            "light": liq_light,
            "light_label": _light_label(liq_light),
            "primary_metric": f"净流动性 ${nl_now:,.0f}B",
            "percentile_10y": nl_pct,
            "direction_13w": dir_13w,
            "change_13w_text": f"13周 {nl_chg_13w:+.0f}B" if nl_chg_13w is not None else "13周待补",
            "as_of": nl_date,
            "released_at": nl_rel.isoformat(),
            "source": "合成数据" if demo else "FRED H.4.1",
            "fresh": nl_fresh,
            "caveat": "净流动性（WALCL−TGA−RRP）属从业者经验口径，按周四 16:30 ET 发布对齐，不单独驱动结论。",
            "summary": liq_reason,
            "details": [
                {"label": "联储总资产 WALCL", "value": f"${walcl[-1][1] / 1000.0:,.1f}B"},
                {"label": "财政部账户 TGA", "value": f"${wtregen[-1][1] / 1000.0:,.1f}B"},
                {"label": "隔夜逆回购 ON RRP", "value": f"${rrp[-1][1]:,.1f}B"},
                {
                    "label": "银行准备金 WRESBAL",
                    "value": (
                        f"${res_now_b:,.1f}B（13周 {res_chg_13w:+.0f}B）"
                        if res_now_b is not None and res_chg_13w is not None
                        else (f"${res_now_b:,.1f}B" if res_now_b is not None else "—")
                    ),
                },
                {
                    "label": "管道利差 SOFR−IORB",
                    "value": f"{sofr_iorb_bp:+.1f}bp（{sofr_as_of}）" if sofr_iorb_bp is not None else "—",
                },
            ],
        }
    else:
        p1 = {
            "key": "liquidity",
            "index": 1,
            "label": "央行与财政水位",
            "light": "unavailable",
            "light_label": "待补齐",
            "primary_metric": "等待 H.4.1 数据",
            "percentile_10y": None,
            "direction_13w": None,
            "change_13w_text": "等待同步",
            "as_of": None,
            "released_at": None,
            "source": "FRED H.4.1",
            "fresh": False,
            "caveat": "净流动性属从业者经验口径。",
            "summary": "尚未获取到已发布的联储 H.4.1 资产负债表数据。",
            "details": [],
        }

    # ================= ② 金融条件 =================
    if nfci:
        nf_date, nf_now, nf_rel = nfci[-1]
        nf_fresh = _fresh_within(nf_date, now, 16)
        nf_pct = causal_percentile([v for _, v, _ in nfci], lookback=520, min_samples=104)
        nf_chg_13w = round(nf_now - nfci[-14][1], 3) if len(nfci) >= 14 else None
        anf_now = anfci[-1][1] if anfci else None
        fast_tighten = nf_chg_13w is not None and nf_chg_13w >= 0.15
        if nf_now > 0 and fast_tighten:
            fc_light = "red"
            fc_summary = f"NFCI 为 {nf_now:+.2f}（高于0轴偏紧）且 13 周快速上行 {nf_chg_13w:+.2f}，左尾下行风险显著升高。"
        elif nf_now > 0 or fast_tighten:
            fc_light = "yellow"
            fc_summary = (
                f"NFCI 为 {nf_now:+.2f}（处于偏紧区间），金融条件承压。"
                if nf_now > 0
                else f"NFCI 虽在 0 轴下方（{nf_now:+.2f}），但 13 周快速收紧 {nf_chg_13w:+.2f}，须留意转紧迹象。"
            )
        elif nf_chg_13w is not None and nf_chg_13w <= 0.02:
            fc_light = "green"
            fc_summary = f"NFCI 为 {nf_now:+.2f}（宽松区间）且近 13 周平稳/转松（{nf_chg_13w:+.2f}），系统性压力低。"
        else:
            fc_light = "yellow"
            fc_summary = f"NFCI 位于宽松区（{nf_now:+.2f}），但近 13 周温和回升 {nf_chg_13w:+.2f}。"
        fc_dir = "收紧" if (nf_chg_13w or 0) > 0.03 else ("转松" if (nf_chg_13w or 0) < -0.03 else "平稳")
        p2 = {
            "key": "financial_conditions",
            "index": 2,
            "label": "金融条件（NFCI）",
            "light": fc_light,
            "light_label": _light_label(fc_light),
            "primary_metric": f"NFCI {nf_now:+.2f}",
            "percentile_10y": nf_pct,
            "direction_13w": fc_dir,
            "change_13w_text": f"13周 {nf_chg_13w:+.2f}" if nf_chg_13w is not None else "13周待补",
            "as_of": nf_date,
            "released_at": nf_rel.isoformat(),
            "source": "合成数据" if demo else "Chicago Fed / FRED",
            "fresh": nf_fresh,
            "caveat": "周三发布截至上周五数据（后续可能小幅修订）；数值 < 0 代表较历史均值宽松，> 0 代表收紧。",
            "summary": fc_summary,
            "details": [
                {"label": "NFCI 全国金融条件", "value": f"{nf_now:+.3f}"},
                {"label": "ANFCI 周期调整口径", "value": f"{anf_now:+.3f}" if anf_now is not None else "—"},
                {"label": "13 周变动（正=收紧）", "value": f"{nf_chg_13w:+.3f}" if nf_chg_13w is not None else "—"},
            ],
        }
    else:
        p2 = {
            "key": "financial_conditions",
            "index": 2,
            "label": "金融条件（NFCI）",
            "light": "unavailable",
            "light_label": "待补齐",
            "primary_metric": "等待 NFCI 数据",
            "percentile_10y": None,
            "direction_13w": None,
            "change_13w_text": "等待同步",
            "as_of": None,
            "released_at": None,
            "source": "Chicago Fed / FRED",
            "fresh": False,
            "caveat": "周频，每周三发布。",
            "summary": "尚未获取到已发布的 NFCI 金融条件指数。",
            "details": [],
        }

    # ================= ③ 信用利差 =================
    # 实测 BAMLH0A0HYM2 在 FRED 仅含近 3 年授权窗口，不足 10 年时自动以 BAA10Y 计算 10 年历史分位
    use_hy_primary = len(hy_oas) >= 2200
    credit_main = hy_oas if use_hy_primary else (baa10y if baa10y else hy_oas)
    credit_main_name = "高收益 OAS" if (use_hy_primary or not baa10y) else "Baa 企债利差"

    if credit_main:
        cr_date, cr_now, cr_rel = credit_main[-1]
        cr_fresh = _fresh_within(cr_date, now, 10)
        cr_pct = causal_percentile([v for _, v, _ in credit_main], lookback=2520, min_samples=500)
        cr_prior = _lookup_prior_by_days(credit_main, 91)
        cr_chg_bp = round((cr_now - cr_prior[1]) * 100.0, 0) if cr_prior else None

        hy_now = hy_oas[-1][1] if hy_oas else None
        hy_date = hy_oas[-1][0] if hy_oas else None
        hy_prior = _lookup_prior_by_days(hy_oas, 91) if hy_oas else None
        hy_chg_bp = round((hy_now - hy_prior[1]) * 100.0, 0) if (hy_now is not None and hy_prior) else None

        # 走阔幅度优先同时检查 HY OAS（若超 +100bp）与主口径
        widen_red = (hy_chg_bp is not None and hy_chg_bp >= 100) or (cr_chg_bp is not None and cr_chg_bp >= 100)
        if widen_red or (cr_pct is not None and cr_pct >= 80.0):
            cr_light = "red"
            cr_summary = (
                f"信用利差 13 周显著走阔（HY OAS {hy_chg_bp:+.0f}bp）"
                if (hy_chg_bp is not None and hy_chg_bp >= 100)
                else f"{credit_main_name} 处于 10 年高位（{cr_pct:.1f}% 分位），信用违约风险溢价抬升。"
            )
        elif cr_pct is not None and cr_pct < 10.0:
            # López-Salido et al. (2017, QJE): 信用利差过低代表情绪过热，标黄而非标绿
            cr_light = "yellow"
            cr_summary = f"{credit_main_name} 处于 10 年极低分位（{cr_pct:.1f}%），信用情绪偏过热、安全垫偏薄。"
        else:
            cr_light = "green"
            cr_summary = f"信用利差位于 10 年常规区间（{f'{cr_pct:.1f}% 分位' if cr_pct is not None else '正常范围'}），企业融资环境平稳。"

        display_metric = (
            f"HY OAS {hy_now:.2f}%"
            if hy_now is not None
            else f"Baa 利差 {cr_now:.2f}%"
        )
        display_chg = hy_chg_bp if hy_chg_bp is not None else cr_chg_bp
        cr_dir = "走阔" if (display_chg or 0) > 15 else ("收窄" if (display_chg or 0) < -15 else "平稳")
        caveat_text = (
            "ICE 高收益 OAS 在 FRED 仅提供近 3 年窗口，10 年分位自动采用 40 年完整的 BAA10Y 口径；分位 < 10% 标黄提示信用过热。"
            if not use_hy_primary and baa10y
            else "信用利差处于历史低分位（< 10%）标黄提示过热风险而非安全（López-Salido et al. 2017）。"
        )
        p3 = {
            "key": "credit",
            "index": 3,
            "label": "信用利差",
            "light": cr_light,
            "light_label": _light_label(cr_light),
            "primary_metric": display_metric,
            "percentile_10y": cr_pct,
            "direction_13w": cr_dir,
            "change_13w_text": f"13周 {display_chg:+.0f}bp" if display_chg is not None else "13周待补",
            "as_of": hy_date or cr_date,
            "released_at": cr_rel.isoformat(),
            "source": "合成数据" if demo else ("FRED BAA10Y + ICE OAS" if not use_hy_primary and baa10y else "FRED"),
            "fresh": cr_fresh,
            "caveat": caveat_text,
            "summary": cr_summary,
            "details": [
                {"label": "ICE 高收益 OAS", "value": f"{hy_now:.2f}%（{hy_date}）" if hy_now is not None else "—"},
                {"label": "Moody's Baa−10Y", "value": f"{baa10y[-1][1]:.2f}%（{baa10y[-1][0]}）" if baa10y else "—"},
                {"label": "10 年分位主口径", "value": f"{credit_main_name} · {cr_pct:.1f}%" if cr_pct is not None else "样本不足"},
                {"label": "HY OAS 13周变化", "value": f"{hy_chg_bp:+.0f}bp" if hy_chg_bp is not None else "—"},
            ],
        }
    else:
        p3 = {
            "key": "credit",
            "index": 3,
            "label": "信用利差",
            "light": "unavailable",
            "light_label": "待补齐",
            "primary_metric": "等待信用利差",
            "percentile_10y": None,
            "direction_13w": None,
            "change_13w_text": "等待同步",
            "as_of": None,
            "released_at": None,
            "source": "FRED",
            "fresh": False,
            "caveat": "高收益 OAS 与 Baa 企债利差。",
            "summary": "尚未获取到已发布的信用利差数据。",
            "details": [],
        }

    # ================= ④ 利率与曲线 =================
    curve_data = curve or {}
    ten_y = finite(curve_data.get("ten_year"))
    two_y = finite(curve_data.get("two_year"))
    three_m = finite(curve_data.get("three_month"))
    spread_10_2_bp = finite(curve_data.get("spread_bp"))
    spread_10_3m_bp = finite(curve_data.get("spread_10y_3m_bp"))
    if spread_10_3m_bp is None and t10y3m:
        spread_10_3m_bp = round(t10y3m[-1][1] * 100.0, 2)
    recession_prob = finite(curve_data.get("recession_prob_12m_pct"))
    if recession_prob is None and spread_10_3m_bp is not None:
        recession_prob = nyfed_recession_prob_pct(spread_10_3m_bp / 100.0)

    real_10y = dfii10[-1][1] if dfii10 else finite(curve_data.get("real_ten_year"))
    real_10y_date = dfii10[-1][0] if dfii10 else curve_data.get("as_of")
    real_10y_fresh = _fresh_within(real_10y_date, now, 10)
    real_10y_pct = causal_percentile([v for _, v, _ in dfii10], lookback=2520, min_samples=500) if dfii10 else None
    real_21d_bp = round((dfii10[-1][1] - dfii10[-22][1]) * 100.0, 0) if len(dfii10) >= 22 else None
    real_13w_prior = _lookup_prior_by_days(dfii10, 91) if dfii10 else None
    real_13w_bp = round((dfii10[-1][1] - real_13w_prior[1]) * 100.0, 0) if (dfii10 and real_13w_prior) else None

    # 检查近 6 个月（约 126 个交易日）是否仍处于倒挂或刚解除倒挂
    currently_inverted = spread_10_3m_bp is not None and spread_10_3m_bp < 0
    recent_inverted_6m = False
    if t10y3m:
        recent_126 = [v for _, v, _ in t10y3m[-126:]]
        recent_inverted_6m = any(v < 0 for v in recent_126)
    elif currently_inverted:
        recent_inverted_6m = True

    rates_as_of = curve_data.get("as_of") or real_10y_date
    if ten_y is not None or real_10y is not None:
        rates_fresh = _fresh_within(rates_as_of, now, 10)
        if real_21d_bp is not None and real_21d_bp >= 50:
            rt_light = "red"
            rt_summary = f"10Y 实际利率近 21 日急升 {real_21d_bp:+.0f}bp（至 {real_10y:.2f}%），对风险资产估值形成明显压制。"
        elif currently_inverted:
            rt_light = "yellow"
            rt_summary = f"10Y−3M 曲线倒挂（{spread_10_3m_bp:+.0f}bp，NY Fed 12M 衰退概率 {recession_prob:.1f}%），中长期周期承压。"
        elif recent_inverted_6m:
            rt_light = "yellow"
            rt_summary = "10Y−3M 曲线近 6 个月内曾倒挂，历史上倒挂解除初期常伴随降息与增长放缓（倒挂解除≠风险解除）。"
        elif real_21d_bp is not None and real_21d_bp >= 25:
            rt_light = "yellow"
            rt_summary = f"10Y 实际利率近 21 日抬升 {real_21d_bp:+.0f}bp，需留意高估值成长股承压。"
        else:
            rt_light = "green"
            rt_summary = (
                f"10Y−3M 利差为正（{spread_10_3m_bp:+.0f}bp），10Y 实际利率 {real_10y:.2f}% 走势平稳。"
                if spread_10_3m_bp is not None and real_10y is not None
                else "利率曲线保持正向且长端实际利率未出现急升。"
            )
        rt_dir = "上行" if (real_13w_bp or 0) > 15 else ("下行" if (real_13w_bp or 0) < -15 else "平稳")
        p4 = {
            "key": "rates",
            "index": 4,
            "label": "利率与曲线",
            "light": rt_light,
            "light_label": _light_label(rt_light),
            "primary_metric": (
                f"实际10Y {real_10y:.2f}%"
                if real_10y is not None
                else f"10Y {ten_y:.2f}%"
            ),
            "percentile_10y": real_10y_pct,
            "direction_13w": rt_dir,
            "change_13w_text": (
                f"21日 {real_21d_bp:+.0f}bp"
                if real_21d_bp is not None
                else (f"13周 {real_13w_bp:+.0f}bp" if real_13w_bp is not None else "待补")
            ),
            "as_of": rates_as_of,
            "released_at": dfii10[-1][2].isoformat() if dfii10 else None,
            "source": "合成数据" if demo else "美国财政部 + FRED DFII10",
            "fresh": rates_fresh,
            "caveat": "10Y−3M 衰退概率采用纽约联储 Probit 基准公式 Φ(-0.5333 - 0.6330×利差)，仅作周期警示不做择时。",
            "summary": rt_summary,
            "details": [
                {"label": "10Y / 2Y / 3M 名义利率", "value": f"{ten_y:.2f}% / {two_y:.2f}% / {f'{three_m:.2f}%' if three_m is not None else '—'}" if ten_y is not None and two_y is not None else "—"},
                {"label": "10Y−3M 利差", "value": f"{spread_10_3m_bp:+.0f}bp" if spread_10_3m_bp is not None else "—"},
                {"label": "NY Fed 12M 衰退概率", "value": f"{recession_prob:.1f}%" if recession_prob is not None else "—"},
                {"label": "10Y 实际利率 DFII10", "value": f"{real_10y:.2f}%（21日 {real_21d_bp:+.0f}bp）" if real_10y is not None and real_21d_bp is not None else (f"{real_10y:.2f}%" if real_10y is not None else "—")},
                {"label": "10Y−2Y 期限利差", "value": f"{spread_10_2_bp:+.0f}bp" if spread_10_2_bp is not None else "—"},
            ],
        }
    else:
        p4 = {
            "key": "rates",
            "index": 4,
            "label": "利率与曲线",
            "light": "unavailable",
            "light_label": "待补齐",
            "primary_metric": "等待利率数据",
            "percentile_10y": None,
            "direction_13w": None,
            "change_13w_text": "等待同步",
            "as_of": None,
            "released_at": None,
            "source": "美国财政部 + FRED",
            "fresh": False,
            "caveat": "美国财政部日度平价曲线与 FRED 10Y TIPS 实际利率。",
            "summary": "尚未获取到有效美债曲线与实际利率数据。",
            "details": [],
        }

    # ================= ⑤ 趋势与广度（全市场基准 ETF，绝不拿自选池冒充） =================
    bm = benchmark_frames or {}
    spy_dates, spy_closes = _extract_etf_close_map(bm.get("SPY.US"))
    qqq_dates, qqq_closes = _extract_etf_close_map(bm.get("QQQ.US"))
    rsp_dates, rsp_closes = _extract_etf_close_map(bm.get("RSP.US"))
    iwm_dates, iwm_closes = _extract_etf_close_map(bm.get("IWM.US"))
    hyg_dates, hyg_closes = _extract_etf_close_map(bm.get("HYG.US"))
    ief_dates, ief_closes = _extract_etf_close_map(bm.get("IEF.US"))

    spy_hv20 = _compute_spy_hv20(spy_closes)
    spy_above_ma200: bool | None = None
    spy_ma200_gap: float | None = None
    spy_ma210_gap: float | None = None
    spy_mom_12_1: float | None = None
    qqq_above_ma200: bool | None = None
    qqq_ma200_gap: float | None = None
    spy_pos_pct: float | None = None

    if len(spy_closes) >= 200:
        ma200 = float(np.mean(spy_closes[-200:]))
        spy_above_ma200 = spy_closes[-1] >= ma200
        spy_ma200_gap = round((spy_closes[-1] / ma200 - 1.0) * 100.0, 2)
        if len(spy_closes) >= 210:
            ma210 = float(np.mean(spy_closes[-210:]))
            spy_ma210_gap = round((spy_closes[-1] / ma210 - 1.0) * 100.0, 2)
        if len(spy_closes) >= 252:
            spy_mom_12_1 = round((spy_closes[-22] / spy_closes[-252] - 1.0) * 100.0, 1)
        spy_pos_pct = causal_percentile(spy_closes, lookback=1000, min_samples=200)

    if len(qqq_closes) >= 200:
        qma200 = float(np.mean(qqq_closes[-200:]))
        qqq_above_ma200 = qqq_closes[-1] >= qma200
        qqq_ma200_gap = round((qqq_closes[-1] / qma200 - 1.0) * 100.0, 2)

    rsp_spy = _compute_ratio_change_63d(rsp_dates, rsp_closes, spy_dates, spy_closes)
    iwm_spy = _compute_ratio_change_63d(iwm_dates, iwm_closes, spy_dates, spy_closes)
    hyg_ief = _compute_ratio_change_63d(hyg_dates, hyg_closes, ief_dates, ief_closes)

    missing_bm = [
        sym.replace(".US", "")
        for sym, seq in (
            ("SPY.US", spy_closes),
            ("QQQ.US", qqq_closes),
            ("RSP.US", rsp_closes),
            ("IWM.US", iwm_closes),
            ("HYG.US", hyg_closes),
            ("IEF.US", ief_closes),
        )
        if len(seq) < 64
    ]

    if spy_above_ma200 is not None:
        tb_as_of = spy_dates[-1]
        tb_fresh = _fresh_within(tb_as_of, now, 7)
        hyg_down = hyg_ief["available"] and hyg_ief["change_63d_pct"] < -0.5
        rsp_down = rsp_spy["available"] and rsp_spy["change_63d_pct"] < -1.0
        iwm_down = iwm_spy["available"] and iwm_spy["change_63d_pct"] < -1.0
        breadth_diverging = rsp_down and iwm_down

        if (not spy_above_ma200 and (hyg_down or qqq_above_ma200 is False)) or (
            not spy_above_ma200 and not hyg_ief["available"]
        ):
            tb_light = "red"
            tb_summary = (
                f"SPY 跌破 200 日线（{spy_ma200_gap:+.1f}%）"
                + ("且 HYG/IEF 风险偏好下行，大盘趋势承压。" if hyg_down else "且科技基准走弱，大盘趋势偏空。")
            )
            trend_axis = "down"
        elif spy_above_ma200 and not breadth_diverging and not hyg_down:
            tb_light = "green"
            tb_summary = f"SPY 站稳 200 日线（{spy_ma200_gap:+.1f}%），基准参与度与信用偏好同步健康。"
            trend_axis = "up"
        else:
            tb_light = "yellow"
            if not spy_above_ma200:
                tb_summary = f"SPY 略低于 200 日线（{spy_ma200_gap:+.1f}%），处于多空拉锯观察期。"
                trend_axis = "down"
            elif breadth_diverging:
                tb_summary = f"SPY 虽在 200 日线上方（{spy_ma200_gap:+.1f}%），但等权 RSP/SPY 与小盘 IWM/SPY 双双走弱，存在广度背离。"
                trend_axis = "up"
            else:
                tb_summary = f"SPY 位于 200 日线上方（{spy_ma200_gap:+.1f}%），但部分风险偏好或广度指标出现分化。"
                trend_axis = "up"

        spy_chg_63d = (
            round((spy_closes[-1] / spy_closes[-64] - 1.0) * 100.0, 1)
            if len(spy_closes) >= 64
            else None
        )
        tb_dir = "上行" if (spy_chg_63d or 0) > 2 else ("下行" if (spy_chg_63d or 0) < -2 else "震荡")
        caveat_bm = (
            f"基于全市场基准 ETF 已确认日线（暂缺：{', '.join(missing_bm)}），不混用自选池。"
            if missing_bm
            else "基于 SPY/QQQ/RSP/IWM/HYG/IEF 六只全市场基准 ETF 已确认日线，避免自选池选择偏差。"
        )
        p5 = {
            "key": "trend_breadth",
            "index": 5,
            "label": "趋势与广度",
            "light": tb_light,
            "light_label": _light_label(tb_light),
            "primary_metric": f"SPY 相对年线 {spy_ma200_gap:+.1f}%",
            "percentile_10y": spy_pos_pct,
            "direction_13w": tb_dir,
            "change_13w_text": f"SPY 13周 {spy_chg_63d:+.1f}%" if spy_chg_63d is not None else "13周待补",
            "as_of": tb_as_of,
            "released_at": None,
            "source": "合成基准日线" if demo else "LongPort 基准 ETF",
            "fresh": tb_fresh,
            "caveat": caveat_bm,
            "summary": tb_summary,
            "details": [
                {"label": "SPY 相对 MA200 / 10月线", "value": f"{spy_ma200_gap:+.1f}% / {f'{spy_ma210_gap:+.1f}%' if spy_ma210_gap is not None else '—'}"},
                {"label": "SPY 12-1 月动量", "value": f"{spy_mom_12_1:+.1f}%" if spy_mom_12_1 is not None else "—"},
                {"label": "QQQ 相对 MA200", "value": f"{qqq_ma200_gap:+.1f}%" if qqq_ma200_gap is not None else "—"},
                {"label": "等权广度 RSP/SPY（13周）", "value": f"{rsp_spy['change_63d_pct']:+.1f}%" if rsp_spy["available"] else "待补齐"},
                {"label": "小盘广度 IWM/SPY（13周）", "value": f"{iwm_spy['change_63d_pct']:+.1f}%" if iwm_spy["available"] else "待补齐"},
                {"label": "风险偏好 HYG/IEF（13周）", "value": f"{hyg_ief['change_63d_pct']:+.1f}%" if hyg_ief["available"] else "待补齐"},
            ],
        }
    else:
        trend_axis = "unavailable"
        p5 = {
            "key": "trend_breadth",
            "index": 5,
            "label": "趋势与广度",
            "light": "unavailable",
            "light_label": "待补齐",
            "primary_metric": "等待基准 ETF 日线",
            "percentile_10y": None,
            "direction_13w": None,
            "change_13w_text": "等待同步",
            "as_of": None,
            "released_at": None,
            "source": "LongPort 基准 ETF",
            "fresh": False,
            "caveat": "使用全市场基准 ETF（SPY/QQQ/RSP/IWM/HYG/IEF）已确认日线。",
            "summary": "正在补齐 SPY 等全市场基准 ETF 的 200 日历史日线。",
            "details": [],
        }

    # ================= ⑥ 波动与美元 =================
    if vix or dxy:
        vix_date, vix_now, vix_rel = vix[-1] if vix else (None, None, None)
        dxy_date, dxy_now, dxy_rel = dxy[-1] if dxy else (None, None, None)
        vix_pct = causal_percentile([v for _, v, _ in vix], lookback=2520, min_samples=500) if vix else None
        vix_prior = _lookup_prior_by_days(vix, 91) if vix else None
        vix_chg_13w = round(vix_now - vix_prior[1], 2) if (vix_now is not None and vix_prior) else None

        dxy_prior = _lookup_prior_by_days(dxy, 91) if dxy else None
        dxy_chg_13w_pct = (
            round((dxy_now / dxy_prior[1] - 1.0) * 100.0, 2)
            if (dxy_now is not None and dxy_prior and dxy_prior[1] > 0)
            else None
        )

        # VRP ≈ VIX² − (SPY HV20)²（以年化百分点平方衡量方差溢价，同时给出直观 VIX−HV20）
        vrp_var: float | None = None
        vrp_vol_diff: float | None = None
        if vix_now is not None and spy_hv20 is not None:
            vrp_var = round(vix_now * vix_now - spy_hv20 * spy_hv20, 1)
            vrp_vol_diff = round(vix_now - spy_hv20, 1)

        vf_as_of = vix_date or dxy_date
        vf_fresh = _fresh_within(vf_as_of, now, 10)
        if (vix_now is not None and vix_now > 25.0) or (vrp_var is not None and vrp_var < 0.0):
            vf_light = "red"
            if vix_now is not None and vix_now > 25.0 and vrp_var is not None and vrp_var < 0.0:
                vf_summary = f"VIX 升至 {vix_now:.1f}（> 25）且方差溢价转负（VRP {vrp_var:+.0f}），市场处于高波动冲击态。"
            elif vix_now is not None and vix_now > 25.0:
                vf_summary = f"VIX 升至 {vix_now:.1f}（高于 25 警戒线），避险情绪升温、组合回撤风险加大。"
            else:
                vf_summary = f"实际波动超过隐含波动（VRP {vrp_var:+.0f} < 0），市场短期波动冲击偏剧烈。"
        elif (dxy_chg_13w_pct is not None and dxy_chg_13w_pct >= 5.0) or (
            vix_now is not None and vix_now >= 20.0
        ):
            vf_light = "yellow"
            vf_summary = (
                f"广义美元 13 周急涨 {dxy_chg_13w_pct:+.1f}%（≥ +5%），对全球美元流动性构成边际收紧压力。"
                if (dxy_chg_13w_pct is not None and dxy_chg_13w_pct >= 5.0)
                else f"VIX 处于 {vix_now:.1f}（20–25 偏高区间），市场波动率有所抬升。"
            )
        else:
            vf_light = "green"
            vf_summary = (
                f"VIX 为 {vix_now:.1f}（< 20）且美元走势温和，波动与汇率环境平稳。"
                if vix_now is not None
                else "美元指数变动温和，汇率压力偏低。"
            )
        vf_dir = "升温" if (vix_chg_13w or 0) > 2 else ("回落" if (vix_chg_13w or 0) < -2 else "平稳")
        p6 = {
            "key": "volatility_fx",
            "index": 6,
            "label": "波动与美元",
            "light": vf_light,
            "light_label": _light_label(vf_light),
            "primary_metric": f"VIX {vix_now:.1f}" if vix_now is not None else f"美元 {dxy_now:.1f}",
            "percentile_10y": vix_pct,
            "direction_13w": vf_dir,
            "change_13w_text": (
                f"美元13周 {dxy_chg_13w_pct:+.1f}%"
                if dxy_chg_13w_pct is not None
                else (f"VIX 13周 {vix_chg_13w:+.1f}" if vix_chg_13w is not None else "待补")
            ),
            "as_of": vf_as_of,
            "released_at": (vix_rel or dxy_rel).isoformat() if (vix_rel or dxy_rel) else None,
            "source": "合成数据" if demo else "FRED VIXCLS + DTWEXBGS",
            "fresh": vf_fresh,
            "caveat": "VRP ≈ VIX² − (SPY 20日年化波动)²，转负说明实际波动已击穿期权隐含预期（Bollerslev et al. 2009）。",
            "summary": vf_summary,
            "details": [
                {"label": "CBOE VIX 恐慌指数", "value": f"{vix_now:.2f}（{vix_date}）" if vix_now is not None else "—"},
                {"label": "SPY 20日年化波动 HV20", "value": f"{spy_hv20:.1f}%" if spy_hv20 is not None else "—"},
                {
                    "label": "方差溢价 VRP（VIX²−HV20²）",
                    "value": f"{vrp_var:+.0f}（VIX−HV20 {vrp_vol_diff:+.1f}pp）" if vrp_var is not None else "—",
                },
                {
                    "label": "广义美元 DTWEXBGS",
                    "value": f"{dxy_now:.2f}（13周 {dxy_chg_13w_pct:+.1f}%）" if dxy_now is not None and dxy_chg_13w_pct is not None else (f"{dxy_now:.2f}" if dxy_now is not None else "—"),
                },
            ],
        }
    else:
        p6 = {
            "key": "volatility_fx",
            "index": 6,
            "label": "波动与美元",
            "light": "unavailable",
            "light_label": "待补齐",
            "primary_metric": "等待 VIX / 美元",
            "percentile_10y": None,
            "direction_13w": None,
            "change_13w_text": "等待同步",
            "as_of": None,
            "released_at": None,
            "source": "FRED",
            "fresh": False,
            "caveat": "VIX 恐慌指数、方差风险溢价与广义美元指数。",
            "summary": "尚未获取到已发布的 VIX 与美元指数数据。",
            "details": [],
        }

    pillars = [p1, p2, p3, p4, p5, p6]
    available_count = sum(1 for p in pillars if p["light"] != "unavailable")
    red_count = sum(1 for p in pillars if p["light"] == "red")
    yellow_count = sum(1 for p in pillars if p["light"] == "yellow")
    green_count = sum(1 for p in pillars if p["light"] == "green")

    # 流动性方向合成（① 央行水位 + ② 金融条件 + ③ 信用利差）
    liq_lights = [p["light"] for p in (p1, p2, p3) if p["light"] != "unavailable"]
    if len(liq_lights) < 2:
        liquidity_axis = "unavailable"
        liquidity_label = "待确认"
    else:
        score_map = {"green": 1, "yellow": 0, "red": -1}
        liq_sum = sum(score_map[x] for x in liq_lights)
        if "red" in liq_lights or liq_sum < 0:
            liquidity_axis = "tightening"
            liquidity_label = "流动性偏紧"
        else:
            liquidity_axis = "easing"
            liquidity_label = "流动性平稳/宽松"

    trend_label = {"up": "指数多头", "down": "指数承压", "unavailable": "待确认"}[trend_axis]

    # 四象限合成：「流动性方向 × 指数趋势」
    if liquidity_axis == "easing" and trend_axis == "up":
        q_code, q_label, q_tone = "tailwind", "顺风", "positive"
        q_desc = "宏观流动性平稳偏松且指数站稳长期均线，环境整体友好，按个股计划与纪律正常跟踪即可。"
    elif liquidity_axis == "tightening" and trend_axis == "up":
        q_code, q_label, q_tone = "divergence", "背离 · 警惕见顶", "warning"
        q_desc = "指数仍在均线上方，但流动性、金融条件或信用已出现收紧信号，警惕高位背离与追高风险。"
    elif liquidity_axis == "easing" and trend_axis == "down":
        q_code, q_label, q_tone = "repair", "修复 · 观察见底", "neutral"
        q_desc = "宏观流动性与金融条件未见明显恶化但指数走势偏弱，适合耐心观察大盘筑底与右侧企稳信号。"
    elif liquidity_axis == "tightening" and trend_axis == "down":
        q_code, q_label, q_tone = "headwind", "逆风", "danger"
        q_desc = "宏观流动性偏紧且指数跌破长期趋势线，市场下行尾部风险偏高，优先严守仓位与个股止损纪律。"
    else:
        q_code, q_label, q_tone = "unavailable", "数据补齐中", "muted"
        q_desc = "等待 FRED 宏观序列与基准 ETF 日线补齐后自动合成市场大势四象限。"

    if available_count == 0:
        risk_level_label, risk_level_tone = "等待宏观数据", "muted"
    elif red_count >= 3:
        risk_level_label, risk_level_tone = "下行风险偏高", "danger"
    elif red_count >= 1:
        risk_level_label, risk_level_tone = "局部压力提示", "warning"
    else:
        risk_level_label, risk_level_tone = "常规风险水位", "positive"

    # 流动性与信用同时亮红灯时提示流动性螺旋（Brunnermeier & Pedersen 2009）
    spiral_alert = p3["light"] == "red" and p6["light"] == "red"
    alerts: list[str] = []
    if spiral_alert:
        alerts.append("高波动与信用利差走阔同时亮红灯，需高度警惕流动性螺旋放大短期回撤（Brunnermeier & Pedersen 2009）。")
    if p1["light"] == "red" and sofr_iorb_bp is not None and sofr_iorb_bp > 0:
        alerts.append(f"货币市场隔夜融资利率高于准备金利率（SOFR−IORB {sofr_iorb_bp:+.1f}bp），关注短期资金管道紧张。")
    if currently_inverted or recent_inverted_6m:
        alerts.append("10Y−3M 曲线处于倒挂或近 6 个月内刚解除倒挂，历史经验提示「倒挂解除≠衰退风险解除」。")

    latest_dates = [p["as_of"] for p in pillars if p.get("as_of")]
    as_of = max(latest_dates) if latest_dates else None

    return {
        "available": available_count > 0,
        "rule_version": MACRO_RULE_VERSION,
        "source": source_label,
        "fetched_at": (fred_bundle or {}).get("fetched_at"),
        "refresh_failed": bool((fred_bundle or {}).get("refresh_failed")),
        "partial_errors": errors,
        "as_of": as_of,
        "quadrant": {
            "code": q_code,
            "label": q_label,
            "tone": q_tone,
            "liquidity_axis": liquidity_axis,
            "liquidity_label": liquidity_label,
            "trend_axis": trend_axis,
            "trend_label": trend_label,
            "description": q_desc,
        },
        "risk_gauge": {
            "red_count": red_count,
            "yellow_count": yellow_count,
            "green_count": green_count,
            "available_count": available_count,
            "total_count": 6,
            "label": risk_level_label,
            "tone": risk_level_tone,
        },
        "alerts": alerts,
        "real_rate": {
            "ten_year_real": real_10y,
            "as_of": real_10y_date,
            "fresh": real_10y_fresh,
            "change_21d_bp": real_21d_bp,
        },
        "pillars": pillars,
        "disclaimer": MACRO_DISCLAIMER,
    }


def demo_fred_bundle(now: datetime) -> dict:
    """为演示模式生成完全确定性的合成宏观序列（无外部联网，标注合成数据）。"""
    today = now.astimezone(NY).date() - timedelta(days=3)
    # 生成近 600 周（~11.5 年）周频与 2700 个工作日合成历史，确保 10 年因果分位与 13 周变化可完整演示
    wed_offset = (today.weekday() - 2) % 7
    last_wed = today - timedelta(days=wed_offset)
    fri_offset = (today.weekday() - 4) % 7
    last_fri = today - timedelta(days=fri_offset)

    weeks_wed = [last_wed - timedelta(weeks=i) for i in range(560, -1, -1)]
    weeks_fri = [last_fri - timedelta(weeks=i) for i in range(560, -1, -1)]
    bdays = pd.bdate_range(end=pd.Timestamp(today), periods=2650)
    days_str = [ts.date().isoformat() for ts in bdays]

    rng = np.random.default_rng(20261123)
    w_len = len(weeks_wed)
    d_len = len(days_str)

    walcl_vals = 4_200_000 + np.linspace(0, 2_750_000, w_len) + np.sin(np.linspace(0, 8, w_len)) * 320_000
    tga_vals = 450_000 + np.linspace(0, 310_000, w_len) + np.cos(np.linspace(0, 10, w_len)) * 90_000
    wres_vals = 2_100_000 + np.linspace(0, 1_050_000, w_len) + np.sin(np.linspace(0, 7, w_len)) * 180_000
    # 末段 13 周净流动性温和扩张（示例顺风/温和环境）
    walcl_vals[-14:] += np.linspace(0, 110_000, 14)
    tga_vals[-14:] -= np.linspace(0, 35_000, 14)

    rrp_vals = np.clip(180.0 + np.sin(np.linspace(0, 12, d_len)) * 140.0 + np.linspace(0, -140, d_len), 8.0, 2200.0)
    sofr_vals = np.clip(3.8 + np.sin(np.linspace(0, 6, d_len)) * 1.2, 0.1, 5.5)
    iorb_vals = sofr_vals + 0.04  # 正常管道状态 SOFR < IORB

    nfci_vals = -0.35 + np.sin(np.linspace(0, 9, len(weeks_fri))) * 0.35 + rng.normal(0, 0.03, len(weeks_fri))
    nfci_vals[-14:] = np.linspace(-0.36, -0.44, 14)
    anfci_vals = nfci_vals - 0.04

    baa_vals = np.clip(2.05 + np.sin(np.linspace(0, 11, d_len)) * 0.65, 1.1, 4.5)
    baa_vals[-65:] = np.linspace(1.92, 1.84, 65)
    hy_vals = np.clip(baa_vals[-780:] + 1.65, 2.5, 9.0)

    vix_vals = np.clip(18.5 + np.sin(np.linspace(0, 18, d_len)) * 6.0 + rng.normal(0, 1.2, d_len), 11.0, 48.0)
    vix_vals[-25:] = np.linspace(17.8, 16.4, 25)
    dxy_vals = 108.0 + np.linspace(0, 11.0, d_len) + np.sin(np.linspace(0, 8, d_len)) * 4.0
    dxy_vals[-65:] = np.linspace(118.2, 119.1, 65)
    dfii_vals = np.clip(1.4 + np.linspace(0, 0.65, d_len) + np.sin(np.linspace(0, 7, d_len)) * 0.45, -0.8, 3.2)
    dfii_vals[-25:] = np.linspace(1.96, 1.88, 25)
    t10y3m_vals = np.clip(0.85 + np.sin(np.linspace(0, 9, d_len)) * 1.1, -1.5, 2.5)
    t10y3m_vals[-140:] = np.linspace(0.28, 0.42, 140)

    return {
        "source": "合成宏观数据",
        "fetched_at": now.isoformat(),
        "series": {
            "WALCL": [[d.isoformat(), round(float(v), 1)] for d, v in zip(weeks_wed, walcl_vals)],
            "WTREGEN": [[d.isoformat(), round(float(v), 1)] for d, v in zip(weeks_wed, tga_vals)],
            "WRESBAL": [[d.isoformat(), round(float(v), 1)] for d, v in zip(weeks_wed, wres_vals)],
            "RRPONTSYD": [[d, round(float(v), 3)] for d, v in zip(days_str, rrp_vals)],
            "SOFR": [[d, round(float(v), 2)] for d, v in zip(days_str, sofr_vals)],
            "IORB": [[d, round(float(v), 2)] for d, v in zip(days_str, iorb_vals)],
            "NFCI": [[d.isoformat(), round(float(v), 3)] for d, v in zip(weeks_fri, nfci_vals)],
            "ANFCI": [[d.isoformat(), round(float(v), 3)] for d, v in zip(weeks_fri, anfci_vals)],
            "BAMLH0A0HYM2": [[d, round(float(v), 2)] for d, v in zip(days_str[-len(hy_vals):], hy_vals)],
            "BAA10Y": [[d, round(float(v), 2)] for d, v in zip(days_str, baa_vals)],
            "VIXCLS": [[d, round(float(v), 2)] for d, v in zip(days_str, vix_vals)],
            "DTWEXBGS": [[d, round(float(v), 3)] for d, v in zip(days_str, dxy_vals)],
            "DFII10": [[d, round(float(v), 2)] for d, v in zip(days_str, dfii_vals)],
            "T10Y3M": [[d, round(float(v), 2)] for d, v in zip(days_str, t10y3m_vals)],
        },
        "errors": {},
        "ok_count": len(FRED_SERIES_IDS),
        "total_count": len(FRED_SERIES_IDS),
        "refresh_failed": False,
    }
