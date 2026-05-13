"""Officer-only query commands."""

from __future__ import annotations

from datetime import date, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from db import db
from utils.date_parser import DateParseError, format_date, format_range, parse_date
from utils.permissions import is_officer

# How long "no entries" responses stay before vanishing. Data results stay
# until the user dismisses them, since they may want to scroll/refer back.
EMPTY_RESULT_AUTODELETE = 10.0


def _chunk_lines(lines: list[str], max_chars: int = 1900) -> list[str]:
    """Split a list of pre-formatted lines into Discord-safe message chunks."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        added = len(line) + 1  # account for newline
        if current_len + added > max_chars and current:
            chunks.append("\n".join(current))
            current = [line]
            current_len = added
        else:
            current.append(line)
            current_len += added
    if current:
        chunks.append("\n".join(current))
    return chunks


class QueryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------------------------------------------- /fehlende

    @app_commands.command(
        name="fehlende",
        description="Officer: Wer ist an einem bestimmten Tag abwesend?",
    )
    @app_commands.describe(datum="Datum (TT.MM.JJJJ)")
    @is_officer()
    async def fehlende(self, interaction: discord.Interaction, datum: str) -> None:
        try:
            target = parse_date(datum, field="Datum")
        except DateParseError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        absent = await db.get_absent_on(target)
        if not absent:
            await interaction.response.send_message(
                f"✅ Am **{format_date(target)}** ist niemand als abwesend eingetragen.",
                ephemeral=True,
                delete_after=EMPTY_RESULT_AUTODELETE,
            )
            return

        lines = [
            f"• **{v.username}** ({format_range(v.start_date, v.end_date)})"
            for v in absent
        ]
        header = f"📋 **{len(absent)} abwesend am {format_date(target)}:**"
        await interaction.response.send_message(
            "\n".join([header, *lines]), ephemeral=True
        )

    # -------------------------------------------------------------- /urlaube_anzeigen

    @app_commands.command(
        name="urlaube_anzeigen",
        description="Officer: Alle Urlaube in den nächsten N Tagen anzeigen.",
    )
    @app_commands.describe(tage="Wie viele Tage in die Zukunft (Standard: 30)")
    @is_officer()
    async def urlaube_anzeigen(
        self,
        interaction: discord.Interaction,
        tage: app_commands.Range[int, 1, 365] = 30,
    ) -> None:
        today = date.today()
        end = today + timedelta(days=tage - 1)
        vacations = await db.get_vacations_in_range(today, end)

        if not vacations:
            await interaction.response.send_message(
                f"Keine Urlaube in den nächsten **{tage}** Tagen eingetragen.",
                ephemeral=True,
                delete_after=EMPTY_RESULT_AUTODELETE,
            )
            return

        # Group by start_date for readable output
        lines = [
            f"📅 **Urlaube vom {format_date(today)} bis {format_date(end)}** "
            f"({len(vacations)} Einträge):",
            "",
        ]
        current_start: date | None = None
        for v in vacations:
            if v.start_date != current_start:
                if current_start is not None:
                    lines.append("")
                lines.append(f"**{format_date(v.start_date)}**")
                current_start = v.start_date
            lines.append(f"• {v.username} ({format_range(v.start_date, v.end_date)})")

        chunks = _chunk_lines(lines)
        await interaction.response.send_message(chunks[0], ephemeral=True)
        for extra in chunks[1:]:
            await interaction.followup.send(extra, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(QueryCog(bot))
