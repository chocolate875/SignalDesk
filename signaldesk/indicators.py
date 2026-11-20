from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands

from . import operators as op
from .calendar import NY, bar_end, calendar, latest_expected_end
from .models import RuleSettings

RULE_VERSION = "fusion-1.1.0"
FEATURE_COLUMNS = [
    "ma20",
    "ma50",
    "ma200",
    "ema20",
    "ema50",
    "rsi",
    "macd",
    "macd_signal",
    "macd_hist",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "atr",
    "vwap",
    "rvol",
    "trend",
    "momentum",
    "volume_score",
    "score",
    "return_1",
    "zscore20",
    "rank20",
    "corr20",
]


def finite(value):
    try:
        return float(value) if math.isfinite(float(value)) else None
    except (ValueError, TypeError):
        return None


def enrich(bars: list[dict], timeframe: str, now: datetime, rules: RuleSettings) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame()
    frame = pd.DataFrame(bars).copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = (
        frame[frame["confirmed"]]
        .sort_values("timestamp", kind="stable")
        .drop_duplicates("timestamp", keep="last")
    )
    frame = frame[frame["timestamp"].map(lambda t: bar_end(t.to_pydatetime(), timeframe) <= now)].reset_index(
        drop=True
    )
    if frame.empty:
        return frame
    invalid = (
        ~np.isfinite(frame[["open", "high", "low", "close", "volume"]]).all(axis=1)
        | (frame["close"] <= 0)
        | (frame["low"] <= 0)
        | (frame["volume"] < 0)
        | (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    )
    # Retain invalid rows as a break: never bridge/fill missing data into a valid signal.
    frame.loc[invalid, ["open", "high", "low", "close", "volume"]] = np.nan
    for col in FEATURE_COLUMNS:
        frame[col] = np.nan
    # Indicators never mix extended and regular bars. Missing/invalid OHLC resets the warmup.
    groups = frame.groupby("session", sort=False)
    for _, session_frame in groups:
        valid = session_frame["close"].notna()
        local = session_frame["timestamp"].dt.tz_convert(NY)
        dates = local.map(lambda t: (t.to_pydatetime() + timedelta(hours=4)).date())
        same_day = dates == dates.shift(1)
        if timeframe == "day":
            sessions = calendar().sessions
            days = local.dt.tz_localize(None).dt.normalize()
            ordinals = pd.Series(sessions.get_indexer(days), index=session_frame.index)
            valid &= ordinals.ge(0)
            gaps = ordinals.diff().gt(1)
        else:
            gaps = same_day & (session_frame["timestamp"].diff().dt.total_seconds() > 900)
        segments = ((~valid) | gaps).cumsum()
        for _, part in session_frame[valid].groupby(segments[valid]):
            if part.empty:
                continue
            ix = part.index
            c, h, low, v = (part[k].astype(float) for k in ["close", "high", "low", "volume"])
            values = {}
            for period in [20, 50, 200]:
                values[f"ma{period}"] = SMAIndicator(c, period, fillna=False).sma_indicator()
            for period in [20, 50]:
                values[f"ema{period}"] = EMAIndicator(c, period, fillna=False).ema_indicator()
            values["rsi"] = RSIIndicator(c, 14, fillna=False).rsi()
            macd = MACD(c, 26, 12, 9, fillna=False)
            values.update(macd=macd.macd(), macd_signal=macd.macd_signal(), macd_hist=macd.macd_diff())
            bb = BollingerBands(c, 20, 2, fillna=False)
            values.update(
                bb_upper=bb.bollinger_hband(), bb_middle=bb.bollinger_mavg(), bb_lower=bb.bollinger_lband()
            )
            atr = (
                AverageTrueRange(h, low, c, 14, fillna=False).average_true_range()
                if len(part) >= 14
                else c * np.nan
            )
            atr = atr.where(np.arange(len(part)) >= 13).replace(0, np.nan)
            values["atr"] = atr
            local_time = part["timestamp"].dt.tz_convert(NY)
            trading_dates = local_time.map(lambda t: (t.to_pydatetime() + timedelta(hours=4)).date())
            typical = (h + low + c) / 3
            if timeframe == "day":
                values["vwap"] = c * np.nan  # One daily OHLC bar is not an intraday VWAP.
                baseline = op.mean(op.delay(v), 20)
            else:
                turn = part["turnover"].where(part["turnover"] > 0, typical * v)
                values["vwap"] = turn.groupby(trading_dates).cumsum() / v.groupby(
                    trading_dates
                ).cumsum().replace(0, np.nan)
                # Same exchange-local clock slot, same session, preceding 20 trading days only.
                slots = local_time.dt.strftime("%H:%M")
                baseline = v.groupby(slots).transform(lambda x: x.shift(1).rolling(20, min_periods=10).mean())
            rvol = v / baseline.replace(0, np.nan)
            values["rvol"] = rvol
            t1 = op.clip((values["ema20"] - values["ema50"]) / atr)
            t2 = op.clip(op.delta(values["ema20"], 5) / atr)
            t3 = np.sign(c - values["ma200"])
            trend = (t1 + t2 + t3) / 3
            momentum = ((values["rsi"] - 50) / 50 + op.clip(values["macd_hist"] / atr)) / 2
            ret = op.returns(c)
            quantity = np.sign(ret) * op.clip(rvol - 1, 0, 1)
            values.update(
                trend=(trend + 1) * 50,
                momentum=(momentum + 1) * 50,
                volume_score=(quantity + 1) * 50,
                return_1=ret,
                zscore20=op.zscore(c, 20),
                rank20=op.ts_rank(c, 20),
                corr20=op.corr(ret, op.delta(v), 20),
            )
            values["score"] = (
                rules.trend_weight * values["trend"]
                + rules.momentum_weight * values["momentum"]
                + rules.volume_weight * values["volume_score"]
            )
            for key, series in values.items():
                frame.loc[ix, key] = series
    return frame.replace([np.inf, -np.inf], np.nan)


def summarize(
    frame: pd.DataFrame,
    timeframe: str,
    session: str,
    now: datetime,
    rules: RuleSettings,
    quote: dict | None = None,
    demo: bool = False,
) -> dict:
    part = frame[frame["session"] == session] if not frame.empty else frame
    empty = {
        "timeframe": timeframe,
        "session": session,
        "valid": False,
        "confirmed_price_available": False,
        "score": None,
        "dimensions": {},
        "indicators": {},
        "risks": ["预热数据不足"],
        "state": "unavailable",
        "as_of": None,
        "rule_version": RULE_VERSION,
        "opportunity_allowed": False,
        "evidence": [],
    }
    if part.empty:
        return empty
    row = part.iloc[-1]
    indicators = {
        k: finite(row[k]) for k in FEATURE_COLUMNS if k not in ["trend", "momentum", "volume_score", "score"]
    }
    dimensions = {k: finite(row[k]) for k in ["trend", "momentum", "volume_score"]}
    score = finite(row["score"])
    risks = []
    if score is None:
        risks.append("预热数据不足或因子缺失")
    expected = latest_expected_end(now, timeframe, session)
    end = bar_end(row["timestamp"].to_pydatetime(), timeframe)
    stale = expected is not None and end + timedelta(seconds=90) < expected
    if stale and not demo:
        risks.append("行情过期：最近应完成K线缺失")
    status = (quote or {}).get("trade_status", "normal").lower()
    if status not in ["normal", "normaltrade", "normal_trade", ""]:
        risks.append("停牌或交易状态受限")
    atr, price = indicators["atr"], finite(row["close"])
    if price and atr and atr / price > 0.04:
        risks.append("波动偏高")
    if price and atr and indicators["ma20"] and abs(price - indicators["ma20"]) / atr > 2:
        risks.append("偏离MA20超过2ATR")
    rsi = indicators.get("rsi")
    if rsi is not None and (rsi >= 70 or rsi <= 30):
        risks.append("RSI进入极值区")
    spread = (quote or {}).get("spread_ratio")
    if not demo and (quote or {}).get("timestamp"):
        try:
            if (now - datetime.fromisoformat(quote["timestamp"])).total_seconds() > 120:
                spread = None
        except ValueError:
            spread = None
    liquidity_ok = True
    if session != "regular":
        if spread is None or spread > rules.max_extended_spread:
            risks.append("盘外价差不足以确认机会" if spread is None else "盘外价差过宽")
            liquidity_ok = False
        if float(row["turnover"]) < rules.min_extended_turnover:
            risks.append("盘外成交额不足")
            liquidity_ok = False
    valid = (
        score is not None and (demo or not stale) and status in ["normal", "normaltrade", "normal_trade", ""]
    )
    state = (
        "strong"
        if score is not None and score >= rules.strong_threshold
        else "weak"
        if score is not None and score <= rules.weak_threshold
        else "neutral"
    )
    if not valid:
        state = "unavailable"
    weights = {
        "trend": rules.trend_weight,
        "momentum": rules.momentum_weight,
        "volume_score": rules.volume_weight,
    }
    contributions = {k: dimensions[k] * w for k, w in weights.items() if dimensions[k] is not None}
    changes = {}
    if valid and len(part) > 1 and finite(part.iloc[-2]["score"]) is not None:
        changes = {k: (dimensions[k] - float(part.iloc[-2][k])) * w for k, w in weights.items()}
    evidence = []
    if score is not None:
        evidence = [
            f"收盘 {price:.2f} / 200期均线 {indicators['ma200']:.2f}；EMA20 {indicators['ema20']:.2f} / EMA50 {indicators['ema50']:.2f}",
            f"RSI14 {rsi:.1f}（中点50）；MACD柱 {indicators['macd_hist']:+.3f}（基准0）",
            f"成交量为历史基准的 {indicators['rvol']:.2f} 倍，本期收盘涨跌 {indicators['return_1']:+.2%}",
        ]
        for i, value in enumerate(dimensions.values()):
            direction = "支持走强" if value >= 60 else "支持走弱" if value <= 40 else "未达方向确认阈值"
            evidence[i] += f"（{direction}）"
    return {
        "timeframe": timeframe,
        "session": session,
        "valid": valid,
        "score": score if valid else None,
        "dimensions": dimensions,
        "indicators": indicators,
        "risks": risks,
        "state": state,
        "as_of": end.isoformat(),
        "rule_version": RULE_VERSION + "+" + hashlib.sha256(rules.model_dump_json().encode()).hexdigest()[:8],
        "weights": weights,
        "contributions": contributions if valid else {},
        "contribution_changes": changes,
        "close": price,
        "confirmed_price_available": price is not None
        and (demo or not stale)
        and status in ["normal", "normaltrade", "normal_trade", ""],
        "opportunity_allowed": valid and liquidity_ok,
        "evidence": evidence,
    }


def chart_rows(frame: pd.DataFrame, session: str, count: int = 220) -> list[dict]:
    if frame.empty:
        return []
    part = frame[frame["session"] == session].tail(count)
    return [
        {
            "timestamp": row["timestamp"].isoformat(),
            **{
                k: finite(row[k])
                for k in ["open", "close", "low", "high", "volume", "turnover"] + FEATURE_COLUMNS
            },
        }
        for _, row in part.iterrows()
    ]
