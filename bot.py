import os
import re
import json
import asyncio
import aiohttp
import discord
from discord import app_commands
from dotenv import load_dotenv
from aiohttp import web

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID_RAW = os.getenv("GUILD_ID", "").strip()
GUILD_ID = int(GUILD_ID_RAW) if GUILD_ID_RAW.isdigit() else 0

PANEL_BASE = os.getenv("PANEL_BASE", "http://82.41.64.36:2007").rstrip("/")
PANEL_USER = os.getenv("PANEL_USER", "")
PANEL_PASS = os.getenv("PANEL_PASS", "")
PANEL_ADD_ACTION = "add_uid"
DEFAULT_DAYS = int(os.getenv("DEFAULT_DAYS", "30"))

GLOBAL_UID_LIMIT = int(os.getenv("GLOBAL_UID_LIMIT", "100"))

WATCH_CHANNEL_ID_RAW = os.getenv("WATCH_CHANNEL_ID", "").strip()
WATCH_CHANNEL_ID = int(WATCH_CHANNEL_ID_RAW) if WATCH_CHANNEL_ID_RAW.isdigit() else 0
TICKET_CHANNEL_ID_RAW = os.getenv("TICKET_CHANNEL_ID", "").strip()
TICKET_CHANNEL_ID = int(TICKET_CHANNEL_ID_RAW) if TICKET_CHANNEL_ID_RAW.isdigit() else 0
PORT = int(os.getenv("PORT", "10000"))
REQUEST_TIMEOUT = 20
UID_RE = re.compile(r"^\d{8,12}$")

OWNER_ID = 1470430137131597936
DEFAULT_LIMIT = 1
CLAIMS_DB = "claims.json"
LIMITS_DB = "limits.json"

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN missing in environment")
if not PANEL_USER or not PANEL_PASS:
    raise SystemExit("PANEL_USER / PANEL_PASS missing in environment")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

_claims_lock = asyncio.Lock()
_panel_session: aiohttp.ClientSession | None = None


def _load_json(path: str, default: dict) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def _save_json(path: str, data: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[db] save failed ({path}): {e}")


def load_claims() -> dict:
    return _load_json(CLAIMS_DB, {})


def save_claims(data: dict) -> None:
    _save_json(CLAIMS_DB, data)


def load_limits() -> dict:
    return _load_json(LIMITS_DB, {})


def save_limits(data: dict) -> None:
    _save_json(LIMITS_DB, data)


def get_user_limit(user_id: int) -> int:
    if user_id == OWNER_ID:
        return 10**9
    limits = load_limits()
    return int(limits.get(str(user_id), DEFAULT_LIMIT))


def get_user_claims(user_id: int) -> list:
    claims = load_claims()
    key = str(user_id)
    entry = claims.get(key)
    if not entry:
        return []
    if isinstance(entry, dict):
        return [entry]
    if isinstance(entry, list):
        return entry
    return []


def add_user_claim(user_id: int, uid: str) -> None:
    claims = load_claims()
    key = str(user_id)
    entry = claims.get(key)
    record = {"uid": uid, "claimedAt": discord.utils.utcnow().isoformat()}
    if entry is None:
        claims[key] = [record]
    elif isinstance(entry, dict):
        claims[key] = [entry, record]
    elif isinstance(entry, list):
        entry.append(record)
        claims[key] = entry
    else:
        claims[key] = [record]
    save_claims(claims)


def total_claims_count() -> int:
    claims = load_claims()
    total = 0
    for entry in claims.values():
        if isinstance(entry, list):
            total += len(entry)
        elif isinstance(entry, dict):
            total += 1
    return total


def ticket_link() -> str:
    if TICKET_CHANNEL_ID and GUILD_ID:
        return f"https://discord.com/channels/{GUILD_ID}/{TICKET_CHANNEL_ID}"
    return ""


def build_limit_embed(author: discord.abc.User, used: int, limit: int) -> discord.Embed:
    e = discord.Embed(
        title="\u26D4 User Limit Reached",
        description=(
            f"You have used **{used}/{limit}** of your allowed UID slots.\n"
            "To increase your limit or change a UID, open a ticket."
        ),
        color=discord.Color.from_rgb(220, 38, 38),
        timestamp=discord.utils.utcnow(),
    )
    link = ticket_link()
    if link:
        e.add_field(
            name="\U0001F3AB Open Ticket",
            value=f"[Click here]({link})",
            inline=False,
        )
    e.set_footer(
        text=f"Executed by {author.display_name}",
        icon_url=author.display_avatar.url,
    )
    return e


def build_global_limit_embed(author: discord.abc.User,
                             used: int, limit: int) -> discord.Embed:
    e = discord.Embed(
        title="\u26D4 Global UID Limit Reached",
        description=(
            f"All **{limit}** available UID slots have been used "
            f"(**{used}/{limit}**).\n"
            "No more UIDs can be added right now. Open a ticket for details."
        ),
        color=discord.Color.from_rgb(220, 38, 38),
        timestamp=discord.utils.utcnow(),
    )
    link = ticket_link()
    if link:
        e.add_field(
            name="\U0001F3AB Open Ticket",
            value=f"[Click here]({link})",
            inline=False,
        )
    e.set_footer(
        text=f"Executed by {author.display_name}",
        icon_url=author.display_avatar.url,
    )
    return e


async def _get_panel_session() -> aiohttp.ClientSession:
    global _panel_session
    if _panel_session is None or _panel_session.closed:
        _panel_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        )
    return _panel_session


