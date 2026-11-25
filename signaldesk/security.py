from __future__ import annotations

import ctypes
import json
import os
import secrets
from pathlib import Path


def data_directory() -> Path:
    override = os.environ.get("SIGNALDESK_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "SignalDesk"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "signaldesk"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, decrypt: bool = False) -> bytes:
    buffer = ctypes.create_string_buffer(data)
    incoming = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = _Blob()
    crypt32 = ctypes.windll.crypt32
    if decrypt:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)
        )
    else:
        ok = crypt32.CryptProtectData(
            ctypes.byref(incoming), "SignalDesk credentials", None, None, None, 1, ctypes.byref(outgoing)
        )
    if not ok:
        raise OSError("Windows凭据加解密失败")
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(outgoing.pbData)


class Vault:
    """Secrets never enter public settings, API responses, subprocess environments or Git."""

    def __init__(self, directory: Path):
        self.directory = directory / "credentials"
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, service: str) -> Path:
        if service not in {"qq", "longport", "longbridge_client"}:
            raise ValueError("未知凭据服务")
        return self.directory / f"{service}.encrypted"

    def save(self, service: str, value: dict):
        raw = json.dumps(value).encode()
        if os.name == "nt":
            encrypted = b"DPAPI1:" + _dpapi(raw)
        else:
            from cryptography.fernet import Fernet

            key = os.environ.get("SIGNALDESK_VAULT_KEY")
            if not key:
                raise ValueError("Linux实盘需先设置SIGNALDESK_VAULT_KEY；不会回退为明文保存")
            encrypted = b"FERNET1:" + Fernet(key.encode()).encrypt(raw)
        path = self._path(service)
        temp = path.with_suffix(".tmp")
        temp.write_bytes(encrypted)
        if os.name != "nt":
            temp.chmod(0o600)
        temp.replace(path)

    def load(self, service: str) -> dict:
        path = self._path(service)
        if not path.exists():
            return {}
        data = path.read_bytes()
        if data.startswith(b"DPAPI1:") and os.name == "nt":
            raw = _dpapi(data[7:], decrypt=True)
        elif data.startswith(b"FERNET1:"):
            from cryptography.fernet import Fernet

            raw = Fernet(os.environ["SIGNALDESK_VAULT_KEY"].encode()).decrypt(data[8:])
        else:
            raise ValueError("凭据不属于此系统或格式不受支持")
        return json.loads(raw)

    def configured(self, service: str) -> bool:
        return self._path(service).exists()


def session_token() -> str:
    return secrets.token_urlsafe(32)


