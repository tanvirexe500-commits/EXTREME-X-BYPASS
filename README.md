# UID Relay Bot

Discord slash-command bot that relays `/add <uid>` to a trial-claim endpoint.
Runs as a Render Web Service with a built-in aiohttp keepalive.

## Commands
- `/add uid:<digits>` — submit UID to the target trial endpoint
- `/ping` — check bot latency

## Setup (local)

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    # create .env with DISCORD_TOKEN, GUILD_ID, TARGET_URL
    python bot.py

## Setup (Render)

1. Push this repo (keep .env out of git).
2. Render → New → Web Service → connect repo.
3. Build: `pip install -r requirements.txt`
4. Start: `python bot.py`
5. Health path: `/healthz`
6. Env vars: `DISCORD_TOKEN`, `GUILD_ID`, `TARGET_URL`
7. UptimeRobot → HTTP monitor on `https://<service>.onrender.com/healthz` every 5 min.

## Discord bot permissions

Integer: `2147568640`
- View Channels
- Send Messages
- Embed Links
- Read Message History
- Use Slash Commands

Scopes: `bot`, `applications.commands`

## Security

Bot has no admin/manage/kick/ban permissions. Token leak → reset token in
Developer Portal, rotate Render env var, redeploy.