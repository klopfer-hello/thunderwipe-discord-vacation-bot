"""Generate the absence heatmap image.

Styled to match the sibling project ``ForgasGuildCalendar-Sync`` —
dark slate background, warm gold accents, soft borders.

A 3x7 grid covering the current week + the next 2 weeks (21 days). Each row
is a week (Mo-So), each cell shows the date and the absence count, colored
from the group background (no one absent) through warm gold to deep red.
Weekend columns are dimmed; today is outlined in the accent gold.

The image is rendered at a near-square aspect ratio so Discord displays it
larger in the channel (very wide strips are auto-shrunk by Discord).
"""

from __future__ import annotations

import io
from datetime import date, timedelta

import matplotlib

matplotlib.use("Agg")  # headless: no display required

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
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

# Cell color: GROUP_BG -> warm gold -> deep red, on the dark background.
_CMAP = LinearSegmentedColormap.from_list(
    "absence_dark",
    [GROUP_BG, _rgb(120, 90, 50), ACCENT_COLOR, _rgb(230, 110, 60), _rgb(196, 31, 59)],
    N=256,
)


def _color_scale_max(counts: np.ndarray) -> float:
    """How many absences map to the darkest red?

    ``max(8, observed_max)`` keeps the gradient meaningful even when the
    dataset is small — a single vacation won't paint the whole grid red.
    """
    observed = float(counts.max()) if counts.size else 0.0
    return max(8.0, observed)


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
    vmax = _color_scale_max(counts)

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
        vmin=0,
        vmax=vmax,
        aspect="auto",
        origin="upper",
        extent=(-0.5, DAYS_PER_WEEK - 0.5, WEEKS - 0.5, -0.5),
        zorder=1,
    )

    # Per-cell decoration: weekend dimming, today highlight, date label, count.
    for r in range(WEEKS):
        for c in range(DAYS_PER_WEEK):
            day = days_grid[r, c]
            count = int(grid[r, c])

            if day.weekday() >= 5:  # Sa/So
                ax.add_patch(
                    Rectangle(
                        (c - 0.5, r - 0.5),
                        1,
                        1,
                        facecolor=(0.0, 0.0, 0.0, 0.35),
                        edgecolor="none",
                        zorder=2,
                    )
                )

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

            intensity = count / vmax if vmax else 0
            primary_text = TEXT_COLOR if intensity < 0.55 else (0.1, 0.08, 0.08)
            secondary_text = SUBTEXT_COLOR if intensity < 0.55 else (0.15, 0.12, 0.12)

            # Date in the upper-left of the cell (small, secondary).
            ax.text(
                c - 0.42,
                r - 0.38,
                day.strftime("%d.%m."),
                ha="left",
                va="top",
                fontsize=9,
                color=secondary_text,
                zorder=5,
            )

            # Count, large, centered.
            ax.text(
                c,
                r + 0.08,
                str(count),
                ha="center",
                va="center",
                fontsize=26,
                fontweight="bold",
                color=primary_text,
                zorder=5,
            )

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
