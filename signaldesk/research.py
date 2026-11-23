"""Public rates and security-level valuation inputs for long-horizon reviews."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from xml.etree import ElementTree

import httpx

from .calendar import NY
from .indicators import finite

TREASURY_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"

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
            except (httpx.HTTPError, ElementTree.ParseError, ValueError):
                if rows:
                    break  # Keep the current pair even if the older comparison is unavailable.
                raise
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
