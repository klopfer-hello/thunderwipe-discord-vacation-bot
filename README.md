# WoW Guild Vacation Bot

Discord bot for a German-speaking WoW guild (~100 members) to track member vacations
and visualize them as an auto-updating heatmap pinned in a channel.

See [`CLAUDE.md`](CLAUDE.md) for the full design spec.

## Contents

- [Commands](#commands)
- [Discord setup (step by step)](#discord-setup-step-by-step)
  - [1. Create the application & bot user](#1-create-the-application--bot-user)
  - [2. Enable the required intent](#2-enable-the-required-intent)
  - [3. Generate the invite URL](#3-generate-the-invite-url)
  - [4. Find your IDs](#4-find-your-ids-server-channel-role)
  - [5. (Optional) Officer role](#5-optional-officer-role)
  - [6. Channel-level permissions](#6-channel-level-permissions-for-the-heatmap-channel)
- [Environment variables](#environment-variables)
- [Local development quickstart](#local-development-quickstart)
- [Running with Docker Compose](#running-with-docker-compose)
- [Contributing](#contributing)
- [Releasing](#releasing)
- [Troubleshooting](#troubleshooting)
- [File layout](#file-layout)

---

## Commands

**Member commands**

| Command | Parameters | Description |
|---|---|---|
| `/urlaub` | `start`, `end` (DD.MM.JJJJ) | Register a vacation. Reply is private (ephemeral). |
| `/urlaub_loeschen` | — | Pick one of your own vacations from a dropdown and delete it. |

**Officer commands** (require the role named in `OFFICER_ROLE_NAME`; open to everyone if that variable is empty)

| Command | Parameters | Description |
|---|---|---|
| `/fehlende` | `datum` (DD.MM.JJJJ) | List all members absent on a given date. |
| `/urlaube_anzeigen` | `tage` (default 30) | List all vacations in the next N days. |

> Discord doesn't allow spaces in slash command names, so `/urlaub löschen`
> from the design spec is implemented as `/urlaub_loeschen`.

The absence **heatmap** is not a command — it lives as a single pinned message in
the channel set via `HEATMAP_CHANNEL_ID` and updates automatically whenever
someone adds or removes a vacation (and once per day at 00:05 local time).

---

## Discord setup (step by step)

You only do this once per Discord server.

### 1. Create the application & bot user

1. Open https://discord.com/developers/applications and sign in.
2. Click **New Application** (top right). Give it a name your guild members will
   see (e.g. `Urlaubsbot`). Tick the developer terms and click **Create**.
3. (Optional) On the **General Information** tab upload an avatar and a
   description — these are what members see in Discord.
4. In the left sidebar open **Bot**.
5. Press **Reset Token** → **Yes, do it!** → **Copy**. **Paste this into your
   `.env`** as the value of `DISCORD_TOKEN`. *(Discord shows the token exactly
   once; if you lose it, hit Reset Token again — that invalidates the old one.)*
6. While you are on the Bot tab, give the bot a friendly username if you want.

> **Never share the token or commit it to git.** Treat it like a password.

### 2. Enable the required intent

Still on the **Bot** tab, scroll down to **Privileged Gateway Intents** and tick:

- ✅ **SERVER MEMBERS INTENT** — required to read role memberships for the
  officer check.

You can leave Message Content Intent and Presence Intent **off** — this bot
uses slash commands only and never reads message text.

Click **Save Changes** at the bottom.

### 3. Generate the invite URL

In the left sidebar open **OAuth2 → URL Generator**.

- **Scopes** (tick both):
  - ✅ `bot`
  - ✅ `applications.commands`

- **Bot Permissions** (tick exactly these):
  - ✅ `Send Messages` — to post the heatmap and command replies
  - ✅ `Embed Links` — for tidy formatting in responses
  - ✅ `Attach Files` — to upload the heatmap PNG
  - ✅ `Read Message History` — to find the pinned heatmap message on restart
  - ✅ `Manage Messages` — required for pinning the heatmap message

Copy the **Generated URL** at the bottom of the page, open it in your browser,
pick your server in the dropdown, and click **Authorize**.

> The bot does **not** need `Administrator` and you should not grant it.
> The five permissions above are the complete set.

After authorizing, Discord creates an auto-managed integration role for the
bot (named after the bot). That role carries the permissions you just ticked.

### 4. Find your IDs (server, channel, role)

Discord IDs are 18–19 digit numbers. To copy them you first need to enable
Developer Mode:

1. In Discord: **User Settings** → **Advanced** → toggle **Developer Mode**
   on.

Then:

- **Server ID** — right-click your server's name in the left sidebar →
  **Copy Server ID**. Paste into `.env` as `GUILD_ID`. *(Setting this makes
  slash commands appear instantly when you start the bot. Leaving it empty
  falls back to global registration, which can take up to an hour.)*
- **Heatmap channel ID** — right-click the channel where the heatmap should
  live (e.g. `#urlaub` or `#abwesenheiten`) → **Copy Channel ID**. Paste into
  `.env` as `HEATMAP_CHANNEL_ID`.
- **Vacation channel ID (optional)** — if you want `/urlaub` to be usable
  only inside one channel, copy that channel's ID into `VACATION_CHANNEL_ID`.

### 5. (Optional) Officer role

If you want to restrict `/fehlende` and `/urlaube_anzeigen` to a subset of
members:

1. In Discord: **Server Settings → Roles → Create Role**. Name it whatever
   you like, e.g. `Officer` or `Raidlead`. The exact name matters — it's
   what you put in `.env`.
2. Assign that role to the relevant guild members.
3. In `.env` set `OFFICER_ROLE_NAME=Officer` (or whatever you named it).

If you leave `OFFICER_ROLE_NAME` empty, everyone on the server can use the
officer commands. That is the bot's default behaviour.

### 6. Channel-level permissions for the heatmap channel

Even after a clean invite with `Manage Messages` ticked, individual channels
can override role permissions. If the heatmap channel has tight overrides
(common for read-only announcement channels), the bot may not be able to pin.

If that happens — you'll see this in the bot logs:

```
WARNING utils.pinned_heatmap: Bot lacks Manage Messages permission; cannot pin heatmap
```

Fix:

1. Right-click the heatmap channel → **Edit Channel** → **Permissions**.
2. Under **Roles/Members** click the **+** and add the bot (or its
   auto-managed role).
3. Enable **Manage Messages** for it.
4. **Save Changes**.

Then either delete the existing unpinned heatmap message (the bot will
re-post and pin it), or just leave it — the bot will pin it the next time
the heatmap refreshes (i.e. on the next `/urlaub` action or at midnight).

---

## Environment variables

All values live in a `.env` file at the project root. Copy `.env.example` to
`.env` and edit. `.env` is in `.gitignore` — never commit it.

| Variable | Required | Purpose |
|---|---|---|
| `DISCORD_TOKEN` | **yes** | Bot token from the developer portal (step 1). |
| `GUILD_ID` | recommended | Discord server ID (step 4). With it, slash commands appear **instantly** on that server. Without it, they sync globally and may take up to an hour. |
| `HEATMAP_CHANNEL_ID` | recommended | Channel for the pinned heatmap (step 4). If unset, the heatmap is disabled. |
| `OFFICER_ROLE_NAME` | — | Role name for officer commands (step 5). **Empty/unset = open to everyone.** |
| `VACATION_CHANNEL_ID` | — | If set, `/urlaub` is only allowed in that channel. |
| `DB_PASSWORD` | docker only | PostgreSQL password used by `docker-compose.yml`. Ignored when running locally. |
| `DATABASE_URL` | — | If set, the bot uses PostgreSQL via this URL. If unset, falls back to local SQLite (`vacations.db`). Compose sets this automatically — leave it empty in `.env`. |

---

## Local development quickstart

**Windows / PowerShell**

```powershell
# 1. Virtualenv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Dependencies
pip install -r requirements.txt

# 3. Configure
Copy-Item .env.example .env
# edit .env: at minimum DISCORD_TOKEN, GUILD_ID, HEATMAP_CHANNEL_ID

# 4. Run
python bot.py
```

**macOS / Linux**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env
python bot.py
```

On the first start, the bot creates `vacations.db` in the project directory
automatically (local SQLite — no setup required).

You should see logs ending in:

```
INFO bot: Slash commands synced to guild ... (instant)
INFO bot: ✅ Bot online als <your bot>
```

Type `/` in any Discord channel — the four commands should now show up under
your bot's name.

---

## Running with Docker Compose

Both the bot and a PostgreSQL database run in their own containers, managed
together by Docker Compose. PostgreSQL data persists in a named volume across
restarts and rebuilds. Both services use `restart: unless-stopped`, so they
come back up automatically after a crash or server reboot.

### One-time setup

1. Make sure your `.env` is filled in:
   - `DISCORD_TOKEN` — bot token
   - `DB_PASSWORD` — pick a strong value (`openssl rand -base64 24` or similar)
   - `GUILD_ID` — your server ID (recommended; instant slash sync)
   - `HEATMAP_CHANNEL_ID` — the channel that holds the pinned heatmap
   - `OFFICER_ROLE_NAME` — role name, or leave empty for open access

   > When running under Docker Compose, `DATABASE_URL` is set automatically
   > by the compose file to point at the `db` container. Leave that variable
   > empty in your `.env`.

2. Make sure no local instance of the bot is running. One token can only
   be connected to Discord once at a time.

### Build and start

```bash
docker compose up -d --build
docker compose logs -f bot       # watch until "✅ Bot online als ..."
```

### Useful commands

```bash
docker compose ps                  # which containers are up
docker compose logs -f bot         # follow bot logs
docker compose logs -f db          # follow Postgres logs
docker compose restart bot         # bounce just the bot
docker compose stop                # stop everything
docker compose down                # stop + remove containers (data volume kept)
docker compose down -v             # ⚠ also delete the database volume
```

### Updating after code changes

```bash
git pull
docker compose up -d --build       # rebuild bot image, leave db untouched
```

### Inspecting the database

```bash
docker compose exec db psql -U guildbot -d guildvacations
# e.g.   SELECT * FROM vacations;
```

> The local `vacations.db` SQLite file is **not** used in Docker — the bot
> connects to PostgreSQL instead, and `.dockerignore` keeps the SQLite file
> out of the image.

---

## Contributing

### Commit messages — Conventional Commits

All commit messages on this repo must follow the
[Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<optional scope>): <short summary>
```

Allowed types: `feat`, `fix`, `refactor`, `docs`, `chore`, `style`, `test`.

Examples:

```
feat(heatmap): add auto-disappear for ephemeral confirmations
fix(permissions): treat empty OFFICER_ROLE_NAME as open access
docs: explain channel-level permission overrides
chore: release v0.2.0
```

The `release.yml` workflow groups commit messages by type when it generates
the changelog for a release, so sticking to these prefixes keeps release
notes useful.

### Pre-commit hooks

This project ships with a `.pre-commit-config.yaml` that runs:

- Whitespace, end-of-file, YAML, TOML, and merge-conflict checks
- **ruff** (lint, with `--fix`) and **ruff-format** (formatting)
- **conventional-pre-commit** (validates your commit message)

Install once:

```bash
pip install pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type commit-msg
```

After that, `git commit` automatically runs the hooks on staged files
and validates the commit message. To run them manually on the whole tree:

```bash
pre-commit run --all-files
```

The same hooks run in CI via [`.github/workflows/lint.yml`](.github/workflows/lint.yml)
on every push to `main` and every pull request.

### Lint & format manually

If you don't want pre-commit, you can run the same tools directly:

```bash
pip install ruff
ruff check .         # lint
ruff check --fix .   # lint + auto-fix
ruff format .        # format
```

---

## Releasing

Releases are cut by **pushing a tag** that starts with `v`. The
[`release.yml`](.github/workflows/release.yml) workflow then:

1. Builds the Docker image and pushes it to **GitHub Container Registry**
   (`ghcr.io/<owner>/<repo>`) tagged both `latest` and `v<version>`.
2. Generates a changelog by grouping commits since the previous tag into
   *New Features* / *Bug Fixes* / *Improvements* / *Documentation*
   sections (using the Conventional Commit prefixes).
3. Creates a GitHub Release with that changelog attached.

To cut a new release:

```bash
# 1. Make sure main is clean and pushed
git switch main && git pull

# 2. Bump the version in pyproject.toml (e.g. 0.1.0 -> 0.2.0)
# 3. Commit it
git commit -am "chore: release v0.2.0"

# 4. Tag and push
git tag v0.2.0
git push origin main --tags
```

Deployed instances can then pull the new image with:

```bash
docker compose pull && docker compose up -d
```

---

## Troubleshooting

**`PrivilegedIntentsRequired` on startup.** You forgot step 2 above. Go to
the Developer Portal → Bot → enable **Server Members Intent** → Save Changes.

**Slash commands don't appear when I type `/`.**
1. Confirm `GUILD_ID` is set in `.env` and matches the server you invited the
   bot to. Restart the bot — you should see `Slash commands synced to guild
   ... (instant)` in the logs.
2. Restart the Discord client (Ctrl+R) — its command picker caches.
3. If you only set commands globally (no `GUILD_ID`), Discord may take up to
   an hour to roll them out.

**Bot logs say `Bot lacks Manage Messages permission; cannot pin heatmap`.**
The heatmap is posted but not pinned. See step 6 — usually the heatmap
channel has a permission override that needs the bot's role added with
**Manage Messages** enabled.

**Heatmap doesn't show up at all.** Check that `HEATMAP_CHANNEL_ID` is the
correct channel ID and that the bot can see (i.e. has `View Channel` in)
that channel. Without that, the bot can't post anything.

**`/urlaub` fails with "Du brauchst die Rolle …".** The user lacks the role
named in `OFFICER_ROLE_NAME`. Either give them the role, or unset
`OFFICER_ROLE_NAME` to open the commands to everyone, then restart the bot.

**Two bots online at once / `Session start limit exceeded`.** You probably
have a local `python bot.py` running and started Docker (or vice versa).
Stop one of them — Discord only allows one gateway connection per token.

---

## File layout

```
thunderwipe-discord-vacation-bot/
├── bot.py                     # entry point + daily heatmap task
├── db.py                      # PostgreSQL + SQLite abstraction
├── commands/
│   ├── vacation.py            # /urlaub, /urlaub_loeschen
│   └── query.py               # /fehlende, /urlaube_anzeigen
├── charts/
│   └── heatmap.py             # absence heatmap image generator
├── utils/
│   ├── date_parser.py         # DD.MM.JJJJ parser + validation
│   ├── permissions.py         # officer role check decorator
│   └── pinned_heatmap.py      # refresh & edit the pinned heatmap message
├── requirements.txt
├── pyproject.toml             # project metadata + ruff config
├── .pre-commit-config.yaml    # lint & commit-message hooks
├── .github/workflows/
│   ├── lint.yml               # pre-commit on push/PR
│   └── release.yml            # build Docker image + GitHub release on v* tags
├── Dockerfile                 # bot image
├── docker-compose.yml         # bot + postgres services
├── .dockerignore
├── .env.example
└── README.md
```
