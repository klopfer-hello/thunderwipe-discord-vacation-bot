"""Generate the absence heatmap image.

Styled to match the sibling project ``ForgasGuildCalendar-Sync`` —
dark slate background, warm gold accents, soft borders.

A 3x7 grid covering the current week + the next 2 weeks (21 days). Each row
is a week (Mo-So), each cell shows the date and the absence count, colored
via discrete buckets (steps of 5 absences — see ``BUCKET_BOUNDARIES``) so the
visual jump matches the guild's intuition that a handful of absences is no
concern, while many are. Today is outlined in the accent gold.

The image is rendered at a near-square aspect ratio so Discord displays it
larger in the channel (very wide strips are auto-shrunk by Discord).
"""

from __future__ import annotations

import io
from datetime import date, timedelta

import matplotlib

matplotlib.use("Agg")  # headless: no display required

import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Rectangle

DAYS_TO_SHOW = 21  # current week + 2 more weeks
WEEKS = 3
DAYS_PER_WEEK = 7

# ---------------------------------------------------------------- palette
# Mirrors ForgasGuildCalendar-Sync (Pillow values converted to /255 floats).


def _rgb(r: int, g: int, b: int) -> tuple[float, float, float]:
    return (r / 255, g / 255, b / 255)


BG_COLOR = _rgb(32, 32, 40)  # outer figure background
GROUP_BG = _rgb(38, 38, 50)  # base cell color (= 0 absences)
HEADER_BG = _rgb(44, 44, 56)
GROUP_HEADER_BG = _rgb(50, 50, 65)
BORDER_COLOR = _rgb(60, 60, 80)
TEXT_COLOR = _rgb(220, 220, 220)
SUBTEXT_COLOR = _rgb(160, 160, 170)
ACCENT_COLOR = _rgb(255, 183, 77)  # warm gold

_WEEKDAY_LABELS_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Discrete buckets, in steps of 5 absences. The guild has ~100 members, so a
# handful of people on vacation is no big deal; the colour scale is calibrated
# to reflect that intuition rather than panicking at the first absence.
#
#   0-4   : background (no concern)
#   5-9   : muted green (mild)
#   10-14 : olive amber (worth noticing)
#   15-19 : orange (concerning)
#   20-24 : red (high)
#   25+   : deep red (critical)
#
# All non-background colours are dark enough that the white in-cell text stays
# readable; a soft black outline (via path_effects) handles the lighter shades.
BUCKET_BOUNDARIES = [0, 5, 10, 15, 20, 25, float("inf")]
BUCKET_COLORS = [
    GROUP_BG,  # 0-4
    _rgb(60, 95, 65),  # 5-9
    _rgb(125, 100, 35),  # 10-14
    _rgb(170, 90, 35),  # 15-19
    _rgb(170, 50, 50),  # 20-24
    _rgb(115, 25, 40),  # 25+
]
_CMAP = ListedColormap(BUCKET_COLORS, name="absence_buckets")
_NORM = BoundaryNorm(BUCKET_BOUNDARIES, _CMAP.N)

# Subtle black outline around in-cell text so it stays legible on every
# bucket colour without having to flip between light and dark text fills.
_TEXT_OUTLINE = [
    path_effects.Stroke(linewidth=2.2, foreground=(0, 0, 0, 0.7)),
    path_effects.Normal(),
]


def generate_heatmap(absence_counts: dict[date, int]) -> io.BytesIO:
    """Build the heatmap PNG.

    Args:
        absence_counts: ``{day: number_of_members_absent}``. Missing days default to 0.

    Returns:
        BytesIO containing a PNG, ready to wrap in ``discord.File``.
    """
    today = date.today()
    start = today - timedelta(days=today.weekday())  # Monday of this week
    days = [start + timedelta(days=i) for i in range(DAYS_TO_SHOW)]
    counts = np.array([absence_counts.get(d, 0) for d in days], dtype=float)

    # Reshape into 3 weeks (rows) × 7 weekdays (columns).
    # Row 0 = top = current week.
    grid = counts.reshape(WEEKS, DAYS_PER_WEEK)
    days_grid = np.array(days, dtype=object).reshape(WEEKS, DAYS_PER_WEEK)

    fig, ax = plt.subplots(figsize=(8.4, 5.0))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    # imshow draws the grid; origin='upper' makes row 0 (current week) the top row.
    ax.imshow(
        grid,
        cmap=_CMAP,
        norm=_NORM,
        aspect="auto",
        origin="upper",
        extent=(-0.5, DAYS_PER_WEEK - 0.5, WEEKS - 0.5, -0.5),
        zorder=1,
    )

    # Per-cell decoration: today highlight, date label, count.
    for r in range(WEEKS):
        for c in range(DAYS_PER_WEEK):
            day = days_grid[r, c]
            count = int(grid[r, c])

            if day == today:
                ax.add_patch(
                    Rectangle(
                        (c - 0.5 + 0.04, r - 0.5 + 0.04),
                        1 - 0.08,
                        1 - 0.08,
                        facecolor="none",
                        edgecolor=ACCENT_COLOR,
                        linewidth=2.6,
                        zorder=4,
                    )
                )

            # Uniform light text fills with a subtle dark outline (path_effects)
            # so both the date label and the count stay legible against every
            # bucket colour — no more flipping to dark text on lighter cells.

            # Date in the upper-left of the cell (small, secondary).
            date_label = ax.text(
                c - 0.42,
                r - 0.38,
                day.strftime("%d.%m."),
                ha="left",
                va="top",
                fontsize=9,
                color=SUBTEXT_COLOR,
                zorder=5,
            )
            date_label.set_path_effects(_TEXT_OUTLINE)

            # Count, large, centered.
            count_text = ax.text(
                c,
                r + 0.08,
                str(count),
                ha="center",
                va="center",
                fontsize=26,
                fontweight="bold",
                color=TEXT_COLOR,
                zorder=5,
            )
            count_text.set_path_effects(_TEXT_OUTLINE)

    # ----- Column headers (weekday names, German) along the top
    ax.set_xticks(range(DAYS_PER_WEEK))
    ax.set_xticklabels(
        _WEEKDAY_LABELS_DE, fontsize=11, color=SUBTEXT_COLOR, fontweight="bold"
    )
    ax.xaxis.tick_top()
    ax.tick_params(axis="x", length=0, pad=8, colors=SUBTEXT_COLOR)

    # If today is in the visible range, gild the matching weekday header.
    today_col = today.weekday()
    if any(d == today for d in days):
        ax.get_xticklabels()[today_col].set_color(ACCENT_COLOR)

    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Soft grid lines between cells.
    for c in range(DAYS_PER_WEEK + 1):
        ax.axvline(c - 0.5, color=BORDER_COLOR, linewidth=0.8, zorder=3)
    for r in range(WEEKS + 1):
        ax.axhline(r - 0.5, color=BORDER_COLOR, linewidth=0.8, zorder=3)

    title = (
        f"Abwesenheitsübersicht  ·  "
        f"{days[0].strftime('%d.%m.')} – {days[-1].strftime('%d.%m.%Y')}"
    )
    ax.set_title(title, fontsize=14, pad=18, color=TEXT_COLOR, fontweight="bold")

    # A little breathing room around the grid.
    ax.set_xlim(-0.55, DAYS_PER_WEEK - 0.45)
    ax.set_ylim(WEEKS - 0.45, -0.55)

    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=170,
        bbox_inches="tight",
        facecolor=BG_COLOR,
        edgecolor="none",
    )
    buf.seek(0)
    plt.close(fig)
    return buf
