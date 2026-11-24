from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


Session = Literal["regular", "pre", "post", "overnight"]
Sleeve = Literal["long", "short", "unassigned"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Allocation(StrictModel):
    symbol: str
    name: str = ""
    long_quantity: float = Field(default=0, ge=0)
    short_quantity: float = Field(default=0, ge=0)
    # Unallocated broker quantity is reconciled by the service, never guessed.
    broker_quantity: float = Field(default=0, ge=0)
    available_quantity: float = Field(default=0, ge=0)
    cost_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    target_price: float | None = Field(default=None, gt=0)
    watch_only: bool = False
    watch_sleeve: Sleeve = "long"
    long_stop_price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    long_target_price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    favorite: bool = False
    in_watchlist: bool = False
    watchlist_groups: list[str] = Field(default_factory=list)
    manual_watch: bool = False

    @model_validator(mode="after")
    def migrate_levels(self):
        # Old mixed/short plans belonged to the tactical sleeve; never copy those into a long plan.
        if self.sleeves() == ["long"]:
            if "long_stop_price" not in self.model_fields_set:
                self.long_stop_price = self.stop_price
            if "long_target_price" not in self.model_fields_set:
                self.long_target_price = self.target_price
        return self

    def long_levels(self):
        return self.long_stop_price, self.long_target_price

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        import re

        value = value.strip().upper()
        if not value.endswith(".US"):
            value += ".US"
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}\.US", value):
            raise ValueError("请输入美股代码，例如 AAPL.US")
        return value

    @property
    def reconciled(self) -> bool:
        return abs(self.long_quantity + self.short_quantity - self.broker_quantity) < 1e-6

    def sleeves(self) -> list[Sleeve]:
        if self.watch_only and self.broker_quantity == 0:
            return [self.watch_sleeve]
        result: list[Sleeve] = []
        if self.long_quantity > 0:
            result.append("long")
        if self.short_quantity > 0:
            result.append("short")
        return result or ["unassigned"]


class RuleSettings(StrictModel):
    trend_weight: float = Field(default=0.45, ge=0, le=1)
    momentum_weight: float = Field(default=0.40, ge=0, le=1)
    volume_weight: float = Field(default=0.15, ge=0, le=1)
    strong_threshold: float = Field(default=70, gt=50, le=100)
    weak_threshold: float = Field(default=30, ge=0, lt=50)
    cooldown_minutes: int = Field(default=30, ge=1, le=1440)
    max_extended_spread: float = Field(default=0.005, gt=0, le=0.1)
    min_extended_turnover: float = Field(default=1_000_000, ge=0)

    @model_validator(mode="after")
    def weights_sum(self):
        if abs(self.trend_weight + self.momentum_weight + self.volume_weight - 1) > 1e-6:
            raise ValueError("三个维度权重之和必须为1")
        return self


class QQSettings(StrictModel):
    enabled: bool = False
    app_id: str = ""
    target_kind: Literal["user", "group"] = "user"
    target_openid: str = ""


class CodexSettings(StrictModel):
    enabled: bool = True
    automatic: bool = False
    daily_limit: int = Field(default=24, ge=0, le=500)
    cooldown_minutes: int = Field(default=30, ge=1, le=1440)
    timeout_seconds: int = Field(default=600, ge=15, le=900)


class Settings(StrictModel):
    mode: Literal["demo", "live"] = "demo"
    desktop_notifications: bool = True
    pause_ordinary: bool = False
    sync_watchlist: bool = True
    rules: RuleSettings = Field(default_factory=RuleSettings)
    qq: QQSettings = Field(default_factory=QQSettings)
    codex: CodexSettings = Field(default_factory=CodexSettings)


class AnalysisResult(StrictModel):
    conclusion: str = Field(max_length=1500)
    action: Literal["observe", "wait", "hold", "review_entry", "review_exit", "review_stop", "review_profit"]
    evidence: list[str] = Field(max_length=12)
    risks: list[str] = Field(max_length=12)
    confirmation_conditions: list[str] = Field(max_length=12)
    data_as_of: str


class Credentials(StrictModel):
    service: Literal["longport", "qq"]
    platform: Literal["longport", "longbridge"] | None = None
    app_key: str = ""
    app_secret: str = ""
    access_token: str = ""


class NotificationEnvelope(StrictModel):
    event_id: str
    symbol: str
    timeframe: str
    session: str
    severity: Literal["info", "warning", "critical"]
    title: str
    message: str
    evidence: list[str] = Field(default_factory=list, max_length=12)
    rule_version: str = ""
    score: float | None = None
    data_as_of: str
    source: Literal["demo", "live", "test"] = "live"
