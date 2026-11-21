"""Public rates and security-level valuation inputs for long-horizon reviews."""

from datetime import date, datetime, timedelta
from xml.etree import ElementTree

import httpx

from .calendar import NY
from .indicators import finite

TREASURY_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"


def treasury_observations(xml: bytes, today: date) -> dict:
    rows = {}
    for row in ElementTree.fromstring(xml).iterfind(".//{*}properties"):
        day = row.findtext("{*}NEW_DATE", "")[:10]
        two = finite(row.findtext("{*}BC_2YEAR"))
        ten = finite(row.findtext("{*}BC_10YEAR"))
        if day and date.fromisoformat(day) <= today and two is not None and ten is not None:
            rows[day] = (two, ten)
    return rows


async def fetch_curve(now: datetime) -> dict:
    today = now.astimezone(NY).date()
    rows = {}
    month = today.replace(day=1)
    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
        for _ in range(3):
            try:
                response = await client.get(
                    TREASURY_URL,
                    params={"data": "daily_treasury_yield_curve",
                            "field_tdr_date_value_month": month.strftime("%Y%m")},
                )
                response.raise_for_status()
                rows.update(treasury_observations(response.content, today))
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
    two, ten = rows[day]
    prior = dates[-22] if len(dates) >= 22 else None
    return {
        "as_of": day,
        "two_year": two,
        "ten_year": ten,
        "spread_bp": round((ten - two) * 100, 2),
        "prior_date": prior,
        "ten_change_bp": round((ten - rows[prior][1]) * 100, 2) if prior else None,
    }


def research_context(valuation: dict, curve: dict, now: datetime, demo: bool) -> dict:
    fetched = valuation.get("fetched_at")
    day = curve.get("as_of")
    valuation_ok = bool(
        fetched and timedelta(0) <= now - datetime.fromisoformat(fetched) <= timedelta(days=4)
    )
    curve_ok = bool(day and 0 <= (now.astimezone(NY).date() - date.fromisoformat(day)).days <= 7)
    pe = valuation.get("pe_ttm")
    earnings_yield = 100 / pe if pe and pe > 0 and valuation_ok else None
    ten = curve.get("ten_year")
    return {
        "valuation": {**valuation, "source": "合成估值" if demo else "LongPort", "fresh": valuation_ok},
        "curve": {**curve, "source": "合成利率" if demo else "美国财政部", "fresh": curve_ok},
        "earnings_yield_pct": earnings_yield,
        "yield_gap_pp": earnings_yield - ten
        if earnings_yield is not None and curve_ok and ten is not None
        else None,
    }
