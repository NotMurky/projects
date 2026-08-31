"""<BOT_NAME_REDACTED> Discord /damage companion.

The Minecraft Fabric mod owns damage queries and formatting. This gateway
handler forwards a validated Discord slash command to the backend over RCON and
publishes the result publicly in the configured Prominence channel.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path

import aiohttp
import discord

from mcrcon import MCRcon

log = logging.getLogger("prominence.damage.discord")
CONFIG = Path(os.environ.get(
    "VELOCITY_DISCORD_CONFIG",
    "/data/compose/13/docker/servers/43ac65de-795f-443f-9cc5-2aecc7447a05/plugins/discord/config.toml",
))
RCON_PASSWORD_FILE = Path(os.environ.get("RCON_PASSWORD_FILE", "/home/<USERNAME_REDACTED>/prominence-hours/rcon.pass"))
RCON_HOST = os.environ.get("RCON_HOST", "<INTERNAL_IP_REDACTED>.11")
RCON_PORT = int(os.environ.get("RCON_PORT", "25575"))
NAME_RE = re.compile(r"[A-Za-z0-9_]{3,16}")


def credentials() -> tuple[str, int]:
    text = CONFIG.read_text(encoding="utf-8")
    token = re.search(r'^token\s*=\s*"([^"]+)"', text, re.MULTILINE)
    channel = re.search(r'^channel\s*=\s*"(\d+)"', text, re.MULTILINE)
    if not token or not channel:
        raise RuntimeError("VelocityDiscord token/channel is missing")
    return token.group(1), int(channel.group(1))


def validate_minutes(value: int) -> int:
    value = int(value)
    if value < 1:
        raise ValueError("minutes must be at least 1")
    return value


def validate_player(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not NAME_RE.fullmatch(value):
        raise ValueError("invalid Minecraft player name")
    return value


def build_rcon_command(minutes: int, player: str | None) -> str:
    minutes = validate_minutes(minutes)
    player = validate_player(player)
    return f"damage {minutes}" + (f" {player}" if player else "")


def clean_output(text: str) -> str:
    # Minecraft legacy color codes are not useful in Discord.
    return re.sub(r"§.", "", text).strip() or "No damage data was returned."


def chunks(text: str, limit: int = 1900) -> list[str]:
    lines = text.splitlines() or [text]
    out: list[str] = []
    current = ""
    for line in lines:
        candidate = line if not current else current + "\n" + line
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                out.append(current)
            current = line[:limit]
    if current:
        out.append(current)
    return out


class DamageClient(discord.Client):
    def __init__(self, token: str, channel_id: int):
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        self.bot_token = token
        self.channel_id = channel_id
        self.rcon = MCRcon(RCON_HOST, RCON_PORT, RCON_PASSWORD_FILE.read_text().strip())

    async def setup_hook(self) -> None:
        app = await self.application_info()
        channel = await self.fetch_channel(self.channel_id)
        payload = {
            "name": "damage",
            "description": "Show Prominence damage totals for a recent time window",
            "options": [
                {"name": "minutes", "description": "Minutes of history", "type": 4, "required": True, "min_value": 1},
                {"name": "player", "description": "Minecraft username (optional)", "type": 3, "required": False},
            ],
        }
        url = f"https://discord.com/api/v10/applications/{app.id}/guilds/{channel.guild.id}/commands"
        headers = {"Authorization": f"Bot {self.bot_token}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status not in (200, 201):
                    raise RuntimeError(f"/damage registration failed: HTTP {response.status}: {(await response.text())[:200]}")
        log.info("registered /damage in Prominence guild")

    async def on_ready(self) -> None:
        log.info("connected as %s", self.user)

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        data = interaction.data or {}
        if interaction.type is not discord.InteractionType.application_command or data.get("name") != "damage":
            return
        if interaction.channel_id != self.channel_id:
            await interaction.response.send_message("Use `/damage` in the Prominence server channel.", ephemeral=True)
            return
        options = {item["name"]: item.get("value") for item in data.get("options", [])}
        try:
            command = build_rcon_command(options.get("minutes"), options.get("player"))
        except (TypeError, ValueError) as exc:
            await interaction.response.send_message(f"Invalid damage query: {exc}", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=False)
        try:
            output = clean_output(await asyncio.to_thread(self.rcon.command, command))
            parts = chunks(output)
            await interaction.followup.send(parts[0], ephemeral=False)
            for part in parts[1:]:
                await interaction.followup.send(part, ephemeral=False)
        except Exception:
            log.exception("damage RCON query failed")
            await interaction.followup.send("Damage query failed; the Minecraft server may be restarting.", ephemeral=False)

    async def close(self) -> None:
        self.rcon.close()
        await super().close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    token, channel_id = credentials()
    client = DamageClient(token, channel_id)
    client.run(token, log_handler=None)


if __name__ == "__main__":
    main()
