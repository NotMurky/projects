"""REST-only !hours command handler for <BOT_NAME_REDACTED> in the Prominence channel.

Why REST rather than a slash-command gateway handler:
Personal's Discord application has an existing interactions endpoint. Discord
routes slash interactions there, not to VelocityDiscord nor a companion gateway
connection. This daemon therefore polls only the configured Prominence channel
for ordinary !hours commands and posts replies as the SAME existing Personal
bot identity. It never connects a second gateway and never affects bridge chat.

Commands:
  !hours              active-time leaderboard
  !hours <Minecraft>  that player's active time and excluded AFK time
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from hours_discord import velocity_discord_credentials
from store import Store
from hours_discord import render_hours
from mcrcon import MCRcon

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stdout)
log = logging.getLogger("prominence.hours.discord_rest")

DB_PATH = os.environ.get("HOURS_DB", "/home/<USERNAME_REDACTED>/prominence-hours/hours.db")
STATE_PATH = Path(os.environ.get("HOURS_DISCORD_STATE", "/home/<USERNAME_REDACTED>/prominence-hours/discord-state.json"))
POLL_SECONDS = float(os.environ.get("DISCORD_POLL_SECONDS", "5"))
RCON_HOST = os.environ.get("RCON_HOST", "<INTERNAL_IP_REDACTED>.11")
RCON_PORT = int(os.environ.get("RCON_PORT", "25575"))
RCON_PASSWORD_FILE = Path(os.environ.get("RCON_PASSWORD_FILE", "/home/<USERNAME_REDACTED>/prominence-hours/rcon.pass"))
API = "https://discord.com/api/v10"
CMD_RE = re.compile(r"^!hours(?:\s+([A-Za-z0-9_]{3,16}))?\s*$", re.IGNORECASE)
DAMAGE_RE = re.compile(r"^!damage\s+(\d{1,4})(?:\s+([A-Za-z0-9_]{3,16}))?\s*$", re.IGNORECASE)
FORMATTING = re.compile(r"§.")


def rcon_command(command: str) -> str:
    try:
        password = RCON_PASSWORD_FILE.read_text().strip()
    except OSError as exc:
        return f"RCON password unavailable: {exc}"
    client = MCRcon(RCON_HOST, RCON_PORT, password)
    try:
        raw = client.command(command)
    except Exception as exc:  # noqa: BLE001 - report to Discord verbatim
        return f"RCON error: {exc}"
    finally:
        try: client.close()
        except Exception: pass
    return FORMATTING.sub("", raw or "").strip() or "(no output)"


def api_request(token: str, method: str, path: str, payload: dict | None = None) -> tuple[int, dict | list | None]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Authorization": "Bot " + token, "Content-Type": "application/json", "User-Agent": "ProminenceHours/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw)
        except Exception:
            body = {"error": raw.decode("utf-8", "replace")[:300]}
        return exc.code, body


def load_last_id() -> int | None:
    try:
        return int(json.loads(STATE_PATH.read_text()).get("last_id"))
    except Exception:
        return None


def save_last_id(message_id: int) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"last_id": str(message_id)}) + "\n")
    os.replace(tmp, STATE_PATH)


def is_newer(a: str, b: int | None) -> bool:
    return b is None or int(a) > b  # Discord snowflakes are sortable integers.


def main() -> None:
    token, channel_id = velocity_discord_credentials()
    store = Store(DB_PATH)
    last_id = load_last_id()
    bot_id: str | None = None
    log.info("!hours REST handler starting for Prominence channel %s", channel_id)

    while True:
        try:
            # Fetch newest first; 25 comfortably covers a brief outage without
            # querying channel history beyond command processing needs.
            status, messages = api_request(token, "GET", f"/channels/{channel_id}/messages?limit=25")
            if status != 200 or not isinstance(messages, list):
                log.warning("Discord message poll failed: HTTP %s", status)
                time.sleep(POLL_SECONDS)
                continue

            # Establish a baseline on first boot: do not reply to old commands.
            if last_id is None:
                if messages:
                    last_id = int(messages[0]["id"])
                    save_last_id(last_id)
                log.info("command polling ready; historical messages ignored")
                time.sleep(POLL_SECONDS)
                continue

            new = [m for m in messages if is_newer(m["id"], last_id)]
            for message in reversed(new):  # oldest -> newest
                last_id = int(message["id"])
                author = message.get("author", {})
                if bot_id is None:
                    # The bot's own ID is available from every returned author
                    # only after /users/@me below; defer fetching until needed.
                    pass
                content = (message.get("content") or "").strip()
                if author.get("bot"):
                    continue
                text: str | None = None
                match = CMD_RE.fullmatch(content)
                dmg_match = DAMAGE_RE.fullmatch(content)
                if match:
                    player = match.group(1)
                    text = render_hours(store, player)
                    label = f"!hours {player}" if player else "!hours"
                elif dmg_match:
                    minutes = int(dmg_match.group(1))
                    if not 1 <= minutes <= 10080:
                        text = "!damage minutes must be 1..10080"
                    else:
                        player = dmg_match.group(2)
                        if not player:
                            text = "Usage: !damage <minutes> <player>"
                        else:
                            text = "```\n" + rcon_command(f"pdamage {minutes} {player}") + "\n```"
                    label = f"!damage {minutes}" + (f" {dmg_match.group(2)}" if dmg_match.group(2) else "")
                else:
                    continue
                post_status, _ = api_request(token, "POST", f"/channels/{channel_id}/messages", {"content": text})
                if post_status not in (200, 201):
                    log.warning("reply failed: HTTP %s", post_status)
                else:
                    log.info("replied to %s", label)
            if new:
                save_last_id(last_id)
        except Exception:
            log.exception("unexpected Discord polling error")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
