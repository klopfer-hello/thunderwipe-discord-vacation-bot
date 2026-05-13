"""Tests for the db.py SQLite path.

These tests instantiate a fresh `Database` against a temporary SQLite file
so the production `vacations.db` is never touched.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

import db as db_module
from db import Database, Vacation


@pytest.fixture
async def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    """A fresh Database wired to a per-test SQLite file."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(db_module, "SQLITE_PATH", str(tmp_path / "test.db"))
    database = Database()
    await database.connect()
    try:
        yield database
    finally:
        await database.close()


class TestAddAndDelete:
    async def test_add_returns_id(self, tmp_db: Database):
        new_id = await tmp_db.add_vacation(
            "1", "Alice", date(2026, 6, 1), date(2026, 6, 5)
        )
        assert isinstance(new_id, int)
        assert new_id > 0

    async def test_delete_only_own_row(self, tmp_db: Database):
        v_id = await tmp_db.add_vacation(
            "1", "Alice", date(2026, 6, 1), date(2026, 6, 5)
        )
        assert await tmp_db.delete_vacation(v_id, "2") is False  # wrong user
        assert await tmp_db.delete_vacation(v_id, "1") is True
        # Second delete returns False — already gone.
        assert await tmp_db.delete_vacation(v_id, "1") is False


class TestUpcomingForUser:
    async def test_excludes_fully_past(self, tmp_db: Database):
        past_start = date.today() - timedelta(days=20)
        past_end = date.today() - timedelta(days=10)
        await tmp_db.add_vacation("1", "Alice", past_start, past_end)
        assert await tmp_db.get_upcoming_vacations_for_user("1") == []

    async def test_includes_in_progress(self, tmp_db: Database):
        start = date.today() - timedelta(days=2)
        end = date.today() + timedelta(days=2)
        await tmp_db.add_vacation("1", "Alice", start, end)
        result = await tmp_db.get_upcoming_vacations_for_user("1")
        assert len(result) == 1
        assert result[0].username == "Alice"

    async def test_sorted_by_start_date_asc(self, tmp_db: Database):
        await tmp_db.add_vacation(
            "1",
            "Alice",
            date.today() + timedelta(days=20),
            date.today() + timedelta(days=25),
        )
        await tmp_db.add_vacation(
            "1",
            "Alice",
            date.today() + timedelta(days=1),
            date.today() + timedelta(days=5),
        )
        result = await tmp_db.get_upcoming_vacations_for_user("1")
        assert [v.start_date for v in result] == sorted(v.start_date for v in result)


class TestOverlapDetection:
    async def test_detects_full_overlap(self, tmp_db: Database):
        await tmp_db.add_vacation("1", "Alice", date(2026, 6, 10), date(2026, 6, 20))
        hits = await tmp_db.get_vacations_overlapping_for_user(
            "1", date(2026, 6, 12), date(2026, 6, 15)
        )
        assert len(hits) == 1

    async def test_detects_partial_overlap_at_start(self, tmp_db: Database):
        await tmp_db.add_vacation("1", "Alice", date(2026, 6, 10), date(2026, 6, 20))
        hits = await tmp_db.get_vacations_overlapping_for_user(
            "1", date(2026, 6, 5), date(2026, 6, 12)
        )
        assert len(hits) == 1

    async def test_adjacent_ranges_overlap_at_touching_day(self, tmp_db: Database):
        # Inclusive end_date: a range ending on the 10th and one starting on
        # the 10th share that single day, so they SHOULD count as overlapping.
        await tmp_db.add_vacation("1", "Alice", date(2026, 6, 1), date(2026, 6, 10))
        hits = await tmp_db.get_vacations_overlapping_for_user(
            "1", date(2026, 6, 10), date(2026, 6, 20)
        )
        assert len(hits) == 1

    async def test_non_overlapping_returns_empty(self, tmp_db: Database):
        await tmp_db.add_vacation("1", "Alice", date(2026, 6, 1), date(2026, 6, 5))
        hits = await tmp_db.get_vacations_overlapping_for_user(
            "1", date(2026, 7, 1), date(2026, 7, 5)
        )
        assert hits == []

    async def test_only_returns_same_user(self, tmp_db: Database):
        await tmp_db.add_vacation("1", "Alice", date(2026, 6, 10), date(2026, 6, 20))
        hits = await tmp_db.get_vacations_overlapping_for_user(
            "2", date(2026, 6, 12), date(2026, 6, 15)
        )
        assert hits == []


class TestAbsentOn:
    async def test_includes_users_active_on_target(self, tmp_db: Database):
        await tmp_db.add_vacation("1", "Alice", date(2026, 6, 1), date(2026, 6, 10))
        await tmp_db.add_vacation("2", "Bob", date(2026, 6, 5), date(2026, 6, 15))
        absent = await tmp_db.get_absent_on(date(2026, 6, 7))
        names = sorted(v.username for v in absent)
        assert names == ["Alice", "Bob"]

    async def test_excludes_users_outside_range(self, tmp_db: Database):
        await tmp_db.add_vacation("1", "Alice", date(2026, 6, 1), date(2026, 6, 5))
        absent = await tmp_db.get_absent_on(date(2026, 6, 10))
        assert absent == []

    async def test_boundary_days_are_inclusive(self, tmp_db: Database):
        await tmp_db.add_vacation("1", "Alice", date(2026, 6, 1), date(2026, 6, 5))
        start_hits = await tmp_db.get_absent_on(date(2026, 6, 1))
        end_hits = await tmp_db.get_absent_on(date(2026, 6, 5))
        assert len(start_hits) == 1
        assert len(end_hits) == 1


class TestAbsenceCounts:
    async def test_counts_distinct_users_per_day(self, tmp_db: Database):
        # Two overlapping vacations from the same user should not double-count.
        await tmp_db.add_vacation("1", "Alice", date(2026, 6, 1), date(2026, 6, 5))
        await tmp_db.add_vacation("1", "Alice", date(2026, 6, 3), date(2026, 6, 8))
        counts = await tmp_db.get_absence_counts_for_range(
            date(2026, 6, 1), date(2026, 6, 8)
        )
        # Every day in the window has exactly one distinct user absent.
        assert all(c == 1 for c in counts.values())

    async def test_returns_zero_for_days_with_no_absences(self, tmp_db: Database):
        counts = await tmp_db.get_absence_counts_for_range(
            date(2026, 6, 1), date(2026, 6, 3)
        )
        assert counts == {
            date(2026, 6, 1): 0,
            date(2026, 6, 2): 0,
            date(2026, 6, 3): 0,
        }


class TestConfigKV:
    async def test_set_then_get_roundtrip(self, tmp_db: Database):
        await tmp_db.set_config("foo", "bar")
        assert await tmp_db.get_config("foo") == "bar"

    async def test_upsert_overwrites_existing_value(self, tmp_db: Database):
        await tmp_db.set_config("foo", "old")
        await tmp_db.set_config("foo", "new")
        assert await tmp_db.get_config("foo") == "new"

    async def test_missing_key_returns_none(self, tmp_db: Database):
        assert await tmp_db.get_config("never-set") is None


class TestRowToVacation:
    def test_string_dates_are_parsed(self):
        v = Database._row_to_vacation(
            {
                "id": 1,
                "user_id": "1",
                "username": "Alice",
                "start_date": "2026-06-01",
                "end_date": "2026-06-05",
            }
        )
        assert isinstance(v, Vacation)
        assert v.start_date == date(2026, 6, 1)
        assert v.end_date == date(2026, 6, 5)
