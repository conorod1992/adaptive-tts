"""Tests for quiet-hours helpers."""

from datetime import time

from custom_components.adaptive_tts.helpers import is_time_in_range


def test_range_crossing_midnight() -> None:
    """A quiet range crossing midnight includes both sides of midnight."""
    assert is_time_in_range(time(23, 30), "23:00:00", "07:00:00")
    assert is_time_in_range(time(6, 59), "23:00:00", "07:00:00")
    assert not is_time_in_range(time(12, 0), "23:00:00", "07:00:00")


def test_normal_range_and_equal_boundaries() -> None:
    """Normal ranges and a full-day equal-boundary policy work."""
    assert is_time_in_range(time(12, 0), "08:00:00", "17:00:00")
    assert not is_time_in_range(time(17, 0), "08:00:00", "17:00:00")
    assert is_time_in_range(time(12, 0), "00:00:00", "00:00:00")
