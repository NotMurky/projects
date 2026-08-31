"""Discord /hours handler for the existing <BOT_NAME_REDACTED> VelocityDiscord bot.

This is deliberately a companion *handler*, not a second Discord bot identity:
it reads the token and channel already configured for VelocityDiscord and only
handles the /hours interaction. VelocityDiscord continues to own chat bridging,
/list, presence, and all normal Discord behavior.

Discord's application-command API is used only to register /hours in the
Prominence channel's guild. Responses are ephemeral so playtime lookups do not
spam the bridge channel.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from pathlib import Path

import aiohttp
import discord

from store import Store, fmt_hours

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("prominence.hours.discord")

VELOCITY_DISCORD_CONFIG = Path(os.environ.get(
    "VELOCITY_DISCORD_CONFIG",
    "/data/compose/13/docker/servers/43ac65de-795f-443f-9cc5-2aecc7447a05/plugins/discord/config.toml",
))
DB_PATH = os.environ.get("HOURS_DB", "/home/<USERNAME_REDACTED>/prominence-hours/hours.db")


def velocity_discord_credentials() -> tuple[str, int]:
    """Read the already-configured Personal bot token + Prominence channel ID.

    The token is never logged, printed, copied, or placed in an env file.
    """
    text = VELOCITY_DISCORD_CONFIG.read_text(encoding="utf-8")
    token = re.search(r'^token\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    channel = re.search(r'^channel\s*=\s*"(\d+)"\s*$', text, re.MULTILINE)
    if not token or not channel:
        raise RuntimeError("VelocityDiscord token/channel configuration not found")
    return token.group(1), int(channel.group(1))


def render_hours(store: Store, player: str | None) -> str:
    if player:
        row = store.get(player)
        if row is None:
            return f"No tracked active time for **{player}** yet. The tracker starts on their next join."
        active = fmt_hours(row["active_seconds"])
        afk = fmt_hours(row["afk_seconds"])
        return (
            f"**{row['name']}** — **{active}** active playtime\n"
            f"AFK excluded: {afk}\n"
            "AFK starts after 5 minutes with no movement or look-direction change."
        )

    rows = store.leaderboard(10)
    if not rows:
        return "No active playtime recorded yet. The tracker is running and will start counting on the next player join."
    lines = ["**Prominence active-playtime leaderboard**"]
    for pos, row in enumerate(rows, 1):
        lines.append(f"`{pos:>2}.` **{row['name']}** — {fmt_hours(row['active_seconds'])}")
    lines.append("_AFK time is excluded after 5 minutes without moving or looking around._")
    return "\n".join(lines)


class HoursClient(discord.Client):
    def __init__(self, token: str, channel_id: int):
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        self.token_value = token
        self.channel_id = channel_id
        self.store = Store(DB_PATH)
        self._registered = False

    async def setup_hook(self) -> None:
        # This bot application may already have VelocityDiscord's /list command.
        # POSTing *only* /hours is non-destructive; do not use bulk PUT/sync.
        app = await self.application_info()
        channel = await self.fetch_channel(self.channel_id)
        guild_id = channel.guild.id
        payload = {
            "name": "hours",
            "description": "Show tracked non-AFK Prominence playtime",
            "options": [{
                "name": "player",
                "description": "Minecraft username (omit for leaderboard)",
                "type": 3,
                "required": False,
            }],
        }
        url = f"https://discord.com/api/v10/applications/{app.id}/guilds/{guild_id}/commands"
        headers = {"Authorization": f"Bot {self.token_value}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                body = await resp.text()
                if resp.status not in (200, 201):
                    raise RuntimeError(f"/hours registration failed: Discord HTTP {resp.status}: {body[:300]}")
        self._registered = True
        log.info("registered /hours for guild %s (Prominence channel %s)", guild_id, self.channel_id)

    async def on_ready(self) -> None:
        log.info("hours handler connected as %s; command_registered=%s", self.user, self._registered)

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        data = interaction.data or {}
        if interaction.type is not discord.InteractionType.application_command:
            return
        if data.get("name") != "hours":
            return  # Leave /list and all VelocityDiscord interactions alone.
        # The command itself is guild-scoped, but keep a narrow runtime guard too.
        if interaction.channel_id != self.channel_id:
            await interaction.response.send_message("This command is only available in the Prominence server channel.", ephemeral=True)
            return
        opts = data.get("options") or []
        player = next((str(x.get("value", "")).strip() for x in opts if x.get("name") == "player"), None)
        # Minecraft usernames are ASCII word characters, 3–16 chars. Rejecting
        # arbitrary input prevents formatting abuse and makes intended lookup clear.
        if player and not re.fullmatch(r"[A-Za-z0-9_]{3,16}", player):
            await interaction.response.send_message("Use a valid Minecraft username (3–16 letters, numbers, or underscores).", ephemeral=True)
            return
        try:
            text = await asyncio.to_thread(render_hours, self.store, player)
            await interaction.response.send_message(text, ephemeral=True)
        except Exception:
            log.exception("/hours failed")
            if not interaction.response.is_done():
                await interaction.response.send_message("Hours lookup failed; please try again.", ephemeral=True)

    async def close(self) -> None:
        self.store.close()
        await super().close()


def main() -> None:
    token, channel_id = velocity_discord_credentials()
    client = HoursClient(token, channel_id)
    client.run(token, log_handler=None)


if __name__ == "__main__":
    main()
