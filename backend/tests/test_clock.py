from datetime import date, datetime, timezone

import pytest

from app.core.clock import FixedClock, SystemClock, require_aware


def test_fixed_clock_converts_business_date_by_timezone():
    clock = FixedClock(
        datetime(2026, 7, 31, 16, 30, tzinfo=timezone.utc), "Asia/Shanghai"
    )
    assert clock.now() == datetime(2026, 7, 31, 16, 30, tzinfo=timezone.utc)
    assert clock.today() == date(2026, 8, 1)


def test_clock_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        require_aware(datetime(2026, 8, 1, 12, 0))


def test_system_clock_is_timezone_aware():
    now = SystemClock("Asia/Shanghai").now()
    assert now.tzinfo is not None
    assert now.utcoffset() is not None
