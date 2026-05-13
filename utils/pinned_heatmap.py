"""Maintain a single pinned heatmap message in the configured channel."""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import discord

from charts.heatmap import DAYS_TO_SHOW, generate_heatmap
from db import Database

log = logging.getLogger(__name__)

_pinned_message_id: int | None = None
_PINNED_MSG_KEY = "heatmap_message_id"
_HEATMAP_HEADER = "📅 **Abwesenheitsübersicht** — wird automatisch aktualisiert"


def _heatmap_channel_id() -> int:
    raw = os.getenv("HEATMAP_CHANNEL_ID", "").strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


async def load_pinned_message_id(db: Database) -> None:
    """Restore the cached message id from the database on bot startup."""
    global _pinned_message_id
    raw = await db.get_config(_PINNED_MSG_KEY)
    if raw:
        try:
            _pinned_message_id = int(raw)
        except ValueError:
            _pinned_message_id = None


async def refresh_heatmap(bot: discord.Client, db: Database) -> None:
    """Regenerate the heatmap and edit (or create) the pinned message."""
    channel_id = _heatmap_channel_id()
    if not channel_id:
        return  # heatmap disabled

    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.DiscordException:
            log.warning("HEATMAP_CHANNEL_ID=%s could not be resolved", channel_id)
            return

    today = date.today()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=DAYS_TO_SHOW - 1)
    counts = await db.get_absence_counts_for_range(start, end)
    buf = generate_heatmap(counts)

    global _pinned_message_id

    async def _ensure_pinned(msg: discord.Message) -> None:
        """Pin the message if it isn't already. Safe to call every refresh."""
        if msg.pinned:
            return
        try:
            await msg.pin(reason="Auto-updating absence heatmap")
            log.info("Pinned heatmap message %s", msg.id)
        except discord.Forbidden:
            log.warning("Bot lacks Manage Messages permission; cannot pin heatmap")
        except discord.HTTPException as exc:
            # e.g. channel already has 50 pinned messages (Discord's limit).
            log.warning("Could not pin heatmap (%s)", exc)

    async def _post_new() -> discord.Message:
        global _pinned_message_id
        buf.seek(0)
        msg = await channel.send(
            content=_HEATMAP_HEADER,
            file=discord.File(buf, "heatmap.png"),
        )
        _pinned_message_id = msg.id
        await db.set_config(_PINNED_MSG_KEY, str(msg.id))
        await _ensure_pinned(msg)
        return msg

    if _pinned_message_id is not None:
        try:
            msg = await channel.fetch_message(_pinned_message_id)
        except (discord.NotFound, discord.Forbidden):
            await _post_new()
            return
        try:
            buf.seek(0)
            msg = await msg.edit(
                content=_HEATMAP_HEADER,
                attachments=[discord.File(buf, "heatmap.png")],
            )
        except discord.HTTPException as exc:
            log.warning("Failed to edit pinned heatmap (%s); posting new one", exc)
            await _post_new()
            return
        await _ensure_pinned(msg)
    else:
        await _post_new()
