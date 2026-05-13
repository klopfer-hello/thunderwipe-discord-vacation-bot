"""Member-facing slash commands: register and delete vacations."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from db import Vacation, db
from utils.date_parser import (
    DateParseError,
    format_range,
    parse_date,
    validate_range,
)
from utils.pinned_heatmap import refresh_heatmap

log = logging.getLogger(__name__)

# How long ephemeral success / "nothing to do" messages stay before vanishing.
# Errors and actionable warnings stay until the user dismisses them.
EPHEMERAL_AUTODELETE = 10.0


async def _delete_response_later(
    interaction: discord.Interaction, delay: float
) -> None:
    """Delete an interaction's original response after `delay` seconds."""
    await asyncio.sleep(delay)
    with contextlib.suppress(discord.NotFound, discord.HTTPException):
        await interaction.delete_original_response()


def _vacation_channel_id() -> int:
    raw = os.getenv("VACATION_CHANNEL_ID", "").strip()
    try:
        return int(raw) if raw else 0
    except ValueError:
        return 0


def _wrong_channel_message(channel_id: int) -> str:
    return (
        f"❌ Dieser Befehl ist nur in <#{channel_id}> erlaubt."
        if channel_id
        else "❌ Dieser Befehl ist hier nicht erlaubt."
    )


class VacationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------------------------------------------- /urlaub

    @app_commands.command(
        name="urlaub",
        description="Trag deinen Urlaub ein (TT.MM.JJJJ).",
    )
    @app_commands.describe(
        start="Startdatum (TT.MM.JJJJ)",
        end="Enddatum (TT.MM.JJJJ)",
    )
    async def urlaub(
        self,
        interaction: discord.Interaction,
        start: str,
        end: str,
    ) -> None:
        channel_id = _vacation_channel_id()
        if channel_id and interaction.channel_id != channel_id:
            await interaction.response.send_message(
                _wrong_channel_message(channel_id), ephemeral=True
            )
            return

        try:
            start_d = parse_date(start, field="Startdatum")
            end_d = parse_date(end, field="Enddatum")
            validate_range(start_d, end_d)
        except DateParseError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        username = interaction.user.display_name

        existing = await db.get_vacations_overlapping_for_user(user_id, start_d, end_d)
        if existing:
            lines = "\n".join(
                f"• {format_range(v.start_date, v.end_date)}" for v in existing
            )
            await interaction.response.send_message(
                "⚠️ Du hast bereits einen überlappenden Urlaub eingetragen:\n"
                f"{lines}\n\nBitte lösche den alten Eintrag zuerst mit `/urlaub_loeschen`.",
                ephemeral=True,
            )
            return

        await db.add_vacation(user_id, username, start_d, end_d)

        await interaction.response.send_message(
            f"✅ Urlaub eingetragen: **{format_range(start_d, end_d)}**.",
            ephemeral=True,
            delete_after=EPHEMERAL_AUTODELETE,
        )

        # Update the pinned heatmap silently in the background.
        try:
            await refresh_heatmap(self.bot, db)
        except Exception:
            log.exception("refresh_heatmap failed after /urlaub")

    # -------------------------------------------------------------- /urlaub_loeschen

    @app_commands.command(
        name="urlaub_loeschen",
        description="Lösche einen deiner eingetragenen Urlaube.",
    )
    async def urlaub_loeschen(self, interaction: discord.Interaction) -> None:
        user_id = str(interaction.user.id)
        vacations = await db.get_upcoming_vacations_for_user(user_id)

        if not vacations:
            await interaction.response.send_message(
                "Du hast keine eingetragenen Urlaube.",
                ephemeral=True,
                delete_after=EPHEMERAL_AUTODELETE,
            )
            return

        view = DeleteVacationView(
            bot=self.bot, owner_id=interaction.user.id, vacations=vacations
        )
        await interaction.response.send_message(
            "Welchen Urlaub möchtest du löschen?",
            view=view,
            ephemeral=True,
        )


# ====================================================================== UI


class DeleteVacationSelect(discord.ui.Select):
    def __init__(self, owner_id: int, vacations: list[Vacation]):
        self._owner_id = owner_id
        options: list[discord.SelectOption] = []
        # Discord caps a Select at 25 options. 25 upcoming vacations per user is plenty.
        for v in vacations[:25]:
            options.append(
                discord.SelectOption(
                    label=f"🗓 {format_range(v.start_date, v.end_date)}"[:100],
                    value=str(v.id),
                )
            )
        super().__init__(
            placeholder="Urlaub auswählen…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self._owner_id:
            await interaction.response.send_message(
                "❌ Dieses Menü gehört nicht dir.", ephemeral=True
            )
            return

        try:
            vacation_id = int(self.values[0])
        except (ValueError, IndexError):
            await interaction.response.send_message(
                "❌ Ungültige Auswahl.", ephemeral=True
            )
            return

        # Look up the row first so we can echo the exact range back to the user.
        user_id = str(interaction.user.id)
        upcoming = await db.get_upcoming_vacations_for_user(user_id)
        match = next((v for v in upcoming if v.id == vacation_id), None)

        deleted = await db.delete_vacation(vacation_id, user_id)
        if not deleted:
            await interaction.response.edit_message(
                content="❌ Dieser Urlaub konnte nicht gefunden werden.",
                view=None,
            )
            return

        label = (
            format_range(match.start_date, match.end_date)
            if match
            else f"#{vacation_id}"
        )
        await interaction.response.edit_message(
            content=f"✅ Urlaub vom **{label}** wurde gelöscht.",
            view=None,
        )
        # edit_message has no `delete_after`; schedule the cleanup ourselves.
        asyncio.create_task(_delete_response_later(interaction, EPHEMERAL_AUTODELETE))

        # Refresh pinned heatmap silently after deletion.
        view: DeleteVacationView = self.view  # type: ignore[assignment]
        try:
            await refresh_heatmap(view.bot, db)
        except Exception:
            log.exception("refresh_heatmap failed after /urlaub_loeschen")


class DeleteVacationView(discord.ui.View):
    def __init__(self, *, bot: commands.Bot, owner_id: int, vacations: list[Vacation]):
        super().__init__(timeout=120)
        self.bot = bot
        self.add_item(DeleteVacationSelect(owner_id=owner_id, vacations=vacations))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VacationCog(bot))
