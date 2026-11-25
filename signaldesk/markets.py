"""Longbridge security identifiers and their regular trading markets."""

import re
from dataclasses import dataclass
from datetime import timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Market:
    code: str
    name: str
    calendar_name: str
    timezone: ZoneInfo
    close_hour: int
    closing_auction: timedelta = timedelta(0)


US = Market("US", "美股", "XNYS", ZoneInfo("America/New_York"), 16)
HK = Market("HK", "港股", "XHKG", ZoneInfo("Asia/Hong_Kong"), 16, timedelta(minutes=10))
CN = Market("CN", "A股", "XSHG", ZoneInfo("Asia/Shanghai"), 15)
EXCHANGES = {"US": US, "HK": HK, "SH": CN, "SZ": CN}


def normalize_symbol(value: str, *, broker: bool = False) -> str:
    value = value.strip().upper()
    ticker, _, exchange = value.rpartition(".")
    if exchange == "HK" and re.fullmatch(r"[0-9]{1,5}", ticker) and int(ticker):
        return f"{int(ticker)}.HK"
    if exchange in {"SH", "SZ"} and re.fullmatch(r"[0-9]{6}", ticker):
        # Mainland B shares trade in foreign currencies and are outside the A-share universe.
        if not ticker.startswith("900" if exchange == "SH" else "200"):
            return value
    if exchange == "US" and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", ticker):
        return value
    if not broker and re.fullmatch(r"[A-Z][A-Z0-9\-]*(?:\.[AB])?", value) and len(value) <= 15:
        return f"{value}.US"
    raise ValueError("请输入股票代码，例如 AAPL、700.HK、600519.SH 或 000001.SZ")


def market_for(symbol: str) -> Market:
    return EXCHANGES[symbol.rsplit(".", 1)[-1]]
