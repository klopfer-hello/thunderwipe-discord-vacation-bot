# CLAUDE.md — WoW Guild Vacation Bot

This file gives Claude Code full context about this project so you can continue development
without re-explaining decisions made in the initial planning session.

---

## Project Overview

A Discord bot for a World of Warcraft guild (~100 members) to manage player vacations/absences.
Members submit their vacation dates via a slash command; officers can query absences and view
visualizations to plan raids around missing members.

**Primary language:** Python  
**Bot framework:** discord.py  
**Database:** PostgreSQL (cloud-ready) with SQLite fallback for local dev  
**Hosting target:** Self-hosted server (Docker + Docker Compose, PostgreSQL in a container)  
**Visualization:** matplotlib for chart images posted directly into Discord  

---

## Project Structure

```
wow-guild-bot/
├── CLAUDE.md                  # this file
├── README.md
├── Dockerfile                 # builds the bot image
├── docker-compose.yml         # bot + postgres services
├── .env                       # secrets — never commit
├── .env.example               # committed template
├── .gitignore
├── requirements.txt
├── bot.py                     # entry point, bot setup, event handlers, daily task loop
├── db.py                      # all database access (init, queries, migrations)
├── commands/
│   ├── __init__.py
│   ├── vacation.py            # /urlaub, /urlaub löschen (with Select UI)
│   └── query.py               # /fehlende, /urlaube_anzeigen
├── charts/
│   ├── __init__.py
│   └── heatmap.py             # absence heatmap generator (returns BytesIO PNG)
└── utils/
    ├── __init__.py
    ├── date_parser.py         # parse DD.MM.YYYY, validate ranges
    ├── permissions.py         # role checks, officer guard
    └── pinned_heatmap.py      # refresh_heatmap() — edits the pinned message
```

---

## Commands

Only two member-facing slash commands exist. Keep the surface area small and simple.

### Member commands (usable by everyone)

| Command | Parameters | Description |
|---|---|---|
| `/urlaub` | `start: str`, `end: str` | Register a vacation. Both dates in DD.MM.YYYY format. Reply is ephemeral (only visible to the user). |
| `/urlaub löschen` | — | Opens an interactive ephemeral menu listing the user's own upcoming vacations. User picks which one to delete via a Discord Select Menu (dropdown). No ID needed. |

**`/urlaub löschen` UX flow:**

1. User types `/urlaub löschen`
2. Bot responds ephemerally with a `discord.ui.Select` dropdown listing their upcoming entries,
   e.g. `"🗓 20.05.2026 – 25.05.2026"`, `"🗓 10.07.2026 – 14.07.2026"`
3. If the user has no upcoming vacations, bot replies: `"Du hast keine eingetragenen Urlaube."`
4. User selects one entry from the dropdown
5. Bot deletes it and confirms: `"✅ Urlaub vom 20.05. – 25.05.2026 wurde gelöscht."`

This is implemented with `discord.ui.View` + `discord.ui.Select`. The select options carry
the vacation `id` as their `value` so no ID ever needs to be typed by the user.

### Moderator commands (require any role listed in `MODERATION_ROLES`)

| Command | Parameters | Description |
|---|---|---|
| `/fehlende` | `datum: str` | Lists all members absent on a given date. |
| `/urlaube_anzeigen` | `tage: int = 30` | Lists all vacations in the next N days. |

The heatmap is **not** triggered by a command — it is maintained automatically as a pinned
message. See the **Pinned Heatmap** section below.

---

## Database Schema

```sql
CREATE TABLE vacations (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT        NOT NULL,
    username    TEXT        NOT NULL,
    start_date  DATE        NOT NULL,
    end_date    DATE        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for the most common query pattern: date range lookups
CREATE INDEX idx_vacations_dates ON vacations (start_date, end_date);

-- Prevent duplicate entries for the same user overlapping same period
-- (enforced in application logic, not DB constraint, to give friendly error messages)
```

For **local development**, the bot falls back to SQLite automatically when `DATABASE_URL` is
not set. The `db.py` module abstracts this so the rest of the code doesn't care.

---

## Environment Variables

Store in `.env` locally and on the server. Never commit this file.

