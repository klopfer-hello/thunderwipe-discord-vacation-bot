"""Moderation role guard for slash commands."""

from __future__ import annotations

import os

import discord
from discord import app_commands


def moderation_roles() -> set[str]:
    """The set of role names that gate moderator commands.

    Configured via the ``MODERATION_ROLES`` environment variable — a
    comma-separated list of Discord role names. An empty value (or missing
    variable) means the commands are open to everyone.
    """
    raw = os.getenv("MODERATION_ROLES", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def member_is_moderator(user: discord.abc.User) -> bool:
    """True if the user carries any configured moderator role, or no role is configured."""
    required = moderation_roles()
    if not required:
        return True
    role_names = {r.name for r in getattr(user, "roles", [])}
    return bool(role_names & required)


def _format_required_roles(roles: set[str]) -> str:
    ordered = sorted(roles)
    if len(ordered) == 1:
        return f"die Rolle „{ordered[0]}“"
    quoted = ", ".join(f"„{r}“" for r in ordered)
    return f"eine der folgenden Rollen: {quoted}"


def is_moderator():
    """Decorator: gate a command behind any of the configured moderator roles.

    Behaviour:
        * ``MODERATION_ROLES`` empty/unset -> the command is open to everyone.
        * ``MODERATION_ROLES`` set -> the invoking member must carry at least
          one of the listed roles; others get a friendly German rejection.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if member_is_moderator(interaction.user):
            return True

        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"❌ Du brauchst {_format_required_roles(moderation_roles())} für diesen Befehl.",
                ephemeral=True,
            )
        return False

    return app_commands.check(predicate)
