"""Public rates and security-level valuation inputs for long-horizon reviews."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from xml.etree import ElementTree

import httpx

from .calendar import NY
from .indicators import finite

TREASURY_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
YAHOO_GOLD_URLS = (
    "https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF",
    "https://query2.finance.yahoo.com/v8/finance/chart/GC%3DF",
)
EASTMONEY_GOLD_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
PUBLIC_MARKET_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# 纽约联储 10Y-3M 单变量 Probit 12 个月衰退概率基准参数（Estrella & Mishkin 1998; NY Fed 1959-2009 估计口径）
NYFED_PROBIT_ALPHA = -0.5333
NYFED_PROBIT_BETA = -0.6330


def nyfed_recession_prob_pct(spread_10y_3m_pct: float | None) -> float | None:
    """按纽约联储 10Y-3M Probit 基准公式计算未来 12 个月美国衰退参考概率（%）。"""
    spread = finite(spread_10y_3m_pct)
    if spread is None:
        return None
    z = NYFED_PROBIT_ALPHA + NYFED_PROBIT_BETA * spread
    prob = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return round(prob * 100.0, 1)


def treasury_curve_observations(xml: bytes, today: date) -> dict[str, tuple[float, float, float | None]]:
    """解析美国财政部 XML 中的 2Y / 10Y / 3M 日度国债平价收益率，仅保留 <= today 的观测日。"""
    rows: dict[str, tuple[float, float, float | None]] = {}
    for row in ElementTree.fromstring(xml).iterfind(".//{*}properties"):
        day = row.findtext("{*}NEW_DATE", "")[:10]
        two = finite(row.findtext("{*}BC_2YEAR"))
        ten = finite(row.findtext("{*}BC_10YEAR"))
        three = finite(row.findtext("{*}BC_3MONTH"))
        if day and date.fromisoformat(day) <= today and two is not None and ten is not None:
            rows[day] = (two, ten, three)
    return rows


def treasury_observations(xml: bytes, today: date) -> dict[str, tuple[float, float]]:
    """向后兼容的 2Y / 10Y 收益率解析入口。"""
    return {day: (two, ten) for day, (two, ten, _) in treasury_curve_observations(xml, today).items()}


async def fetch_curve(now: datetime) -> dict:
    today = now.astimezone(NY).date()
    rows: dict[str, tuple[float, float, float | None]] = {}
    month = today.replace(day=1)
    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
        for _ in range(3):
            fetched_month = False
            last_err: Exception | None = None
            for attempt in range(2):
                try:
                    response = await client.get(
                        TREASURY_URL,
                        params={
                            "data": "daily_treasury_yield_curve",
                            "field_tdr_date_value_month": month.strftime("%Y%m"),
                        },
                    )
                    response.raise_for_status()
                    rows.update(treasury_curve_observations(response.content, today))
                    fetched_month = True
                    break
                except (httpx.HTTPError, ElementTree.ParseError, ValueError) as exc:
                    last_err = exc
                    if attempt == 0 and isinstance(exc, httpx.HTTPError):
                        continue
                    break
            if not fetched_month:
                if rows:
                    break  # Keep the current pair even if the older comparison is unavailable.
                if last_err is not None:
                    raise last_err
            if len(rows) >= 22:
                break
            month = (month - timedelta(days=1)).replace(day=1)
    if not rows:
        raise ValueError("缺少同日美债利率")
    return curve_summary(rows)


def curve_summary(rows: dict) -> dict:
    dates = sorted(rows)
    day = dates[-1]
    latest = rows[day]
    two, ten = latest[0], latest[1]
    three = latest[2] if len(latest) >= 3 else None
    prior = dates[-22] if len(dates) >= 22 else None
    spread_10y_3m_bp = round((ten - three) * 100, 2) if three is not None else None
    recession_prob = nyfed_recession_prob_pct(ten - three) if three is not None else None
    return {
        "as_of": day,
        "three_month": three,
        "two_year": two,
        "ten_year": ten,
        "spread_bp": round((ten - two) * 100, 2),
        "spread_10y_3m_bp": spread_10y_3m_bp,
        "recession_prob_12m_pct": recession_prob,
        "prior_date": prior,
        "ten_change_bp": round((ten - rows[prior][1]) * 100, 2) if prior else None,
    }


def research_context(
    valuation: dict,
    curve: dict,
    now: datetime,
    demo: bool,
    real_ten_year: float | None = None,
    real_rate_fresh: bool = False,
) -> dict:
    fetched = valuation.get("fetched_at")
    day = curve.get("as_of")
    valuation_ok = bool(
        fetched and timedelta(0) <= now - datetime.fromisoformat(fetched) <= timedelta(days=4)
    )
    curve_ok = bool(day and 0 <= (now.astimezone(NY).date() - date.fromisoformat(day)).days <= 7)
    pe = valuation.get("pe_ttm")
    earnings_yield = 100 / pe if pe and pe > 0 and valuation_ok else None
    ten = curve.get("ten_year")
    eff_real = finite(real_ten_year if real_ten_year is not None else curve.get("real_ten_year"))
    eff_real_fresh = bool(real_rate_fresh or (curve.get("real_ten_year") is not None and curve_ok))
    curve_payload = {
        "three_month": None,
        "spread_10y_3m_bp": None,
        "recession_prob_12m_pct": None,
        **curve,
        "real_ten_year": eff_real,
        "source": "合成利率" if demo else "美国财政部",
        "fresh": curve_ok,
    }
    return {
        "valuation": {**valuation, "source": "合成估值" if demo else "LongPort", "fresh": valuation_ok},
        "curve": curve_payload,
        "earnings_yield_pct": earnings_yield,
        "yield_gap_pp": earnings_yield - ten
        if earnings_yield is not None and curve_ok and ten is not None
        else None,
        "real_ten_year": eff_real if eff_real_fresh else None,
        "real_yield_gap_pp": round(earnings_yield - eff_real, 4)
        if earnings_yield is not None and eff_real is not None and eff_real_fresh
        else None,
    }


def _positive_finite(value: object) -> float | None:
    num = finite(value)
    return num if num is not None and num > 0 else None


def parse_yahoo_comex_gold(payload: dict, now: datetime) -> dict:
    """解析 Yahoo Finance COMEX 黄金主力期货（GC=F）2 个月日线与最新价。"""
    chart = payload.get("chart") if isinstance(payload, dict) else None
    results = chart.get("result") if isinstance(chart, dict) else None
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        raise ValueError("Yahoo COMEX 黄金返回缺少 chart.result")
    entry = results[0]
    meta = entry.get("meta") if isinstance(entry.get("meta"), dict) else {}
    timestamps = entry.get("timestamp") if isinstance(entry.get("timestamp"), list) else []
    indicators = entry.get("indicators") if isinstance(entry.get("indicators"), dict) else {}
    quote_list = indicators.get("quote") if isinstance(indicators.get("quote"), list) else []
    quote = quote_list[0] if quote_list and isinstance(quote_list[0], dict) else {}
    closes = quote.get("close") if isinstance(quote.get("close"), list) else []
    highs = quote.get("high") if isinstance(quote.get("high"), list) else []
    lows = quote.get("low") if isinstance(quote.get("low"), list) else []

    # COMEX 电子盘于美东 18:00 切换至下一交易日，允许 +1 日边界并过滤异常远期时间
    max_day = now.astimezone(NY).date() + timedelta(days=1)
    by_day: dict[str, tuple[float, float | None, float | None]] = {}
    for idx, ts in enumerate(timestamps):
        if not isinstance(ts, (int, float)) or not math.isfinite(ts):
            continue
        close_val = _positive_finite(closes[idx]) if idx < len(closes) else None
        if close_val is None:
            continue
        day_date = datetime.fromtimestamp(float(ts), tz=timezone.utc).astimezone(NY).date()
        if day_date > max_day:
            continue
        high_val = _positive_finite(highs[idx]) if idx < len(highs) else None
        low_val = _positive_finite(lows[idx]) if idx < len(lows) else None
        by_day[day_date.isoformat()] = (close_val, high_val, low_val)

    days = sorted(by_day)
    market_ts = meta.get("regularMarketTime")
    quote_time: str | None = None
    market_day: str | None = None
    if isinstance(market_ts, (int, float)) and math.isfinite(market_ts):
        qdt = datetime.fromtimestamp(float(market_ts), tz=timezone.utc)
        if qdt.astimezone(NY).date() <= max_day:
            quote_time = qdt.isoformat()
            market_day = qdt.astimezone(NY).date().isoformat()

    price = _positive_finite(meta.get("regularMarketPrice"))
    if price is None and days:
        price = by_day[days[-1]][0]
    if price is None:
        raise ValueError("Yahoo COMEX 黄金缺少有效最新价格")

    as_of = market_day or (days[-1] if days else None)
    if not as_of:
        raise ValueError("Yahoo COMEX 黄金缺少有效交易日期")

    # 注意：range=2mo 下 chartPreviousClose 为 2 个月前基准，严禁直接当作昨收
    prev_close = _positive_finite(meta.get("previousClose"))
    if prev_close is None and days:
        if days[-1] == as_of and len(days) >= 2:
            prev_close = by_day[days[-2]][0]
        elif days[-1] < as_of:
            prev_close = by_day[days[-1]][0]
        elif len(days) >= 2:
            prev_close = by_day[days[-2]][0]
        else:
            prev_close = _positive_finite(meta.get("chartPreviousClose"))

    day_high = _positive_finite(meta.get("regularMarketDayHigh")) or (by_day[days[-1]][1] if days else None)
    day_low = _positive_finite(meta.get("regularMarketDayLow")) or (by_day[days[-1]][2] if days else None)
    if day_high is not None:
        day_high = max(day_high, price)
    if day_low is not None:
        day_low = min(day_low, price)

    prior_date = days[-22] if len(days) >= 22 else None
    change_21d_pct = (
        round((price / by_day[prior_date][0] - 1.0) * 100.0, 2)
        if prior_date is not None
        else None
    )
    change_pct = (
        round((price / prev_close - 1.0) * 100.0, 2)
        if prev_close is not None
        else None
    )
    raw_exch = str(meta.get("fullExchangeName") or meta.get("exchangeName") or "").upper()
    exchange = "COMEX" if ("COMEX" in raw_exch or "CMX" in raw_exch or not raw_exch) else raw_exch
    return {
        "symbol": "GC=F",
        "name": "COMEX 黄金主力",
        "exchange": exchange,
        "currency": str(meta.get("currency") or "USD").upper(),
        "unit": "美元/盎司",
        "price": round(price, 2),
        "prev_close": round(prev_close, 2) if prev_close is not None else None,
        "change_pct": change_pct,
        "day_high": round(day_high, 2) if day_high is not None else None,
        "day_low": round(day_low, 2) if day_low is not None else None,
        "prior_date": prior_date,
        "change_21d_pct": change_21d_pct,
        "as_of": as_of,
        "quote_time": quote_time,
        "fetched_at": now.isoformat(),
        "source": "Yahoo Finance (COMEX)",
    }


def parse_eastmoney_comex_gold(payload: dict, now: datetime) -> dict:
    """解析东方财富 COMEX 黄金主力连续（101.GC00Y）日线回退数据。"""
    data = payload.get("data") if isinstance(payload, dict) else None
    klines = data.get("klines") if isinstance(data, dict) else None
    if not isinstance(klines, list) or not klines:
        raise ValueError("东方财富 COMEX 黄金返回缺少 klines")

    max_day = now.astimezone(NY).date() + timedelta(days=1)
    by_day: dict[str, tuple[float, float | None, float | None]] = {}
    for line in klines:
        if not isinstance(line, str):
            continue
        parts = line.split(",")
        if len(parts) < 5:
            continue
        day_str = parts[0].strip()[:10]
        try:
            day_date = date.fromisoformat(day_str)
        except ValueError:
            continue
        if day_date > max_day:
            continue
        close_val = _positive_finite(parts[2])
        if close_val is None:
            continue
        high_val = _positive_finite(parts[3])
        low_val = _positive_finite(parts[4])
        by_day[day_str] = (close_val, high_val, low_val)

    days = sorted(by_day)
    if not days:
        raise ValueError("东方财富 COMEX 黄金无有效日线收盘数据")

    as_of = days[-1]
    price, day_high, day_low = by_day[as_of]
    prev_close = by_day[days[-2]][0] if len(days) >= 2 else None
    prior_date = days[-22] if len(days) >= 22 else None
    change_pct = (
        round((price / prev_close - 1.0) * 100.0, 2)
        if prev_close is not None
        else None
    )
    change_21d_pct = (
        round((price / by_day[prior_date][0] - 1.0) * 100.0, 2)
        if prior_date is not None
        else None
    )
    return {
        "symbol": "GC00Y",
        "name": "COMEX 黄金主力",
        "exchange": "COMEX",
        "currency": "USD",
        "unit": "美元/盎司",
        "price": round(price, 2),
        "prev_close": round(prev_close, 2) if prev_close is not None else None,
        "change_pct": change_pct,
        "day_high": round(day_high, 2) if day_high is not None else None,
        "day_low": round(day_low, 2) if day_low is not None else None,
        "prior_date": prior_date,
        "change_21d_pct": change_21d_pct,
        "as_of": as_of,
        "quote_time": None,
        "fetched_at": now.isoformat(),
        "source": "东方财富 (COMEX黄金)",
    }


async def fetch_comex_gold(now: datetime) -> dict:
    """按「Yahoo Finance GC=F 主备节点 → 东方财富 101.GC00Y 热备」顺序免 Key 拉取 COMEX 黄金行情。"""
    last_err: Exception | None = None
    async with httpx.AsyncClient(
        timeout=15,
        follow_redirects=True,
        headers=PUBLIC_MARKET_HEADERS,
    ) as client:
        for url in YAHOO_GOLD_URLS:
            try:
                resp = await client.get(url, params={"range": "2mo", "interval": "1d"})
                resp.raise_for_status()
                return parse_yahoo_comex_gold(resp.json(), now)
            except (httpx.HTTPError, ValueError) as exc:
                last_err = exc
                continue
        try:
            resp = await client.get(
                EASTMONEY_GOLD_URL,
                params={
                    "secid": "101.GC00Y",
                    "fields1": "f1,f2,f3",
                    "fields2": "f51,f52,f53,f54,f55,f56",
                    "klt": "101",
                    "fqt": "0",
                    "lmt": "30",
                    "end": "20500101",
                },
            )
            resp.raise_for_status()
            return parse_eastmoney_comex_gold(resp.json(), now)
        except (httpx.HTTPError, ValueError) as exc:
            last_err = exc
    raise ValueError(f"COMEX 黄金公开行情获取失败：{type(last_err).__name__ if last_err else 'Unknown'}")


def gold_context(
    gold: dict | None,
    now: datetime,
    demo: bool,
    real_ten_year: float | None = None,
    real_rate_fresh: bool = False,
) -> dict:
    """将 COMEX 黄金缓存与 10Y TIPS 实际利率结合为标准化、可安全脱敏展示的市场研究上下文。"""
    raw = gold if isinstance(gold, dict) else {}
    price = _positive_finite(raw.get("price"))
    prev_close = _positive_finite(raw.get("prev_close"))
    day_high = _positive_finite(raw.get("day_high"))
    day_low = _positive_finite(raw.get("day_low"))
    change_pct = finite(raw.get("change_pct"))
    if change_pct is None and price is not None and prev_close is not None:
        change_pct = round((price / prev_close - 1.0) * 100.0, 2)
    change_21d_pct = finite(raw.get("change_21d_pct"))
    as_of = raw.get("as_of") if isinstance(raw.get("as_of"), str) and raw.get("as_of") else None
    fetched_at = raw.get("fetched_at") if isinstance(raw.get("fetched_at"), str) and raw.get("fetched_at") else None
    available = price is not None

    fresh = False
    if available:
        if demo:
            fresh = True
        else:
            fetched_ok = True
            if fetched_at:
                try:
                    delta = now - datetime.fromisoformat(fetched_at)
                    fetched_ok = timedelta(seconds=-60) <= delta <= timedelta(days=3)
                except ValueError:
                    fetched_ok = False
            day_ok = False
            if as_of:
                try:
                    day_gap = (now.astimezone(NY).date() - date.fromisoformat(as_of)).days
                    day_ok = -1 <= day_gap <= 7
                except ValueError:
                    day_ok = False
            fresh = fetched_ok and day_ok

    eff_real = finite(real_ten_year) if real_rate_fresh else None
    linkage_label = "待同步实际利率"
    linkage_note = (
        "黄金不产生利息，传统上与 10Y TIPS 实际利率呈负相关；待 10Y TIPS 实际利率与 COMEX 金价齐备后自动对照联动。"
    )
    if available and eff_real is not None:
        if eff_real >= 1.8 and change_21d_pct is not None and change_21d_pct >= 2.0:
            linkage_label = "高实际利率下偏强（避险/购金溢价）"
            linkage_note = (
                f"当前 10Y TIPS 实际利率处于 {eff_real:.2f}% 偏高水位，但 COMEX 金价近 21 日仍走强 {change_21d_pct:+.1f}%，"
                "呈现与传统利率负相关的脱锚特征，常见于央行购金、财政担忧或避险情绪主导阶段。"
            )
        elif eff_real <= 1.2 and (change_21d_pct is None or change_21d_pct >= 0):
            linkage_label = "低实际利率顺风"
            linkage_note = (
                f"当前 10Y TIPS 实际利率位于 {eff_real:.2f}% 较低区间，持有无息黄金的机会成本较低，宏观利率环境对金价相对友好。"
            )
        elif eff_real >= 1.8 and change_21d_pct is not None and change_21d_pct <= -2.0:
            linkage_label = "高实际利率压制"
            linkage_note = (
                f"10Y TIPS 实际利率维持在 {eff_real:.2f}% 高位，叠加 COMEX 金价近 21 日回落 {change_21d_pct:+.1f}%，"
                "反映高真实资金成本对无息贵金属估值的压制。"
            )
        else:
            chg_part = (
                f"近 21 日变动 {change_21d_pct:+.1f}%"
                if change_21d_pct is not None
                else "短周期走势平稳"
            )
            linkage_label = "利率与金价中性拉锯"
            linkage_note = (
                f"10Y TIPS 实际利率当前为 {eff_real:.2f}%，COMEX 金价{chg_part}；二者暂未出现显著极端背离，"
                "可结合美元与美债长端方向综合观察。"
            )

    return {
        "available": available,
        "symbol": str(raw.get("symbol") or "GC=F"),
        "name": str(raw.get("name") or "COMEX 黄金主力"),
        "exchange": str(raw.get("exchange") or "COMEX"),
        "currency": str(raw.get("currency") or "USD"),
        "unit": str(raw.get("unit") or "美元/盎司"),
        "price": round(price, 2) if price is not None else None,
        "prev_close": round(prev_close, 2) if prev_close is not None else None,
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "day_high": round(day_high, 2) if day_high is not None else None,
        "day_low": round(day_low, 2) if day_low is not None else None,
        "prior_date": raw.get("prior_date"),
        "change_21d_pct": round(change_21d_pct, 2) if change_21d_pct is not None else None,
        "as_of": as_of,
        "quote_time": raw.get("quote_time"),
        "fetched_at": fetched_at,
        "source": "合成期金" if demo else str(raw.get("source") or "COMEX 公开行情"),
        "fresh": fresh,
        "refresh_failed": bool(raw.get("refresh_failed")),
        "real_ten_year": eff_real,
        "real_rate_linkage": linkage_label,
        "real_rate_note": linkage_note,
    }
