"""Query commands — moderator listings plus self-service views."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from db import Vacation, db
from utils.date_parser import DateParseError, format_date, format_range, parse_date
from utils.permissions import is_moderator, member_is_moderator

log = logging.getLogger(__name__)

# How long "no entries" responses stay before vanishing. Data results stay
# until the user dismisses them, since they may want to scroll/refer back.
EMPTY_RESULT_AUTODELETE = 10.0


async def _resolve_member_name(guild: discord.Guild | None, vacation: Vacation) -> str:
    """Return the member's current display_name, refreshing the DB if stale.

    Discord allows members to change their username, global display name, or
    per-guild nickname at any time. We snapshotted ``display_name`` at the
    moment of ``/urlaub``, so without this lookup officer queries would show
    the stale text. Lookup is cache-only (no API roundtrip); the bot is
    configured with ``Intents.members`` so the cache is warm.

    Side-effect: if the live display_name differs from what's in the DB,
    every row for this user_id is updated so subsequent queries don't have
    to refresh again.
    """
    if guild is None:
        return vacation.username
    member = guild.get_member(int(vacation.user_id))
    if member is None:
        # Member has left the guild (or isn't cached); keep the last name we
        # know to avoid showing a bare user_id in the output.
        return vacation.username
    current = member.display_name
    if current != vacation.username:
        try:
            await db.update_username_for_user(vacation.user_id, current)
        except Exception:
            # Failing to persist isn't fatal — we still want to display
            # the current name to the requesting officer.
            log.exception("Failed to refresh username for user_id=%s", vacation.user_id)
    return current


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
    @is_moderator()
    async def fehlende(self, interaction: discord.Interaction, datum: str) -> None:
        try:
            target = parse_date(datum, field="Datum")
        except DateParseError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        absent = await db.get_absent_on(target)
        if not absent:
            await interaction.followup.send(
                f"✅ Am **{format_date(target)}** ist niemand als abwesend eingetragen.",
                ephemeral=True,
            )
            return

        lines = [
            f"• **{await _resolve_member_name(interaction.guild, v)}** "
            f"({format_range(v.start_date, v.end_date)})"
            for v in absent
        ]
        header = f"📋 **{len(absent)} abwesend am {format_date(target)}:**"
        await interaction.followup.send("\n".join([header, *lines]), ephemeral=True)

    # -------------------------------------------------------------- /urlaube_anzeigen

    @app_commands.command(
        name="urlaube_anzeigen",
        description="Urlaube in den nächsten N Tagen anzeigen (Nicht-Moderatoren sehen nur ihre eigenen).",
    )
    @app_commands.describe(tage="Wie viele Tage in die Zukunft (Standard: 30)")
    async def urlaube_anzeigen(
        self,
        interaction: discord.Interaction,
        tage: app_commands.Range[int, 1, 365] = 30,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        today = date.today()
        end = today + timedelta(days=tage - 1)
        is_mod = member_is_moderator(interaction.user)
        vacations = await db.get_vacations_in_range(today, end)
        if not is_mod:
            user_id = str(interaction.user.id)
            vacations = [v for v in vacations if v.user_id == user_id]

        if not vacations:
            empty = (
                f"Keine Urlaube in den nächsten **{tage}** Tagen eingetragen."
                if is_mod
                else f"Du hast keine Urlaube in den nächsten **{tage}** Tagen eingetragen."
            )
            await interaction.followup.send(empty, ephemeral=True)
            return

        # Group by start_date for readable output
        header = (
            f"📅 **Urlaube vom {format_date(today)} bis {format_date(end)}** "
            f"({len(vacations)} Einträge):"
            if is_mod
            else f"📅 **Deine Urlaube vom {format_date(today)} bis {format_date(end)}** "
            f"({len(vacations)} Einträge):"
        )
        lines = [header, ""]
        current_start: date | None = None
        for v in vacations:
            if v.start_date != current_start:
                if current_start is not None:
                    lines.append("")
                lines.append(f"**{format_date(v.start_date)}**")
                current_start = v.start_date
            name = (
                await _resolve_member_name(interaction.guild, v)
                if is_mod
                else v.username
            )
            lines.append(f"• {name} ({format_range(v.start_date, v.end_date)})")

        chunks = _chunk_lines(lines)
        for chunk in chunks:
            await interaction.followup.send(chunk, ephemeral=True)

    # -------------------------------------------------------------- /meine_urlaube

    @app_commands.command(
        name="meine_urlaube",
        description="Zeige deine eigenen anstehenden Urlaube.",
    )
    async def meine_urlaube(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)
        vacations = await db.get_upcoming_vacations_for_user(user_id)

        if not vacations:
            await interaction.followup.send(
                "Du hast keine eingetragenen Urlaube.", ephemeral=True
            )
            return

        lines = [f"📅 **Deine Urlaube** ({len(vacations)} Einträge):", ""]
        for v in vacations:
            lines.append(f"• {format_range(v.start_date, v.end_date)}")

        chunks = _chunk_lines(lines)
        for chunk in chunks:
            await interaction.followup.send(chunk, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(QueryCog(bot))
