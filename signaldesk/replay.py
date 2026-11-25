"""Replay the same causal indicator/event pipeline; this is not a portfolio return backtest."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .calendar import bar_end
from .demo import make_bars
from .events import EventEngine
from .indicators import enrich, summarize
from .markets import market_for, normalize_symbol
from .models import RuleSettings, utcnow
from .storage import Store


def load_bars(path: Path, session: str) -> list[dict]:
    if path.suffix.lower() == ".json":
        records = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError("JSON必须是OHLCV记录数组")
        table = pd.DataFrame(records)
    else:
        table = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(table.columns):
        raise ValueError(f"缺少必需列：{', '.join(sorted(required - set(table.columns)))}")
    for value in table["timestamp"]:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp) or stamp.tzinfo is None:
            raise ValueError("timestamp必须是带时区的有效ISO8601时间")
    for name in ["open", "high", "low", "close", "volume"]:
        table[name] = pd.to_numeric(table[name], errors="coerce")
    if "confirmed" not in table:
        table["confirmed"] = True
    if not table["confirmed"].isin([True, False]).all():
        raise ValueError("confirmed必须为true/false")
    if "session" not in table:
        table["session"] = session
    if not table["session"].isin(["regular", "pre", "post", "overnight"]).all():
        raise ValueError("session必须为regular/pre/post/overnight")
    if "turnover" not in table:
        table["turnover"] = table["close"] * table["volume"]
    else:
        table["turnover"] = pd.to_numeric(table["turnover"], errors="coerce")
    return table.to_dict("records")


def replay(bars: list[dict], symbol: str, timeframe: str, session: str = "regular") -> dict:
    symbol = normalize_symbol(symbol)
    venue = market_for(symbol)
    frame = enrich(bars, timeframe, datetime(2035, 1, 1, tzinfo=timezone.utc), RuleSettings(), venue)
    with tempfile.TemporaryDirectory(prefix="signaldesk-replay-") as temporary:
        store = Store(Path(temporary))
        engine = EventEngine(store)
        valid = 0
        for ix in frame.index[frame["session"] == session]:
            now = bar_end(frame.loc[ix, "timestamp"].to_pydatetime(), timeframe, venue)
            summary = summarize(frame.loc[:ix], timeframe, session, now, RuleSettings(), demo=True, market=venue)
            valid += bool(summary["valid"])
            engine.fusion(
                symbol,
                "long" if timeframe == "day" else "short",
                summary,
                RuleSettings(),
                "demo",
                historical=True,
            )
        events = store.events(count=10000)
        store.close()
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "session": session,
        "bar_count": len(frame),
        "valid_snapshots": valid,
        "event_count": len(events),
        "events": list(reversed(events)),
        "note": "仅复现技术事件，不是收益回测；缺少盘外盘口时不能验证盘外机会的可交易性",
    }


def main():
    parser = argparse.ArgumentParser(description="用相同信号引擎回放本机OHLCV数据")
    parser.add_argument("--input", type=Path, help="本机CSV或JSON文件，缺省使用合成数据")
    parser.add_argument("--symbol", default="NVDA.US")
    parser.add_argument("--timeframe", choices=["day", "15m"], default="day")
    parser.add_argument("--session", choices=["regular", "pre", "post", "overnight"], default="regular")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.input:
        bars = load_bars(args.input, args.session)
    else:
        bars = make_bars(normalize_symbol(args.symbol), args.timeframe, utcnow())
    report = replay(bars, args.symbol, args.timeframe, args.session)
    text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