```env
# Required
DISCORD_TOKEN=your_bot_token_here

# Database password — used by docker-compose.yml to configure both the db container
# and the DATABASE_URL passed to the bot container
DB_PASSWORD=choose_a_strong_password

# When running via Docker Compose, DATABASE_URL is set automatically by the compose file.
# Leave blank here — only fill this in if running the bot outside Docker.
DATABASE_URL=

# Optional tuning
MODERATION_ROLES=Officer           # Comma-separated role names that gate moderator commands
HEATMAP_CHANNEL_ID=                # Channel ID where the pinned heatmap lives
VACATION_CHANNEL_ID=               # If set, bot only accepts /urlaub in this channel
```

`.env.example` (commit this):
```env
DISCORD_TOKEN=
DB_PASSWORD=
DATABASE_URL=
MODERATION_ROLES=Officer
HEATMAP_CHANNEL_ID=
VACATION_CHANNEL_ID=
```

---

## Key Implementation Decisions

### Why slash commands and not prefix commands (e.g. `!urlaub`)?

Slash commands (`/urlaub`) are invisible in the channel — Discord only shows the response,
and with `ephemeral=True` even that is private. Prefix commands would show the full message
text in the channel. The user explicitly wanted vacation entries not visible to everyone.

### Why ephemeral responses?

The channel stays clean. Only the person registering a vacation sees the confirmation.
Officers' query results are also ephemeral by default (no clutter in shared channels).

### Date format: DD.MM.YYYY

The guild is German-speaking (command name is German: "Urlaub" = vacation). The date format
matches German convention. The `date_parser.py` utility handles parsing and should give
friendly German error messages.

### PostgreSQL on Railway, SQLite locally

Cloud platforms with ephemeral filesystems (Railway, Render free tier) will lose SQLite data
on every restart. PostgreSQL hosted on Railway is the correct solution. Locally, SQLite is
fine and requires no setup. `db.py` detects `DATABASE_URL` and switches accordingly.

### Chart output: matplotlib images posted as Discord files

Rather than an external dashboard, charts are generated as PNG images by matplotlib and
posted directly into Discord via `discord.File`. This requires no extra hosting. Officers
run a command, bot posts the image. Simple, no browser needed.

---

## Code Patterns to Follow

### Slash command skeleton

```python
# commands/vacation.py
import discord
from discord import app_commands
from discord.ext import commands

class VacationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="urlaub", description="Trag deinen Urlaub ein")
    @app_commands.describe(
        start="Startdatum (TT.MM.JJJJ)",
        end="Enddatum (TT.MM.JJJJ)"
    )
    async def urlaub(self, interaction: discord.Interaction, start: str, end: str):
        # 1. Parse and validate dates via utils/date_parser.py
        # 2. Insert into DB via db.py
        # 3. Respond ephemeral
        await interaction.response.send_message("...", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(VacationCog(bot))
```

### Moderator-only guard

`MODERATION_ROLES` is a comma-separated list of role names. A member only
needs to carry **one** of them to invoke the gated command. An empty value
means the commands are open to everyone.

```python
# utils/permissions.py
import os
import discord
from discord import app_commands

def moderation_roles() -> set[str]:
    raw = os.getenv("MODERATION_ROLES", "")
    return {part.strip() for part in raw.split(",") if part.strip()}

def is_moderator():
    """app_commands check — use as decorator on moderator commands."""
    async def predicate(interaction: discord.Interaction) -> bool:
        required = moderation_roles()
        if not required:
            return True  # open access
        member_roles = {r.name for r in interaction.user.roles}
        if member_roles & required:
            return True
        await interaction.response.send_message(
            "❌ Du brauchst eine der konfigurierten Rollen für diesen Befehl.",
            ephemeral=True,
        )
        return False
    return app_commands.check(predicate)
```

Usage:
```python
from utils.permissions import is_moderator

@app_commands.command(name="fehlende")
@is_moderator()
async def fehlende(self, interaction, datum: str):
    ...
```

### Posting a chart as a Discord image

```python
import io
import discord
import matplotlib.pyplot as plt

async def send_chart(interaction: discord.Interaction, fig: plt.Figure, filename: str):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    await interaction.followup.send(file=discord.File(buf, filename=filename))
```

