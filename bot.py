"""Discord bot entry point.

Run locally:
    python bot.py

Environment is loaded from a `.env` file in the working directory.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import time

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from db import close_db, db, init_db
from utils.pinned_heatmap import load_pinned_message_id, refresh_heatmap

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("bot")


COGS = ("commands.vacation", "commands.query")


class GuildVacationBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True  # needed to read role memberships
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        await init_db()
        await load_pinned_message_id(db)

        for cog in COGS:
            await self.load_extension(cog)
            log.info("Loaded cog: %s", cog)

        # If GUILD_ID is set, sync slash commands to that guild only.
        # Guild-scoped sync is instant; global sync can take up to an hour.
        guild_id_raw = os.getenv("GUILD_ID", "").strip()
        if guild_id_raw:
            try:
                guild = discord.Object(id=int(guild_id_raw))
            except ValueError:
                log.warning(
                    "GUILD_ID=%r is not a valid integer; falling back to global sync",
                    guild_id_raw,
                )
                await self.tree.sync()
                log.info("Slash commands synced globally (may take up to 1h to appear)")
            else:
                # Mirror global commands into the guild and sync there.
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                log.info("Slash commands synced to guild %s (instant)", guild_id_raw)
        else:
            await self.tree.sync()
            log.info("Slash commands synced globally (may take up to 1h to appear)")

        self.daily_heatmap.start()

    async def close(self) -> None:
        self.daily_heatmap.cancel()
        await super().close()
        await close_db()

    # Runs every day at 00:05 server time
    @tasks.loop(time=time(hour=0, minute=5))
    async def daily_heatmap(self) -> None:
        try:
            await refresh_heatmap(self, db)
            log.info("Daily heatmap refresh complete")
        except Exception:
            log.exception("Daily heatmap refresh failed")

    @daily_heatmap.before_loop
    async def _wait_until_ready(self) -> None:
        await self.wait_until_ready()


bot = GuildVacationBot()


@bot.event
async def on_ready() -> None:
    log.info("✅ Bot online als %s (%s)", bot.user, bot.user.id if bot.user else "?")
    # On first start (or after a deploy) refresh the heatmap right away so the
    # pinned image is current.
    try:
        await refresh_heatmap(bot, db)
    except Exception:
        log.exception("Initial heatmap refresh failed")


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: discord.app_commands.AppCommandError
) -> None:
    # The officer guard already replies; suppress the duplicate error here.
    if isinstance(error, discord.app_commands.CheckFailure):
        return

    log.exception("Unhandled application command error", exc_info=error)
    message = "❌ Da ist etwas schiefgelaufen. Bitte versuche es später noch einmal."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        sys.stderr.write(
            "❌ DISCORD_TOKEN ist nicht gesetzt. Bitte trag ihn in deine .env-Datei ein.\n"
        )
        sys.exit(1)
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
