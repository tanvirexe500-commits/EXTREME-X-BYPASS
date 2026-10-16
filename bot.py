import os
import asyncio
import aiohttp
import discord
from discord import app_commands
from dotenv import load_dotenv
from aiohttp import web

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
TARGET_URL = os.getenv("TARGET_URL")
PORT = int(os.getenv("PORT", "10000"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    tree.copy_global_to(guild=guild)
    synced = await tree.sync(guild=guild)
    print(f"{client.user} online — synced {len(synced)} commands")


@tree.command(name="add", description="Add UID to the bypass portal")
@app_commands.describe(uid="Numeric game UID")
async def add_uid(interaction: discord.Interaction, uid: str):
    if not uid.isdigit():
        await interaction.response.send_message("UID must be numeric.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Origin": "https://ultimateuidbypass.site",
        "Referer": "https://ultimateuidbypass.site/",
        "Accept": "application/json, text/plain, */*",
    }

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(TARGET_URL, json={"uid": uid}, headers=headers,
                              timeout=aiohttp.ClientTimeout(total=20)) as r:
                text = await r.text()
                try:
                    data = await r.json()
                except Exception:
                    data = None

                if r.status == 200 and data and data.get("success"):
                    claim = data.get("claim") or {}
                    await interaction.followup.send(
                        f"UID `{uid}` added.\n"
                        f"duration: `{claim.get('days','?')}d`  •  "
                        f"expires: `{claim.get('expiresAt','?')}`",
                        ephemeral=True,
                    )
                else:
                    snippet = (text or "")[:300]
                    await interaction.followup.send(
                        f"Failed — HTTP {r.status}\n`{snippet}`",
                        ephemeral=True,
                    )
    except Exception as e:
        await interaction.followup.send(f"Request error: `{e}`", ephemeral=True)


# ----- keepalive HTTP server for Render -----

async def handle_ping(request):
    return web.Response(text="ok")


async def start_http():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/healthz", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"HTTP keepalive on :{PORT}")


async def main():
    await start_http()
    await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())