Always call `await interaction.response.defer()` before generating a chart, since it takes
more than 3 seconds and Discord will time out the interaction otherwise:

```python
async def heatmap(self, interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)   # shows "Bot is thinking..."
    fig = generate_heatmap(...)
    await send_chart(interaction, fig, "heatmap.png")
```

---

## Pinned Heatmap (auto-updating)

The heatmap is the primary visualization. It lives as a **single pinned message** in a
designated channel (e.g. `#abwesenheiten`). The bot keeps it up to date automatically —
no officer needs to run a command.

### What it shows

- **Current week + next 2 weeks** (21 days total), always rolling forward
- One column per day, labeled with weekday + date (e.g. `Mo\n12.05`)
- One row — just color intensity showing how many members are absent that day
- Color scale: white (0) → light amber → deep red (many absent)
- The count is printed inside each cell (e.g. `3`)
- Weekend columns (Sa, So) are visually dimmed (lighter background) since raids rarely happen

### Update triggers

The pinned message is regenerated and edited (not reposted) in two situations:

1. **Any `/urlaub` or `/urlaub löschen`** — immediately after the DB write succeeds,
   the heatmap is regenerated and the pinned message is edited silently in the background.
2. **Daily at midnight** via `discord.ext.tasks` — catches any edge cases (e.g. today rolled
   forward, so yesterday drops off the window).

### Implementation notes

```python
# charts/heatmap.py

from datetime import date, timedelta
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import io

DAYS_TO_SHOW = 21   # current week + 2 more weeks

def generate_heatmap(absence_counts: dict[date, int], max_members: int = 100) -> io.BytesIO:
    """
    absence_counts: {date: count_of_absent_members}
    Returns a PNG BytesIO ready to send as a discord.File.
    """
    today = date.today()
    # Start from Monday of the current week
    start = today - timedelta(days=today.weekday())
    dates = [start + timedelta(days=i) for i in range(DAYS_TO_SHOW)]

    counts = np.array([absence_counts.get(d, 0) for d in dates], dtype=float)

    fig, ax = plt.subplots(figsize=(14, 2.5))
    # ... pcolormesh / imshow rendering ...
    # Weekend columns: add a subtle gray overlay rect over Sa/So columns
    # Cell text: ax.text() centered in each cell with the count

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return buf
```

```python
# utils/pinned_heatmap.py

import os
import discord

HEATMAP_CHANNEL_ID = int(os.getenv("HEATMAP_CHANNEL_ID", "0"))
_pinned_message_id: int | None = None   # cached in memory; also store in DB for restarts

async def refresh_heatmap(bot: discord.Client, db) -> None:
    """Regenerate the heatmap image and edit the pinned message."""
    channel = bot.get_channel(HEATMAP_CHANNEL_ID)
    if not channel:
        return

    absence_counts = await db.get_absence_counts_for_range(...)
    buf = generate_heatmap(absence_counts)

    global _pinned_message_id
    try:
        if _pinned_message_id:
            msg = await channel.fetch_message(_pinned_message_id)
            await msg.edit(attachments=[discord.File(buf, "heatmap.png")])
        else:
            raise discord.NotFound(None, None)
    except discord.NotFound:
        # First run or message was deleted — post a new one and pin it
        msg = await channel.send(
            content="📅 **Abwesenheitsübersicht** — wird automatisch aktualisiert",
            file=discord.File(buf, "heatmap.png")
        )
        await msg.pin()
        _pinned_message_id = msg.id
        await db.set_config("heatmap_message_id", str(msg.id))
```

### DB additions for pinned heatmap

```sql
-- Simple key-value store for bot config (heatmap message ID, etc.)
CREATE TABLE bot_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

On startup, `bot.py` reads `heatmap_message_id` from `bot_config` so `_pinned_message_id`
survives bot restarts.

### New environment variable

```env
HEATMAP_CHANNEL_ID=   # Discord channel ID where the pinned heatmap lives
```

---

## Visualization Plan

### Absence heatmap (pinned, auto-updating)

See **Pinned Heatmap** section above. This is the only visualization.

---

## Bot Entry Point

```python
# bot.py
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from db import init_db

load_dotenv()

