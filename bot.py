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
TARGET_URL = os.getenv(
    "TARGET_URL",
    "https://ultimateuidbypass.site/api/uid-system/trials/uid_trial_17de005fd3/claim",
)
WATCH_CHANNEL_ID_RAW = os.getenv("WATCH_CHANNEL_ID", "").strip()
WATCH_CHANNEL_ID = int(WATCH_CHANNEL_ID_RAW) if WATCH_CHANNEL_ID_RAW.isdigit() else 0
TICKET_CHANNEL_ID_RAW = os.getenv("TICKET_CHANNEL_ID", "").strip()
TICKET_CHANNEL_ID = int(TICKET_CHANNEL_ID_RAW) if TICKET_CHANNEL_ID_RAW.isdigit() else 0
PORT = int(os.getenv("PORT", "10000"))
REQUEST_TIMEOUT = 20
UID_RE = re.compile(r"^\d{8,12}$")
DB = "claims.json"

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN missing in environment")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

_claims_lock = asyncio.Lock()


def load_claims() -> dict:
    if os.path.exists(DB):
        try:
            with open(DB, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_claims(data: dict) -> None:
    try:
        with open(DB, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[claims] save failed: {e}")


def ticket_link() -> str:
    if TICKET_CHANNEL_ID and GUILD_ID:
        return f"https://discord.com/channels/{GUILD_ID}/{TICKET_CHANNEL_ID}"
    return ""


def build_limit_embed(author: discord.abc.User) -> discord.Embed:
    e = discord.Embed(
        title="\u26D4 User Limit Reached",
        description=(
            "You have already claimed **1 UID**.\n"
            "Each user may only add **1 UID** in total.\n\n"
            "To change or add another UID, open a ticket in "
            "**create-ticket**."
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


async def submit_uid(uid: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Origin": "https://ultimateuidbypass.site",
        "Referer": "https://ultimateuidbypass.site/",
        "Accept": "application/json, text/plain, */*",
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                TARGET_URL,
                json={"uid": uid},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as r:
                text = await r.text()
                try:
                    data = await r.json()
                except Exception:
                    data = None
                return {"status": r.status, "text": text, "data": data}
    except asyncio.TimeoutError:
        return {"status": 0, "text": "timeout", "data": None}
    except Exception as e:
        return {"status": 0, "text": f"{type(e).__name__}: {e}", "data": None}


def build_success(uid: str, data: dict, author: discord.abc.User) -> discord.Embed:
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


def build_failure(uid: str, status: int, snippet: str, author: discord.abc.User) -> discord.Embed:
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
        claims = load_claims()
        key = str(author.id)

        if key in claims:
            embed = build_limit_embed(author)
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
            claims[key] = {
                "uid": uid,
                "claimedAt": discord.utils.utcnow().isoformat(),
            }
            save_claims(claims)
            embed = build_success(uid, data, author)
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

    uid = content

    async def reply(embed):
        try:
            await message.reply(embed=embed, mention_author=False)
        except discord.Forbidden:
            pass

    await process_request(uid, message.author, reply)


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


@tree.command(name="add-reset", description="Reset a user's UID claim (admin only)")
@app_commands.describe(user="User whose claim to reset")
@app_commands.default_permissions(manage_guild=True)
async def add_reset(interaction: discord.Interaction, user: discord.Member):
    async with _claims_lock:
        claims = load_claims()
        key = str(user.id)
        if key not in claims:
            await interaction.response.send_message(
                f"{user.mention} has no claim on record.", ephemeral=True
            )
            return
        old = claims.pop(key)
        save_claims(claims)

    embed = discord.Embed(
        title="\u267B\uFE0F Claim Reset",
        description=f"Removed claim for {user.mention}.",
        color=discord.Color.from_rgb(220, 38, 38),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Previous UID", value=f"`{old.get('uid','?')}`", inline=True)
    embed.set_footer(
        text=f"Executed by {interaction.user.display_name}",
        icon_url=interaction.user.display_avatar.url,
    )
    await interaction.response.send_message(embed=embed, ephemeral=False)


@tree.command(name="ping", description="Check if the bot is online")
async def ping(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    claims = load_claims()
    await interaction.response.send_message(
        f"pong — gateway `{latency}ms`\n"
        f"guild scoped: `{GUILD_ID or 'global'}`\n"
        f"watch channel: `{WATCH_CHANNEL_ID or 'any'}`\n"
        f"ticket channel: `{TICKET_CHANNEL_ID or 'unset'}`\n"
        f"total claims recorded: `{len(claims)}`\n"
        f"commands loaded: `{[c.name for c in tree.get_commands()]}`",
        ephemeral=True,
    )


@tree.command(name="sync", description="Re-sync slash commands (owner only)")
async def sync_cmd(interaction: discord.Interaction):
    if interaction.user.id != interaction.client.application.owner.id:
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
    print(f"[ready] guild target: {GUILD_ID or 'GLOBAL'}")
    print(f"[ready] watch channel: {WATCH_CHANNEL_ID or 'ANY'}")
    print(f"[ready] ticket channel: {TICKET_CHANNEL_ID or 'unset'}")
    print(f"[ready] target url: {TARGET_URL}")
    print(f"[ready] claims on disk: {len(load_claims())}")

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
