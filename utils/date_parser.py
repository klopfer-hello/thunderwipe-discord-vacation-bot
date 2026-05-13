"""Parse DD.MM.YYYY dates with friendly German error messages."""

from __future__ import annotations

from datetime import date, datetime


class DateParseError(ValueError):
    """Raised when the user supplies an unparseable or invalid date."""


def parse_date(raw: str, *, field: str = "Datum") -> date:
    """Parse a DD.MM.YYYY string into a `date`.

    Accepts a few common variations: ``5.6.2026``, ``05.06.26``, ``05.06.2026``.
    Raises ``DateParseError`` with a German message on failure.
    """
    text = (raw or "").strip()
    if not text:
        raise DateParseError(f"{field} fehlt. Bitte im Format TT.MM.JJJJ angeben.")

    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            parsed = datetime.strptime(text, fmt).date()
            if fmt == "%d.%m.%y" and parsed.year < 2000:
                parsed = parsed.replace(year=parsed.year + 100)
            return parsed
        except ValueError:
            continue

    raise DateParseError(
        f"„{raw}“ ist kein gültiges {field}. Bitte im Format TT.MM.JJJJ angeben "
        f"(z.B. 05.06.2026)."
    )


def validate_range(start: date, end: date) -> None:
    """Check that a start/end pair makes sense. Raises ``DateParseError`` otherwise."""
    if end < start:
        raise DateParseError(
            "Das Enddatum liegt vor dem Startdatum. Bitte korrigiere die Reihenfolge."
        )
    today = date.today()
    if end < today:
        raise DateParseError(
            "Dieser Urlaub liegt komplett in der Vergangenheit – Eintrag nicht nötig."
        )
    span_days = (end - start).days + 1
    if span_days > 365:
        raise DateParseError(
            "Der Urlaub umfasst mehr als 365 Tage. Bitte teile ihn in kleinere Einträge auf."
        )


def format_date(d: date) -> str:
    """Render a date as DD.MM.YYYY."""
    return d.strftime("%d.%m.%Y")


def format_range(start: date, end: date) -> str:
    if start == end:
        return format_date(start)
    return f"{format_date(start)} – {format_date(end)}"