async def submit_uid(uid: str) -> dict:
    session = await _get_panel_session()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Referer": f"{PANEL_BASE}/reseller",
        "Origin": PANEL_BASE,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        login_data = {"username": PANEL_USER, "password": PANEL_PASS}
        async with session.post(
            f"{PANEL_BASE}/login",
            data=login_data,
            headers=headers,
            allow_redirects=True,
        ) as lr:
            login_body = await lr.text()
            if "ADMIN LOGIN" in login_body or "CLIENT LOGIN" in login_body:
                print("[panel] login failed")
                return {"status": lr.status, "text": "login failed", "data": None}

        add_data = {
            "action": PANEL_ADD_ACTION,
            "uid": uid,
            "custom_name": "discord-bot",
            "days": str(DEFAULT_DAYS),
        }

        async with session.post(
            f"{PANEL_BASE}/reseller",
            data=add_data,
            headers=headers,
            allow_redirects=False,
        ) as r:
            status = r.status
            if status in (301, 302, 303, 307, 308):
                redirect_url = r.headers.get("Location", "/reseller")
                if not redirect_url.startswith("http"):
                    redirect_url = PANEL_BASE + redirect_url
                async with session.get(redirect_url, headers=headers) as gr:
                    text = await gr.text()
            else:
                text = await r.text()

        if "ADMIN LOGIN" in text or "CLIENT LOGIN" in text:
            return {"status": 200, "text": "Session dropped during POST.", "data": None}

        if uid in text:
            data = {
                "success": True,
                "claim": {"days": DEFAULT_DAYS, "expiresAt": ""},
                "apiResult": {"message": f"Account ID '{uid}' added successfully."},
                "message": f"Account ID '{uid}' added successfully.",
                "alreadyClaimed": False,
            }
            return {"status": 200, "text": text, "data": data}

        err = ""
        m = re.search(r'class="toast[^"]*"[^>]*>.*?<span[^>]*>([^<]+)', text, re.DOTALL)
        if m:
            err = m.group(1).strip()
        else:
            m = re.search(r'class="card-alert[^>]*>\s*([^<]+)', text)
            if m:
                err = m.group(1).strip()

        if "No UIDs registered yet" in text:
            return {"status": 200, "text": err or "Panel rejected UID (empty state returned).", "data": None}

        return {"status": 200, "text": err or "UID not found, and no error message was provided.", "data": None}

    except asyncio.TimeoutError:
        return {"status": 0, "text": "timeout", "data": None}
    except Exception as e:
        return {"status": 0, "text": f"{type(e).__name__}: {e}", "data": None}


def build_success(uid: str, data: dict, author: discord.abc.User,
                  used: int, limit: int) -> discord.Embed:
    claim = data.get("claim") or {}
    days = claim.get("days", "?")
    expires = claim.get("expiresAt", "")
    already = bool(data.get("alreadyClaimed"))
    server_msg = (
        data.get("message")
        or (data.get("apiResult") or {}).get("message")
        or f"Account ID '{uid}' added successfully."
    )

    embed = discord.Embed(
        title="\u2705 UID Added Successfully",
        color=discord.Color.from_rgb(220, 38, 38),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="\U0001F194 Target UID", value=f"`{uid}`", inline=True)
    embed.add_field(name="\u23F3 Active Days", value=f"**{days}** Day(s)", inline=True)
    embed.add_field(
        name="\U0001F4CA Usage",
        value=f"`{used}/{limit}`" if limit < 10**8 else "`unlimited`",
        inline=True,
    )
    embed.add_field(
        name="\U0001F4CB Server Message",
        value=f"```{server_msg}```",
        inline=False,
    )
    if expires:
        embed.add_field(name="\u23F0 Expires", value=f"`{expires}`", inline=False)
    if already:
        embed.add_field(
            name="\u26A0\uFE0F Note",
            value="This IP already claimed this portal.",
            inline=False,
        )
    embed.set_footer(
        text=f"Executed by {author.display_name}",
        icon_url=author.display_avatar.url,
    )
    return embed


