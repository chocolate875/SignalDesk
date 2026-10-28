"""Small, independent, point-in-time operator registry; no eval or future offsets."""
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Operator:
    name: str
    fn: Callable
    description: str
    windowed: bool = True


def _window(window: int) -> int:
    if not isinstance(window, int) or isinstance(window, bool) or window < 1:
        raise ValueError("window必须为正整数，不允许未来窗口")
    return window


def delay(x: pd.Series, window: int = 1) -> pd.Series:
    return x.shift(_window(window))


def delta(x: pd.Series, window: int = 1) -> pd.Series:
    return x - delay(x, window)


def returns(x: pd.Series, window: int = 1) -> pd.Series:
    base = delay(x, window).replace(0, np.nan)
    return x / base - 1


def mean(x: pd.Series, window: int) -> pd.Series:
    return x.rolling(_window(window), min_periods=window).mean()


def std(x: pd.Series, window: int) -> pd.Series:
    return x.rolling(_window(window), min_periods=window).std(ddof=0)


def ts_min(x: pd.Series, window: int) -> pd.Series:
    return x.rolling(_window(window), min_periods=window).min()


def ts_max(x: pd.Series, window: int) -> pd.Series:
    return x.rolling(_window(window), min_periods=window).max()


def ts_rank(x: pd.Series, window: int) -> pd.Series:
    return x.rolling(_window(window), min_periods=window).rank(pct=True)


def zscore(x: pd.Series, window: int) -> pd.Series:
    return (x - mean(x, window)) / std(x, window).replace(0, np.nan)


def corr(x: pd.Series, other: pd.Series, window: int) -> pd.Series:
    return x.rolling(_window(window), min_periods=window).corr(other).replace([np.inf, -np.inf], np.nan)


def clip(x: pd.Series, lower: float = -1, upper: float = 1) -> pd.Series:
    if lower > upper:
        raise ValueError("lower不得大于upper")
    return x.clip(lower, upper)


REGISTRY = {
    name: Operator(name, fn, description, name != "clip")
    for name, fn, description in [
        ("delay", delay, "仅向过去取值"), ("delta", delta, "与过去值之差"),
        ("returns", returns, "无填充收益率"), ("mean", mean, "完整窗口均值"),
        ("std", std, "总体标准差ddof=0"), ("min", ts_min, "滚动最小"),
        ("max", ts_max, "滚动最大"), ("ts_rank", ts_rank, "当前值在历史窗口中的百分位，平均秩"),
        ("zscore", zscore, "零方差返回不可用"), ("corr", corr, "同时间索引相关性"),
        ("clip", clip, "有界裁剪"),
    ]
}


def evaluate(name: str, *args, **kwargs) -> pd.Series:
    if name not in REGISTRY:
        raise ValueError("未注册的算子")
    return REGISTRY[name].fn(*args, **kwargs)
