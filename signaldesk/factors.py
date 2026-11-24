"""严格因果的实证学术因子引擎（仅使用已确认常规前复权日线与免费估值输入，绝不引用未来数据）。"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from .calendar import NY
from .indicators import finite


def _contiguous_regular_tail(frame: pd.DataFrame | None) -> pd.DataFrame:
    """截取最新一段无缺失、无 OHLC 异常的连续常规时段日线尾部。"""
    if frame is None or frame.empty:
        return pd.DataFrame()
    reg = frame[frame["session"] == "regular"] if "session" in frame.columns else frame
    if reg.empty:
        return pd.DataFrame()

    valid = (
        reg["close"].notna()
        & np.isfinite(reg["close"])
        & (reg["close"] > 0)
        & reg["high"].notna()
        & np.isfinite(reg["high"])
        & (reg["high"] > 0)
        & reg["low"].notna()
        & np.isfinite(reg["low"])
        & (reg["low"] > 0)
        & (reg["high"] >= reg["low"])
    )
    if "open" in reg.columns:
        valid = (
            valid
            & reg["open"].notna()
            & np.isfinite(reg["open"])
            & (reg["open"] > 0)
            & (reg["high"] >= reg[["open", "close"]].max(axis=1) - 1e-9)
            & (reg["low"] <= reg[["open", "close"]].min(axis=1) + 1e-9)
        )
    if "volume" in reg.columns:
        valid = valid & reg["volume"].notna() & np.isfinite(reg["volume"]) & (reg["volume"] >= 0)

    if valid.empty or not bool(valid.iloc[-1]):
        return pd.DataFrame()
    breaks = (~valid).cumsum()
    # 必须叠加 valid 掩码，避免把断档 NaN 行本身误纳入连续尾部首行
    return reg[valid & (breaks == breaks.iloc[-1])].copy()


def _trading_dates_series(frame: pd.DataFrame) -> pd.Series | None:
    """将带时区时间索引转为纽约交易日期键，兼容夏令时与日边界。"""
    if "timestamp" not in frame.columns or frame.empty:
        return None
    ts = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    if ts.isna().any():
        return None
    local = ts.dt.tz_convert(NY)
    return local.map(lambda t: (t.to_pydatetime() + timedelta(hours=4)).date())


def compute_yang_zhang_hv(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    window: int,
) -> float | None:
    """计算 Yang-Zhang (2000) 无偏最小方差年化波动率（%）。

    融合隔夜跳空方差、日内开收方差与 Rogers-Satchell 日内极值方差。
    """
    if window < 2 or len(closes) < window + 1:
        return None
    o_prev_c = np.log(opens[1:] / closes[:-1])
    c_o = np.log(closes[1:] / opens[1:])
    h_c = np.log(np.maximum(highs[1:], 1e-12) / closes[1:])
    h_o = np.log(np.maximum(highs[1:], 1e-12) / opens[1:])
    l_c = np.log(np.maximum(lows[1:], 1e-12) / closes[1:])
    l_o = np.log(np.maximum(lows[1:], 1e-12) / opens[1:])
    rs = h_c * h_o + l_c * l_o

    o_win = o_prev_c[-window:]
    c_win = c_o[-window:]
    rs_win = rs[-window:]
    if not (np.isfinite(o_win).all() and np.isfinite(c_win).all() and np.isfinite(rs_win).all()):
        return None

    sigma_o2 = float(np.var(o_win, ddof=1))
    sigma_c2 = float(np.var(c_win, ddof=1))
    sigma_rs2 = float(np.mean(rs_win))
    k = 0.34 / (1.34 + (window + 1.0) / (window - 1.0))
    total_var = max(0.0, sigma_o2 + k * sigma_c2 + (1.0 - k) * sigma_rs2)
    val = finite(math.sqrt(total_var) * math.sqrt(252.0) * 100.0)
    return round(val, 1) if val is not None else None


def _aligned_spy_returns(
    tail: pd.DataFrame,
    spy_frame: pd.DataFrame | None,
) -> tuple[np.ndarray, np.ndarray] | None:
    """按纽约交易日期内连接对齐个股与 SPY 的同日简单收益率，严格截断在个股最新日期内。"""
    if spy_frame is None or spy_frame.empty or len(tail) < 2:
        return None
    spy_tail = _contiguous_regular_tail(spy_frame)
    if len(spy_tail) < 2:
        return None

    stock_dates = _trading_dates_series(tail)
    spy_dates = _trading_dates_series(spy_tail)
    if stock_dates is None or spy_dates is None:
        return None

    last_stock_date = stock_dates.iloc[-1]
    s_ret = pd.Series(tail["close"].to_numpy(dtype=float)).pct_change().iloc[1:]
    s_df = pd.DataFrame({"d": stock_dates.iloc[1:].to_numpy(), "ri": s_ret.to_numpy()})

    m_ret = pd.Series(spy_tail["close"].to_numpy(dtype=float)).pct_change().iloc[1:]
    m_df = pd.DataFrame({"d": spy_dates.iloc[1:].to_numpy(), "rm": m_ret.to_numpy()})
    m_df = m_df[m_df["d"] <= last_stock_date]

    merged = (
        s_df.drop_duplicates("d", keep="last")
        .merge(m_df.drop_duplicates("d", keep="last"), on="d", how="inner")
        .sort_values("d", kind="stable")
    )
    ri = merged["ri"].to_numpy(dtype=float)
    rm = merged["rm"].to_numpy(dtype=float)
    mask = np.isfinite(ri) & np.isfinite(rm)
    if int(mask.sum()) < 20:
        return None
    return ri[mask], rm[mask]


def compute_academic_factors(
    frame: pd.DataFrame | None,
    spy_frame: pd.DataFrame | None = None,
    valuation: dict | None = None,
    is_fund: bool = False,
    is_leveraged: bool = False,
) -> dict[str, Any]:
    """计算严格因果的多维度学术量化因子（全零付费数据源、窗口不足返回 None）。"""
    empty: dict[str, Any] = {
        "available": False,
        "window_days": 0,
        "yang_zhang_hv20_pct": None,
        "yang_zhang_hv60_pct": None,
        "high_52w": None,
        "low_52w": None,
        "high_52w_ratio": None,
        "drawdown_52w_pct": None,
        "residual_mom_z": None,
        "residual_mom_window": None,
        "alpha_vs_spy_60d_pct": None,
        "beta_spy": None,
        "info_discreteness": None,
        "id_label": None,
        "overnight_20d_pct": None,
        "intraday_20d_pct": None,
        "overnight_60d_pct": None,
        "intraday_60d_pct": None,
        "tug_of_war_state": None,
        "tug_of_war_label": None,
        "tug_of_war_warning": "",
        "max5_21d_pct": None,
        "lottery_overheated": False,
        "downside_beta": None,
        "realized_skew_60d": None,
        "amihud_20d": None,
        "avg_dollar_vol_20d": None,
        "illiquid_flag": False,
        "turnover_rate_pct": None,
        "market_cap": None,
        "high_turnover_flag": False,
    }
    tail = _contiguous_regular_tail(frame)
    if len(tail) < 20:
        return empty

    closes = tail["close"].to_numpy(dtype=float)
    highs = tail["high"].to_numpy(dtype=float)
    lows = tail["low"].to_numpy(dtype=float)
    has_open = "open" in tail.columns
    opens = tail["open"].to_numpy(dtype=float) if has_open else None
    close_now = finite(closes[-1])
    if close_now is None or close_now <= 0:
        return empty

    # 1. Yang-Zhang 无偏波动率
    yz20 = compute_yang_zhang_hv(opens, highs, lows, closes, 20) if opens is not None else None
    yz60 = compute_yang_zhang_hv(opens, highs, lows, closes, 60) if opens is not None else None

    # 2. 全标的统一 52 周高点锚定（George & Hwang 2004）
    win_52w = tail.tail(252)
    high_52w = None
    low_52w = None
    high_52w_ratio = None
    drawdown_52w_pct = None
    if len(win_52w) >= 60:
        h52 = finite(float(np.max(win_52w["high"].to_numpy(dtype=float))))
        l52 = finite(float(np.min(win_52w["low"].to_numpy(dtype=float))))
        if h52 is not None and h52 > 0:
            high_52w = round(h52, 4)
            high_52w_ratio = round(close_now / h52, 4)
            drawdown_52w_pct = round((close_now / h52 - 1.0) * 100.0, 2)
        if l52 is not None and l52 > 0:
            low_52w = round(l52, 4)

    # 简单收益率与对数收益率
    simple_rets = np.diff(closes) / closes[:-1]
    log_rets = np.diff(np.log(closes))

    # 3. 残差动量（vs SPY）与下行贝塔（Downside Beta）
    residual_mom_z = None
    residual_mom_window = None
    alpha_vs_spy_60d_pct = None
    beta_spy = None
    downside_beta = None
    aligned = _aligned_spy_returns(tail, spy_frame)
    if aligned is not None:
        ri_all, rm_all = aligned
        if len(ri_all) >= 60:
            ri60, rm60 = ri_all[-60:], rm_all[-60:]
            var_m60 = float(np.var(rm60, ddof=1))
            if var_m60 > 1e-12:
                cov60 = float(np.cov(ri60, rm60, ddof=1)[0, 1])
                b60 = finite(cov60 / var_m60)
                if b60 is not None:
                    beta_spy = round(b60, 2)
            alpha_val = (float(np.prod(1.0 + ri60) - 1.0) - float(np.prod(1.0 + rm60) - 1.0)) * 100.0
            if finite(alpha_val) is not None:
                alpha_vs_spy_60d_pct = round(alpha_val, 2)

        if len(ri_all) >= 126:
            w = 252 if len(ri_all) >= 252 else 126
            residual_mom_window = "12-1M" if w == 252 else "6-1M"
            w_ri = ri_all[-w:]
            w_rm = rm_all[-w:]
            var_mw = float(np.var(w_rm, ddof=1))
            if var_mw > 1e-12:
                beta_est = float(np.cov(w_ri, w_rm, ddof=1)[0, 1] / var_mw)
                # 采用扣 Beta 不扣自身 Alpha 的特质收益（Blitz et al. 2011），
                # 确保稳定跑赢大盘的慢牛不会因样本截距吸收均值而被清零。
                form_ri = w_ri[:-21]
                form_rm = w_rm[:-21]
                eps_form = form_ri - beta_est * form_rm
                eps_std = float(np.std(eps_form, ddof=1)) if len(eps_form) >= 20 else 0.0
                if eps_std > 1e-12:
                    ir_val = float(np.sum(eps_form)) / (eps_std * math.sqrt(len(eps_form)))
                    if finite(ir_val) is not None:
                        residual_mom_z = round(ir_val, 2)

        dn_len = min(len(ri_all), 126)
        if dn_len >= 60:
            ri_dn_win = ri_all[-dn_len:]
            rm_dn_win = rm_all[-dn_len:]
            dn_mask = rm_dn_win < 0.0
            if int(dn_mask.sum()) >= 15:
                rm_neg = rm_dn_win[dn_mask]
                ri_neg = ri_dn_win[dn_mask]
                var_neg = float(np.var(rm_neg, ddof=1))
                if var_neg > 1e-12:
                    cov_neg = float(np.cov(ri_neg, rm_neg, ddof=1)[0, 1])
                    db_val = finite(cov_neg / var_neg)
                    if db_val is not None:
                        downside_beta = round(db_val, 2)

    # 4. 蛙跳动量 / 信息离散度（FIP / ID，Da et al. 2014）
    info_discreteness = None
    id_label = None
    rets_id: np.ndarray | None = None
    if len(simple_rets) >= 126:
        rets_id = simple_rets[-min(len(simple_rets), 252):-21]
    elif len(simple_rets) >= 60:
        rets_id = simple_rets[-60:]
    if rets_id is not None and len(rets_id) >= 30:
        cum_p = float(np.prod(1.0 + rets_id) - 1.0)
        p_pos = float(np.mean(rets_id > 0.0))
        p_neg = float(np.mean(rets_id < 0.0))
        sign_p = 1.0 if cum_p > 0.0 else (-1.0 if cum_p < 0.0 else 0.0)
        id_val = sign_p * (p_neg - p_pos)
        info_discreteness = round(id_val, 3)
        if cum_p > 0.0 and info_discreteness <= -0.10:
            id_label = "连续慢牛"
        elif cum_p > 0.0 and info_discreteness >= 0.05:
            id_label = "脉冲跳涨"
        elif cum_p < 0.0 and info_discreteness <= -0.10:
            id_label = "持续阴跌"
        else:
            id_label = "节奏均衡"

    # 5. 隔夜 vs 日内拉锯分解（Lou, Polk & Skouras 2019 & 后续）
    overnight_20d_pct = None
    intraday_20d_pct = None
    overnight_60d_pct = None
    intraday_60d_pct = None
    tug_state = None
    tug_label = None
    tug_warning = ""
    if opens is not None and len(closes) >= 21:
        g_on = opens[1:] / closes[:-1]
        g_id = closes[1:] / opens[1:]
        if np.isfinite(g_on[-20:]).all() and np.isfinite(g_id[-20:]).all():
            on20 = (float(np.prod(g_on[-20:])) - 1.0) * 100.0
            id20 = (float(np.prod(g_id[-20:])) - 1.0) * 100.0
            overnight_20d_pct = round(on20, 2)
            intraday_20d_pct = round(id20, 2)
            if (on20 >= 4.0 and id20 <= -4.0) or (on20 - id20 >= 10.0 and id20 < -1.5):
                tug_state = "night_pump_day_dump"
                tug_label = "高开低走特征"
                tug_warning = (
                    f"近20日隔夜累计 {on20:+.1f}% 但盘中累计 {id20:+.1f}%，"
                    "历史呈高开低走派发特征，盘外拉高谨防开盘追高"
                )
            elif id20 >= 4.0 and on20 <= -3.0:
                tug_state = "day_accum_night_dip"
                tug_label = "低开承接特征"
            elif on20 >= 2.5 and id20 >= 2.5:
                tug_state = "resonant_up"
                tug_label = "日夜共振走强"
            elif on20 <= -2.5 and id20 <= -2.5:
                tug_state = "resonant_down"
                tug_label = "日夜共振偏弱"
            else:
                tug_state = "neutral"
                tug_label = "日夜均衡"
        if len(closes) >= 61 and np.isfinite(g_on[-60:]).all() and np.isfinite(g_id[-60:]).all():
            overnight_60d_pct = round((float(np.prod(g_on[-60:])) - 1.0) * 100.0, 2)
            intraday_60d_pct = round((float(np.prod(g_id[-60:])) - 1.0) * 100.0, 2)

    # 6. MAX5 彩票过热与近 60 日已实现偏度（Bali et al. 2011; Amaya et al. 2015）
    max5_21d_pct = None
    lottery_overheated = False
    if len(simple_rets) >= 21:
        top5 = np.sort(simple_rets[-21:])[-5:]
        max5_val = float(np.mean(top5) * 100.0)
        if finite(max5_val) is not None:
            max5_21d_pct = round(max5_val, 2)
            threshold = 11.0 if is_leveraged else 6.5
            lottery_overheated = max5_21d_pct >= threshold

    realized_skew_60d = None
    if len(log_rets) >= 60:
        lr60 = log_rets[-60:]
        mu60 = float(np.mean(lr60))
        sd60 = float(np.std(lr60, ddof=0))
        if sd60 > 1e-12:
            skew_val = float(np.mean(((lr60 - mu60) / sd60) ** 3))
            if finite(skew_val) is not None:
                realized_skew_60d = round(skew_val, 2)

    # 7. Amihud 非流动性冲击（Amihud 2002）与免费换手/市值字段
    amihud_20d = None
    avg_dollar_vol_20d = None
    illiquid_flag = False
    if "volume" in tail.columns and len(simple_rets) >= 20:
        vol_arr = tail["volume"].to_numpy(dtype=float)[1:]
        typ_arr = ((highs[1:] + lows[1:] + closes[1:]) / 3.0) * vol_arr
        if "turnover" in tail.columns:
            turn_arr = tail["turnover"].to_numpy(dtype=float)[1:]
            dv_arr = np.where(np.isfinite(turn_arr) & (turn_arr > 0), turn_arr, typ_arr)
        else:
            dv_arr = typ_arr
        r20 = simple_rets[-20:]
        dv20 = dv_arr[-20:]
        valid_dv = np.isfinite(dv20) & (dv20 > 0) & np.isfinite(r20)
        if int(valid_dv.sum()) >= 15:
            avg_dv = float(np.mean(dv20[valid_dv]))
            # 单位：% 涨跌幅 / 每百万美元成交额
            illiq_series = (np.abs(r20[valid_dv]) * 100.0) / (dv20[valid_dv] / 1_000_000.0)
            amihud_val = float(np.mean(illiq_series))
            if finite(avg_dv) is not None:
                avg_dollar_vol_20d = round(avg_dv, 0)
            if finite(amihud_val) is not None:
                amihud_20d = round(amihud_val, 4)
            if (avg_dollar_vol_20d is not None and avg_dollar_vol_20d < 5_000_000.0) or (
                amihud_20d is not None and amihud_20d > 0.5
            ):
                illiquid_flag = True

    val_dict = valuation or {}
    turnover_rate_pct = finite(val_dict.get("turnover_rate_pct"))
    if turnover_rate_pct is not None:
        turnover_rate_pct = round(turnover_rate_pct, 2)
    market_cap = finite(val_dict.get("market_cap"))
    if market_cap is not None:
        market_cap = round(market_cap, 0)
    high_turnover_flag = bool(not is_fund and turnover_rate_pct is not None and turnover_rate_pct >= 18.0)

    return {
        "available": True,
        "window_days": min(len(tail), 252),
        "yang_zhang_hv20_pct": yz20,
        "yang_zhang_hv60_pct": yz60,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "high_52w_ratio": high_52w_ratio,
        "drawdown_52w_pct": drawdown_52w_pct,
        "residual_mom_z": residual_mom_z,
        "residual_mom_window": residual_mom_window,
        "alpha_vs_spy_60d_pct": alpha_vs_spy_60d_pct,
        "beta_spy": beta_spy,
        "info_discreteness": info_discreteness,
        "id_label": id_label,
        "overnight_20d_pct": overnight_20d_pct,
        "intraday_20d_pct": intraday_20d_pct,
        "overnight_60d_pct": overnight_60d_pct,
        "intraday_60d_pct": intraday_60d_pct,
        "tug_of_war_state": tug_state,
        "tug_of_war_label": tug_label,
        "tug_of_war_warning": tug_warning,
        "max5_21d_pct": max5_21d_pct,
        "lottery_overheated": lottery_overheated,
        "downside_beta": downside_beta,
        "realized_skew_60d": realized_skew_60d,
        "amihud_20d": amihud_20d,
        "avg_dollar_vol_20d": avg_dollar_vol_20d,
        "illiquid_flag": illiquid_flag,
        "turnover_rate_pct": turnover_rate_pct,
        "market_cap": market_cap,
        "high_turnover_flag": high_turnover_flag,
    }