def build_failure(uid: str, status: int, snippet: str,
                  author: discord.abc.User) -> discord.Embed:
    embed = discord.Embed(
        title="\u274c UID Add Failed",
        description=f"HTTP `{status}`" if status else "Network error",
        color=discord.Color.from_rgb(190, 18, 60),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Target UID", value=f"`{uid}`", inline=True)
    embed.add_field(
        name="Server Message",
        value=f"```{(snippet or 'no response body')[:300]}```",
        inline=False,
    )
    embed.set_footer(
        text=f"Executed by {author.display_name}",
        icon_url=author.display_avatar.url,
    )
    return embed


async def process_request(uid: str, author: discord.abc.User, reply_target):
    async with _claims_lock:
        total_used = total_claims_count()
        if GLOBAL_UID_LIMIT > 0 and total_used >= GLOBAL_UID_LIMIT:
            embed = build_global_limit_embed(author, total_used, GLOBAL_UID_LIMIT)
            if reply_target is not None:
                try:
                    await reply_target(embed)
                except discord.Forbidden:
                    pass
            return

        limit = get_user_limit(author.id)
        used_list = get_user_claims(author.id)
        used = len(used_list)

        if used >= limit:
            embed = build_limit_embed(author, used, limit)
            if reply_target is not None:
                try:
                    await reply_target(embed)
                except discord.Forbidden:
                    pass
            return

        result = await submit_uid(uid)
        data = result.get("data")
        status = result.get("status", 0)

        if status == 200 and isinstance(data, dict) and data.get("success"):
            add_user_claim(author.id, uid)
            new_used = used + 1
            embed = build_success(uid, data, author, new_used, limit)
        else:
            embed = build_failure(uid, status, result.get("text", ""), author)

        if reply_target is not None:
            try:
                await reply_target(embed)
            except discord.Forbidden:
                pass


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not message.guild:
        return
    if GUILD_ID and message.guild.id != GUILD_ID:
        return
    if WATCH_CHANNEL_ID and message.channel.id != WATCH_CHANNEL_ID:
        return

    content = message.content.strip()
    if not UID_RE.match(content):
        return

    async def reply(embed):
        try:
            await message.reply(embed=embed, mention_author=False)
        except discord.Forbidden:
            pass

    await process_request(content, message.author, reply)


@tree.command(name="add", description="Add a UID to the bypass portal")
@app_commands.describe(uid="Numeric game UID (8-12 digits)")
async def add_uid(interaction: discord.Interaction, uid: str):
    uid = uid.strip()
    if not UID_RE.match(uid):
        bad = discord.Embed(
            title="\u274c Invalid UID",
            description="UID must be 8 to 12 digits, numeric only.",
            color=discord.Color.from_rgb(220, 38, 38),
            timestamp=discord.utils.utcnow(),
        )
        bad.set_footer(
            text=f"Executed by {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url,
        )
        await interaction.response.send_message(embed=bad, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False, thinking=True)

    async def reply(embed):
        try:
            await interaction.followup.send(embed=embed, ephemeral=False)
        except discord.Forbidden:
            pass

    await process_request(uid, interaction.user, reply)


@tree.command(name="whitelist", description="Set UID limit for a user (owner only)")
@app_commands.describe(user="Target user", limit="Number of UIDs they can add")
async def whitelist_cmd(interaction: discord.Interaction,
                        user: discord.Member, limit: int):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "Owner only.", ephemeral=True
        )
        return

    if limit < 0 or limit > 1000:
        await interaction.response.send_message(
            "Limit must be between 0 and 1000.", ephemeral=True
        )
        return

    async with _claims_lock:
        limits = load_limits()
        if limit <= DEFAULT_LIMIT:
            limits.pop(str(user.id), None)
            effective = DEFAULT_LIMIT
        else:
            limits[str(user.id)] = limit
            effective = limit
        save_limits(limits)
        used = len(get_user_claims(user.id))

    embed = discord.Embed(
        title="\U0001F510 Whitelist Updated",
        color=discord.Color.from_rgb(220, 38, 38),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="User", value=user.mention, inline=True)
    embed.add_field(name="New Limit", value=f"`{effective}`", inline=True)
    embed.add_field(name="Used", value=f"`{used}`", inline=True)
    embed.set_footer(
        text=f"Executed by {interaction.user.display_name}",
        icon_url=interaction.user.display_avatar.url,
    )
    await interaction.response.send_message(embed=embed, ephemeral=False)


