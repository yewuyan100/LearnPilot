from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    """Business time seam. ``now`` is always UTC-aware; ``today`` is local."""

    def now(self) -> datetime: ...

    def today(self) -> date: ...


def require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Clock values must be timezone-aware")
    return value


def as_utc(value: datetime) -> datetime:
    return require_aware(value).astimezone(timezone.utc)


@dataclass(frozen=True)
class SystemClock:
    timezone_name: str

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def today(self) -> date:
        return self.now().astimezone(self.zone).date()


@dataclass(frozen=True)
class FixedClock:
    instant: datetime
    timezone_name: str

    def __post_init__(self) -> None:
        require_aware(self.instant)
        ZoneInfo(self.timezone_name)

    def now(self) -> datetime:
        return as_utc(self.instant)

    def today(self) -> date:
        return self.now().astimezone(ZoneInfo(self.timezone_name)).date()


def clock_from_settings(settings) -> Clock:
    fixed = settings.clock_fixed_now or settings.adaptive_fixed_now
    if fixed is not None:
        return FixedClock(require_aware(fixed), settings.app_timezone)
    return SystemClock(settings.app_timezone)
