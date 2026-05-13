"""Officer role guard for slash commands."""

from __future__ import annotations

import os

import discord
from discord import app_commands


def officer_role_name() -> str:
    """The name of the role that gates officer commands, or empty string for open access."""
    return os.getenv("OFFICER_ROLE_NAME", "").strip()


def is_officer():
    """Decorator: gate a command behind the officer role.

    Behaviour:
        * ``OFFICER_ROLE_NAME`` empty/unset -> the command is open to everyone.
        * ``OFFICER_ROLE_NAME`` set -> only members carrying that exact role
          name may invoke the command; others get a friendly German rejection.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        role = officer_role_name()
        if not role:
            return True  # open access — no officer role configured

        member = interaction.user
        role_names = {r.name for r in getattr(member, "roles", [])}
        if role in role_names:
            return True

        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"❌ Du brauchst die Rolle „{role}“ für diesen Befehl.",
                ephemeral=True,
            )
        return False

    return app_commands.check(predicate)