@tree.command(name="add-reset", description="Reset a user's UID claims (owner or admin)")
@app_commands.describe(user="User whose claims to reset")
@app_commands.default_permissions(manage_guild=True)
async def add_reset(interaction: discord.Interaction, user: discord.Member):
    if interaction.user.id != OWNER_ID and not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Not allowed.", ephemeral=True)
        return

    async with _claims_lock:
        claims = load_claims()
        removed = claims.pop(str(user.id), None)
        save_claims(claims)

    embed = discord.Embed(
        title="\u267B\uFE0F Claims Reset",
        description=f"Cleared claims for {user.mention}.",
        color=discord.Color.from_rgb(220, 38, 38),
        timestamp=discord.utils.utcnow(),
    )
    if removed:
        if isinstance(removed, list):
            uids = ", ".join(f"`{r.get('uid','?')}`" for r in removed)
        else:
            uids = f"`{removed.get('uid','?')}`"
        embed.add_field(name="Removed", value=uids or "—", inline=False)
    embed.set_footer(
        text=f"Executed by {interaction.user.display_name}",
        icon_url=interaction.user.display_avatar.url,
    )
    await interaction.response.send_message(embed=embed, ephemeral=False)


@tree.command(name="claims", description="Show a user's current claims")
@app_commands.describe(user="Target user (optional, default: yourself)")
async def claims_cmd(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    if target.id != interaction.user.id and interaction.user.id != OWNER_ID \
            and not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "You can only view your own claims.", ephemeral=True
        )
        return

    claims = get_user_claims(target.id)
    limit = get_user_limit(target.id)
    limit_str = "`unlimited`" if limit >= 10**8 else f"`{limit}`"

    embed = discord.Embed(
        title="\U0001F4C4 UID Claims",
        color=discord.Color.from_rgb(220, 38, 38),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="User", value=target.mention, inline=True)
    embed.add_field(name="Used", value=f"`{len(claims)}`", inline=True)
    embed.add_field(name="Limit", value=limit_str, inline=True)
    if claims:
        lines = []
        for c in claims:
            lines.append(f"`{c.get('uid','?')}` — {c.get('claimedAt','?')[:19]}")
        embed.add_field(
            name="UIDs",
            value="\n".join(lines)[:1000],
            inline=False,
        )
    embed.set_footer(
        text=f"Executed by {interaction.user.display_name}",
        icon_url=interaction.user.display_avatar.url,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="ping", description="Check if the bot is online")
async def ping(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    total = total_claims_count()
    global_str = "unlimited" if GLOBAL_UID_LIMIT <= 0 else f"{total}/{GLOBAL_UID_LIMIT}"
    await interaction.response.send_message(
        f"pong — gateway `{latency}ms`\n"
        f"guild: `{GUILD_ID or 'global'}`\n"
        f"watch: `{WATCH_CHANNEL_ID or 'any'}`\n"
        f"ticket: `{TICKET_CHANNEL_ID or 'unset'}`\n"
        f"global: `{global_str}`\n"
        f"claims: `{len(load_claims())}` | limits: `{len(load_limits())}`\n"
        f"commands: `{[c.name for c in tree.get_commands()]}`",
        ephemeral=True,
    )


@tree.command(name="sync", description="Re-sync slash commands (owner only)")
async def sync_cmd(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("Owner only.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            tree.copy_global_to(guild=guild)
            synced = await tree.sync(guild=guild)
        else:
            synced = await tree.sync()
        names = [c.name for c in synced]
        await interaction.followup.send(
            f"synced `{len(names)}` commands: `{names}`", ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(f"sync failed: `{e}`", ephemeral=True)


@client.event
async def on_ready():
    print(f"[ready] {client.user} (id={client.user.id})")
    print(f"[ready] owner: {OWNER_ID}")
    print(f"[ready] guild: {GUILD_ID or 'GLOBAL'}")
    print(f"[ready] watch: {WATCH_CHANNEL_ID or 'ANY'}")
    print(f"[ready] ticket: {TICKET_CHANNEL_ID or 'unset'}")
    print(f"[ready] panel: {PANEL_BASE} user={PANEL_USER} days={DEFAULT_DAYS}")
    print(f"[ready] global limit: {GLOBAL_UID_LIMIT or 'unlimited'}")
    print(f"[ready] claims: {len(load_claims())} | limits: {len(load_limits())}")

    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            tree.copy_global_to(guild=guild)
            synced = await tree.sync(guild=guild)
            print(f"[sync] guild {GUILD_ID} → {len(synced)} commands")
            for c in synced:
                print(f"[sync]   /{c.name}")
        else:
            synced = await tree.sync()
            print(f"[sync] global → {len(synced)} commands (up to 1h)")
            for c in synced:
                print(f"[sync]   /{c.name}")
    except discord.Forbidden as e:
        print(f"[sync] Forbidden — applications.commands scope missing? {e}")
    except Exception as e:
        print(f"[sync] failed: {type(e).__name__}: {e}")


async def _health(_request):
    return web.Response(text="ok")


async def start_http_server():
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/healthz", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"[http] keepalive on :{PORT}")


async def main():
    await start_http_server()
    await client.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
