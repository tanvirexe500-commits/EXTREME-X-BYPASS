"""
UID Relay Bot
- Discord slash commands: /add_uid, /ping, /sync
- /add_uid relays UID to ultimateuidbypass.site trial claim endpoint
- Single-process: Discord client + aiohttp keepalive server for Render
"""

import os
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
PORT = int(os.getenv("PORT", "10000"))
REQUEST_TIMEOUT = 20

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN missing in environment")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# ---------- /add_uid ----------

@tree.command(name="add_uid", description="Add a UID to the bypass portal")
@app_commands.describe(uid="Numeric game UID (digits only)")
async def add_uid(interaction: discord.Interaction, uid: str):
    uid = uid.strip()

    # invalid input → red embed
    if not uid.isdigit():
        bad = discord.Embed(
            title="\u274c Invalid UID",
            description="UID must contain digits only.",
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
        async with aiohttp.ClientSession() as session:
            async with session.post(
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

                if r.status == 200 and isinstance(data, dict) and data.get("success"):
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
                    embed.add_field(
                        name="\U0001F194 Target UID",
                        value=f"`{uid}`",
                        inline=True,
                    )
                    embed.add_field(
                        name="\u23F3 Active Days",
                        value=f"**{days}** Day(s)",
                        inline=True,
                    )
                    access_text = "**\U0001F451 Admin Access (Unlimited)**"
                    if already:
                        access_text = "**\U0001F512 IP Lock \u2014 Already Claimed**"
                    embed.add_field(
                        name="\U0001F4B3 Credit Status",
                        value=access_text,
                        inline=False,
                    )
                    embed.add_field(
                        name="\U0001F4CB Server Message",
                        value=f"```{server_msg}```",
                        inline=False,
                    )
                    if expires:
                        embed.add_field(
                            name="\u23F0 Expires",
                            value=f"`{expires}`",
                            inline=False,
                        )
                    embed.set_footer(
                        text=f"Executed by {interaction.user.display_name}",
                        icon_url=interaction.user.display_avatar.url,
                    )

                    await interaction.followup.send(embed=embed, ephemeral=False)
                    return

                # failure embed
                snippet = (text or "")[:300]
                fail = discord.Embed(
                    title="\u274c UID Add Failed",
                    description=f"HTTP `{r.status}`",
                    color=discord.Color.from_rgb(190, 18, 60),
                    timestamp=discord.utils.utcnow(),
                )
                fail.add_field(name="Target UID", value=f"`{uid}`", inline=True)
                fail.add_field(
                    name="Server Message",
                    value=f"```{snippet or 'no response body'}```",
                    inline=False,
                )
                fail.set_footer(
                    text=f"Executed by {interaction.user.display_name}",
                    icon_url=interaction.user.display_avatar.url,
                )
                await interaction.followup.send(embed=fail, ephemeral=False)

    except asyncio.TimeoutError:
        t = discord.Embed(
            title="\u274c Request Timed Out",
            description="The bypass server took too long to respond.",
            color=discord.Color.from_rgb(190, 18, 60),
            timestamp=discord.utils.utcnow(),
        )
        t.set_footer(
            text=f"Executed by {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url,
        )
        await interaction.followup.send(embed=t, ephemeral=False)

    except Exception as e:
        t = discord.Embed(
            title="\u274c Request Error",
            description=f"```{e}```",
            color=discord.Color.from_rgb(190, 18, 60),
            timestamp=discord.utils.utcnow(),
        )
        t.set_footer(
            text=f"Executed by {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url,
        )
        await interaction.followup.send(embed=t, ephemeral=False)


# ---------- /ping ----------

@tree.command(name="ping", description="Check if the bot is online")
async def ping(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    await interaction.response.send_message(
        f"pong — gateway `{latency}ms`\n"
        f"guild scoped: `{GUILD_ID or 'global'}`\n"
        f"commands loaded: `{[c.name for c in tree.get_commands()]}`",
        ephemeral=True,
    )


# ---------- /sync (owner only) ----------

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


# ---------- ready ----------

@client.event
async def on_ready():
    print(f"[ready] {client.user} (id={client.user.id})")
    print(f"[ready] guild target: {GUILD_ID or 'GLOBAL'}")
    print(f"[ready] target url: {TARGET_URL}")

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


# ---------- keepalive HTTP for Render ----------

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