def safe_child_environment() -> dict[str, str]:
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "APPDATA",
        "LOCALAPPDATA",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
    # No LONGPORT_*, QQ_*, SIGNALDESK_VAULT_KEY or arbitrary inherited app credentials.
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def safe_snapshot(
    stock: dict,
    mode: str,
    macro: dict | None = None,
    gold: dict | None = None,
) -> dict:
    """Explicit allowlist instead of trying to redact an unbounded account object."""
    summaries = stock.get("summaries", {})
    plan = stock.get("long_plan", {})
    close = plan.get("close")
    plan_context = {k: plan.get(k) for k in ("status", "as_of", "basis", "watch_only")}
    for level in ("stop", "target"):
        plan_context[f"{level}_distance_percent"] = (
            (close / plan[level] - 1) * 100 if close and plan.get(level) else None
        )
    weight = stock.get("weight_percent")
    if weight is not None and stock.get("broker_quantity"):
        long_qty = stock.get("long_quantity")
        weight = weight * long_qty / stock["broker_quantity"] if long_qty is not None else None
    research = stock.get("research", {})
    instrument = stock.get("instrument") or {}
    is_fund = bool(instrument.get("is_fund"))
    fund_metrics = stock.get("fund_metrics") or {}
    forecast = stock.get("forecast", {})
    rating = forecast.get("rating", {})
    levels = forecast.get("levels", {})
    wt = stock.get("wave_trend", {})
    wt_trend = wt.get("trend", {})
    wt_wave = wt.get("wave", {})
    academic_factors = stock.get("academic_factors") or {}
    risk_budget = forecast.get("risk_budget") or {}
    raw_val = research.get("valuation", {})
    safe_valuation = (
        {
            "source": raw_val.get("source"),
            "company_valuation_applicable": False,
            "pe_ttm": None,
            "pb": None,
            "dividend_yield_pct": raw_val.get("dividend_yield_pct"),
            "turnover_rate_pct": None,
            "market_cap": None,
            "fetched_at": raw_val.get("fetched_at"),
            "fresh": raw_val.get("fresh"),
            "refresh_failed": raw_val.get("refresh_failed"),
        }
        if is_fund
        else {
            "company_valuation_applicable": True,
            **{
                k: raw_val.get(k)
                for k in (
                    "source",
                    "pe_ttm",
                    "pb",
                    "dividend_yield_pct",
                    "turnover_rate_pct",
                    "market_cap",
                    "fetched_at",
                    "fresh",
                    "refresh_failed",
                )
            },
        }
    )
    return {
        "source": mode,
        "symbol": stock["symbol"],
        "name": stock.get("name", ""),
        "instrument": {
            k: instrument.get(k)
            for k in (
                "asset_type",
                "type_label",
                "benchmark",
                "is_fund",
                "is_leveraged",
                "is_inverse",
                "leverage",
                "company_valuation_applicable",
                "risk_notice",
            )
        }
        if instrument
        else {},
        "fund_metrics": {
            k: fund_metrics.get(k)
            for k in (
                "available",
                "window_days",
                "high_52w",
                "low_52w",
                "drawdown_from_high_pct",
                "range_position_pct",
                "max_drawdown_pct",
                "hv20_pct",
                "hv60_pct",
                "ma200_gap_pct",
                "return_20d_pct",
                "return_60d_pct",
                "return_252d_pct",
            )
        }
        if is_fund and fund_metrics
        else {},
        "investment_horizon": "long",
        "long_position_assigned": "long" in stock.get("sleeves", []) and not stock.get("watch_only"),
        "position_weight_percent": weight if stock.get("reconciled", True) else None,
        "long_plan": plan_context,
        "forecast": {
            "rating": {
                k: rating.get(k) for k in ("code", "label", "score", "confidence")
            },
            "levels": {
                k: levels.get(k)
                for k in (
                    "available",
                    "buy_low",
                    "buy_high",
                    "sell_low",
                    "sell_high",
                    "stop_loss",
                    "risk_reward_ratio",
                )
            },
            "risk_budget": {
                k: risk_budget.get(k)
                for k in (
                    "available",
                    "yz_hv_pct",
                    "vol_scale",
                    "macro_red_count",
                    "macro_multiplier",
                    "macro_label",
                    "suggested_exposure_ratio",
                    "trailing_stop",
                    "peak_60d",
                    "trailing_drawdown_pct",
                    "trailing_breached",
                )
            }
            if risk_budget
            else {},
        }
        if forecast
        else {},
        "academic_factors": {
            k: academic_factors.get(k)
            for k in (
                "available",
                "window_days",
                "yang_zhang_hv20_pct",
                "yang_zhang_hv60_pct",
                "high_52w",
                "high_52w_ratio",
                "drawdown_52w_pct",
                "residual_mom_z",
                "residual_mom_window",
                "alpha_vs_spy_60d_pct",
                "beta_spy",
                "info_discreteness",
                "id_label",
                "overnight_20d_pct",
                "intraday_20d_pct",
                "tug_of_war_state",
                "tug_of_war_label",
                "tug_of_war_warning",
                "max5_21d_pct",
                "lottery_overheated",
                "downside_beta",
                "realized_skew_60d",
                "amihud_20d",
                "illiquid_flag",
                "turnover_rate_pct",
                "market_cap",
                "high_turnover_flag",
            )
        }
        if academic_factors
        else {},
        "wave_trend": {
            "available": wt.get("available"),
            "summary": wt.get("summary"),
            "trend": {
                k: wt_trend.get(k)
                for k in (
                    "direction",
                    "label",
                    "structure",
                    "channel_position_label",
                    "breakout_level",
                    "invalidation_level",
                )
            },
            "wave": {
                k: wt_wave.get(k)
                for k in ("pattern", "pattern_label", "current_wave", "phase_label", "confidence")
            },
        }
        if wt
        else {},
        "research": {
            "valuation": safe_valuation,
            "curve": {
                k: research.get("curve", {}).get(k)
                for k in (
                    "source",
                    "as_of",
                    "three_month",
                    "two_year",
                    "ten_year",
                    "spread_bp",
                    "spread_10y_3m_bp",
                    "recession_prob_12m_pct",
                    "ten_change_bp",
                    "prior_date",
                    "real_ten_year",
                    "fresh",
                    "refresh_failed",
                )
            },
            "gold": (
                {
                    k: gold.get(k)
                    for k in (
                        "available",
                        "symbol",
                        "name",
                        "exchange",
                        "currency",
                        "unit",
                        "price",
                        "prev_close",
                        "change_pct",
                        "day_high",
                        "day_low",
                        "prior_date",
                        "change_21d_pct",
                        "as_of",
                        "source",
                        "fresh",
                        "refresh_failed",
                        "real_ten_year",
                        "real_rate_linkage",
                    )
                }
                if isinstance(gold, dict) and gold
                else {}
            ),
            "earnings_yield_pct": None if is_fund else research.get("earnings_yield_pct"),
            "yield_gap_pp": None if is_fund else research.get("yield_gap_pp"),
            "real_ten_year": research.get("real_ten_year"),
            "real_yield_gap_pp": None if is_fund else research.get("real_yield_gap_pp"),
        },
        "macro_regime": (
            {
                "available": bool(macro.get("available")),
                "rule_version": macro.get("rule_version"),
                "source": macro.get("source"),
                "as_of": macro.get("as_of"),
                "quadrant": {
                    k: (macro.get("quadrant") or {}).get(k)
                    for k in ("code", "label", "liquidity_label", "trend_label")
                },
                "risk_gauge": {
                    k: (macro.get("risk_gauge") or {}).get(k)
                    for k in ("red_count", "yellow_count", "green_count", "available_count", "total_count", "label")
                },
                "alerts": list(macro.get("alerts") or [])[:5],
                "real_rate": {
                    k: (macro.get("real_rate") or {}).get(k)
                    for k in ("ten_year_real", "as_of", "fresh", "change_21d_bp")
                },
                "pillars": [
                    {
                        k: p.get(k)
                        for k in (
                            "key",
                            "label",
                            "light",
                            "light_label",
                            "primary_metric",
                            "percentile_10y",
                            "direction_13w",
                            "as_of",
                        )
                    }
                    for p in (macro.get("pillars") or [])
                    if isinstance(p, dict)
                ],
            }
            if macro
            else {}
        ),
        "market": {
            key: stock.get("quote", {}).get(key)
            for key in ["last", "timestamp", "trade_status", "session", "stale"]
        },
        "extended_hours": (
            {
                k: (stock.get("extended_hours") or {}).get(k)
                for k in (
                    "available",
                    "is_live_session",
                    "source",
                    "active_session",
                    "active_label",
                    "price",
                    "ref_close",
                    "gap_pct",
                    "high",
                    "low",
                    "turnover",
                    "turnover_text",
                    "timestamp",
                    "liquid",
                    "liquidity_label",
                    "alert_level",
                    "headline",
                    "triggers",
                    "tug_of_war",
                )
            }
            if stock.get("extended_hours")
            else {}
        ),
        "technical": {"day:regular": summaries["day:regular"]} if "day:regular" in summaries else {},
    }