intents = discord.Intents.default()
intents.members = True  # needed to resolve role memberships

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await init_db()
    # Load cogs
    for cog in ["commands.vacation", "commands.query", "commands.charts"]:
        await bot.load_extension(cog)
    await bot.tree.sync()
    print(f"✅ Bot online als {bot.user} ({bot.user.id})")

bot.run(os.getenv("DISCORD_TOKEN"))
```

---

## requirements.txt

```
discord.py>=2.3.0
python-dotenv>=1.0.0
matplotlib>=3.8.0
asyncpg>=0.29.0      # PostgreSQL async driver
aiosqlite>=0.20.0    # SQLite async driver for local dev
Pillow>=10.0.0       # matplotlib PNG output dependency
```

---

## Server Setup & Deployment (Docker Compose)

The bot and its PostgreSQL database each run in their own Docker container, managed together
by Docker Compose. Compose handles networking between them, restarts on crash, and starts
everything automatically when the server boots.

---

### New files required in the repo

#### `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

CMD ["python", "bot.py"]
```

#### `docker-compose.yml`

```yaml
services:

  db:
    image: postgres:16-alpine
    container_name: guildbot-db
    restart: unless-stopped
    environment:
      POSTGRES_USER: guildbot
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: guildvacations
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U guildbot -d guildvacations"]
      interval: 10s
      timeout: 5s
      retries: 5

  bot:
    build: .
    container_name: guildbot
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    env_file:
      - .env
    environment:
      # Overrides whatever DATABASE_URL is in .env — always points to the db container
      DATABASE_URL: postgresql://guildbot:${DB_PASSWORD}@db:5432/guildvacations

volumes:
  postgres_data:   # named volume — data persists across container restarts and rebuilds
```

#### Updated `.env.example`

```env
DISCORD_TOKEN=
DB_PASSWORD=choose_a_strong_password

# Docker Compose sets DATABASE_URL automatically — leave blank here
DATABASE_URL=

MODERATION_ROLES=Officer
HEATMAP_CHANNEL_ID=
VACATION_CHANNEL_ID=
```

> **Note:** `DATABASE_URL` is intentionally left empty in `.env` for local dev (SQLite
> fallback). Docker Compose overrides it via the `environment:` block so the bot always
> reaches the `db` container when running in Docker.

---

### 1. Install Docker on the server (Ubuntu/Debian)

```bash
# Update and install prerequisites
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl gnupg

# Add Docker's official GPG key and repo
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine + Compose plugin
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Allow your user to run Docker without sudo (log out and back in after this)
sudo usermod -aG docker $USER

# Enable Docker to start on boot
sudo systemctl enable docker
```

Verify the install:
```bash
docker --version
docker compose version
```

---

### 2. Clone the repo onto the server

```bash
git clone https://github.com/yourusername/wow-guild-bot.git
cd wow-guild-bot
```

---

### 3. Create the `.env` file

```bash
cp .env.example .env
nano .env
```

Fill in at minimum:
- `DISCORD_TOKEN` — from the Discord Developer Portal
- `DB_PASSWORD` — choose something strong, e.g. `openssl rand -base64 24`
- `HEATMAP_CHANNEL_ID` — the Discord channel ID for the pinned heatmap
- `MODERATION_ROLES` — comma-separated names of the Discord roles that may use moderator commands

---

### 4. Build and start everything

```bash
# Build the bot image and start both containers in the background
docker compose up -d --build

