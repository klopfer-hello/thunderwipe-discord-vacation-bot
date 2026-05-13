"""Tests for utils.date_parser."""

from datetime import date, timedelta

import pytest

from utils.date_parser import (
    DateParseError,
    format_date,
    format_range,
    parse_date,
    validate_range,
)


class TestParseDate:
    def test_dd_mm_yyyy(self):
        assert parse_date("05.06.2026") == date(2026, 6, 5)

    def test_single_digit_day_and_month(self):
        assert parse_date("5.6.2026") == date(2026, 6, 5)

    def test_two_digit_year_is_treated_as_2000s(self):
        assert parse_date("05.06.26") == date(2026, 6, 5)

    def test_whitespace_is_trimmed(self):
        assert parse_date("  05.06.2026  ") == date(2026, 6, 5)

    def test_empty_string_raises(self):
        with pytest.raises(DateParseError) as exc:
            parse_date("")
        assert "fehlt" in str(exc.value)

    def test_only_whitespace_raises(self):
        with pytest.raises(DateParseError):
            parse_date("   ")

    def test_garbage_raises(self):
        with pytest.raises(DateParseError) as exc:
            parse_date("not a date")
        assert "TT.MM.JJJJ" in str(exc.value)

    def test_invalid_day_raises(self):
        with pytest.raises(DateParseError):
            parse_date("32.01.2026")

    def test_invalid_month_raises(self):
        with pytest.raises(DateParseError):
            parse_date("01.13.2026")

    def test_field_name_appears_in_error(self):
        with pytest.raises(DateParseError) as exc:
            parse_date("", field="Startdatum")
        assert "Startdatum" in str(exc.value)

    def test_iso_format_is_rejected(self):
        # We only accept DD.MM.YYYY — keep ISO out so user mistakes are loud.
        with pytest.raises(DateParseError):
            parse_date("2026-06-05")


class TestValidateRange:
    def _future(self, days_offset: int = 0) -> date:
        return date.today() + timedelta(days=days_offset)

    def test_valid_future_range_ok(self):
        validate_range(self._future(1), self._future(7))  # no exception

    def test_single_day_range_ok(self):
        d = self._future(1)
        validate_range(d, d)

    def test_end_before_start_raises(self):
        with pytest.raises(DateParseError) as exc:
            validate_range(self._future(7), self._future(1))
        assert "Enddatum" in str(exc.value)

    def test_fully_past_range_raises(self):
        with pytest.raises(DateParseError) as exc:
            validate_range(self._future(-10), self._future(-5))
        assert "Vergangenheit" in str(exc.value)

    def test_range_ending_today_ok(self):
        validate_range(self._future(-3), self._future(0))  # ends today, still allowed

    def test_range_over_one_year_raises(self):
        with pytest.raises(DateParseError) as exc:
            validate_range(self._future(1), self._future(400))
        assert "365" in str(exc.value)


class TestFormatters:
    def test_format_date(self):
        assert format_date(date(2026, 6, 5)) == "05.06.2026"

    def test_format_range_distinct_days(self):
        result = format_range(date(2026, 6, 5), date(2026, 6, 10))
        assert result == "05.06.2026 – 10.06.2026"

    def test_format_range_single_day(self):
        result = format_range(date(2026, 6, 5), date(2026, 6, 5))
        assert result == "05.06.2026"
