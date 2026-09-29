from datetime import datetime, timezone

from app.service import as_utc


def test_as_utc_adds_utc_to_naive_datetime():
    dt = datetime(2026, 9, 29, 9, 57, 43)
    fixed = as_utc(dt)
    assert fixed is not None
    assert fixed.tzinfo == timezone.utc


def test_as_utc_keeps_aware_datetime():
    dt = datetime(2026, 9, 29, 9, 57, 43, tzinfo=timezone.utc)
    assert as_utc(dt) == dt