# Watch the logs to confirm the bot comes online
docker compose logs -f bot
```

You should see `✅ Bot online als ...` in the logs. Done.

---

### Updating after code changes

```bash
git pull
docker compose up -d --build   # rebuilds the bot image, restarts only changed containers
```

The `db` container is not rebuilt (it uses a pre-built image) so your data is safe.

---

### Useful maintenance commands

```bash
docker compose ps                     # are both containers running?
docker compose logs -f bot            # live bot logs
docker compose logs -f db             # live postgres logs
docker compose logs --tail 100 bot    # last 100 bot log lines
docker compose restart bot            # restart just the bot (e.g. after config change)
docker compose stop                   # stop everything
docker compose down                   # stop and remove containers (data volume kept)
docker compose down -v                # ⚠️ stop and DELETE all data (volume removed)
```

### Connecting to the database directly

```bash
# Open a psql shell inside the running db container
docker compose exec db psql -U guildbot -d guildvacations
```

---

### How `restart: unless-stopped` works

Both services have `restart: unless-stopped`. This means:
- If the bot crashes, Docker restarts it automatically within a few seconds
- If the server reboots, Docker starts both containers automatically on boot
- The only time they stay stopped is if you explicitly run `docker compose stop`

No systemd unit file needed — Docker handles it.

---

## Discord Developer Portal Setup

1. Go to https://discord.com/developers/applications
2. Create a new application → Bot tab → Add Bot
3. Copy the token → `DISCORD_TOKEN` in `.env`
4. Under "Privileged Gateway Intents" enable:
   - **Server Members Intent** (required to read member roles)
5. OAuth2 → URL Generator:
   - Scopes: `bot`, `applications.commands`
   - Bot permissions: `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History`, `Manage Messages` (needed to pin the heatmap message)
6. Use the generated URL to invite the bot to your guild

---

## Local Development Quickstart

```bash
# Clone repo
git clone <your-repo-url>
cd wow-guild-bot

# Create virtualenv
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env and add your DISCORD_TOKEN
# Leave DATABASE_URL empty → bot will use local SQLite (vacations.db)

# Run
python bot.py
```

The bot will create `vacations.db` automatically on first run when running locally.

---

## What Is Not Built Yet

The following features were discussed but not implemented in the initial session:

- [ ] `Dockerfile` — build the bot image
- [ ] `docker-compose.yml` — bot + postgres services
- [ ] `/urlaub` — register a vacation (core command)
- [ ] `/urlaub löschen` — interactive Select Menu to delete own entry
- [ ] Pinned heatmap — auto-updating message in `HEATMAP_CHANNEL_ID`
- [ ] `refresh_heatmap()` called after every DB write and daily at midnight
- [ ] `bot_config` table to persist the pinned message ID across restarts
- [ ] `/fehlende` — officer command: who is absent on a given date
- [ ] `/urlaube_anzeigen` — officer command: list vacations in next N days
- [ ] Overlap detection — warn user if new vacation overlaps an existing own entry
- [ ] `VACATION_CHANNEL_ID` enforcement — restrict `/urlaub` to a specific channel
- [ ] Paginated output for `/urlaube_anzeigen` when many results
- [ ] Localization — standardize all messages to German

---

## Conversation Context

This project was planned in a Claude.ai chat session. Key decisions made:

- **Slash commands chosen over prefix commands** to keep the vacation channel clean
- **Ephemeral responses** so vacation entries are private
- **Date format DD.MM.YYYY** to match German convention (guild is German-speaking)
- **Heatmap recommended** over full calendar for 100-member guilds (calendar is too dense)
- **Self-hosted server with Docker Compose chosen for hosting** — bot and PostgreSQL each run
  in their own container; `restart: unless-stopped` handles crash recovery and boot startup;
  named volume persists DB data across rebuilds; no cloud dependency
- **matplotlib charts posted as Discord images** — no external web dashboard needed
- **Only two member commands**: `/urlaub` and `/urlaub löschen` — kept deliberately minimal
- **`/urlaub löschen` uses a Select Menu** (dropdown) so users never have to type or know an ID
- **Heatmap is a pinned message, not a command** — it updates automatically on every DB write
  and via a daily midnight task; officers don't need to trigger it manually
- **Heatmap window: current week + next 2 weeks** (21 days, always rolling)
- **Single pinned message is edited in-place** (not reposted) to avoid channel spam; the
  message ID is persisted in a `bot_config` table so it survives bot restarts
- **Discord bot permissions needed**: `Send Messages`, `Embed Links`, `Attach Files`,
  `Read Message History`, `Manage Messages` (for pinning)

---

## Coding Style

- Python 3.11+
- Type hints on all function signatures
- Async throughout (discord.py is async, db access should be too via asyncpg/aiosqlite)
- Error handling: catch expected errors (bad date format, no entries found) and respond
  with friendly German messages. Let unexpected errors propagate to a global error handler
  in `bot.py` that logs and responds with a generic "something went wrong" message.
- Keep command handlers thin — business logic in `db.py` and `utils/`, not in the command itself
- No hardcoded strings for error messages — collect them at the top of each file or in a
  `messages.py` constants file
