"""Tests for charts.heatmap."""

from datetime import date, timedelta

from charts.heatmap import DAYS_TO_SHOW, generate_heatmap


class TestGenerateHeatmap:
    def test_empty_counts_returns_png(self):
        buf = generate_heatmap({})
        data = buf.getvalue()
        assert data.startswith(b"\x89PNG\r\n\x1a\n"), "expected PNG magic bytes"
        assert len(data) > 1000  # at least a few KB of pixels

    def test_handles_populated_counts(self):
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        counts = {monday + timedelta(days=i): i for i in range(DAYS_TO_SHOW)}
        buf = generate_heatmap(counts)
        assert buf.getvalue().startswith(b"\x89PNG")

    def test_extra_dates_outside_window_are_ignored(self):
        far_future = date.today() + timedelta(days=400)
        far_past = date.today() - timedelta(days=400)
        buf = generate_heatmap({far_future: 99, far_past: 99})
        # Should still render fine; out-of-window keys are ignored.
        assert buf.getvalue().startswith(b"\x89PNG")

    def test_buffer_is_positioned_at_start(self):
        buf = generate_heatmap({})
        # Caller should be able to .read() directly without seeking.
        assert buf.tell() == 0

    def test_negative_or_huge_counts_dont_crash(self):
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        counts = {monday: 1000, monday + timedelta(days=1): 0}
        buf = generate_heatmap(counts)
        assert buf.getvalue().startswith(b"\x89PNG")
