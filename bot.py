@tree.command(name="add_uid", description="Add a UID to the bypass portal")
@app_commands.describe(uid="Numeric game UID (digits only)")
async def add_uid(interaction: discord.Interaction, uid: str):
    uid = uid.strip()

    # ---- validation: non-numeric → red embed ----
    if not uid.isdigit():
        bad = discord.Embed(
            title="\u274c Invalid UID",
            description="UID must contain digits only.",
            color=discord.Color.from_rgb(220, 38, 38),  # red-600
            timestamp=discord.utils.utcnow(),
        )
        bad.set_footer(text=f"Executed by {interaction.user.display_name}",
                       icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=bad, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

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

                    # ---- success embed ----
                    embed = discord.Embed(
                        title="\u2705 UID Added Successfully",
                        color=discord.Color.from_rgb(220, 38, 38),  # red
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

                    # Access line — first field of second row
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

                # ---- failure embed ----
                snippet = (text or "")[:300]
                fail = discord.Embed(
                    title="\u274c UID Add Failed",
                    description=f"HTTP `{r.status}`",
                    color=discord.Color.from_rgb(190, 18, 60),  # darker red
                    timestamp=discord.utils.utcnow(),
                )
                fail.add_field(
                    name="Target UID",
                    value=f"`{uid}`",
                    inline=True,
                )
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
        t.set_footer(text=f"Executed by {interaction.user.display_name}",
                     icon_url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=t, ephemeral=False)

    except Exception as e:
        t = discord.Embed(
            title="\u274c Request Error",
            description=f"```{e}```",
            color=discord.Color.from_rgb(190, 18, 60),
            timestamp=discord.utils.utcnow(),
        )
        t.set_footer(text=f"Executed by {interaction.user.display_name}",
                     icon_url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=t, ephemeral=False)
