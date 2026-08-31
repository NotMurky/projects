#!/usr/bin/env python3
"""Post Luna voice transcript/reply pairs to the private Discord transcript channel."""

from __future__ import annotations

import json
import logging
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BIND_HOST = "<INTERNAL_IP_REDACTED>.12"
BIND_PORT = 8644
ALLOWED_SOURCE = "<INTERNAL_IP_REDACTED>.212"
DISCORD_CHANNEL_ID = "1540023321779769364"
MAX_BODY_BYTES = 16_384
LOG = logging.getLogger("luna_transcript_relay")


def is_allowed_source(address: str) -> bool:
    """Accept events only from the Home Assistant VM."""
    return address == ALLOWED_SOURCE


def _safe_text(value: str, limit: int) -> str:
    text = value.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
    text = " ".join(text.split())
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def format_discord_message(transcript: str, reply: str) -> str:
    """Format a compact, mention-safe Discord transcript entry."""
    prefix = "**Luna voice transcript**\n"
    user_label = "**You:** "
    luna_label = "**Luna:** "
    budget = 2000 - len(prefix) - len(user_label) - len(luna_label) - 2
    user_budget = budget // 2
    reply_budget = budget - user_budget
    return (
        f"{prefix}{user_label}{_safe_text(transcript, user_budget)}\n"
        f"{luna_label}{_safe_text(reply, reply_budget)}"
    )


def _load_discord_token() -> str:
    """Read the gateway bot token at runtime without logging it."""
    env_path = Path.home() / ".hermes" / ".env"
    for line in env_path.read_text().splitlines():
        if line.startswith("DISCORD_BOT_TOKEN="):
            token = line.split("=", 1)[1].strip()
            if token:
                return token
    raise RuntimeError("DISCORD_BOT_TOKEN is missing")


def post_to_discord(transcript: str, reply: str) -> None:
    """Create one Discord message using the configured bot token."""
    token = _load_discord_token()
    request = Request(
        f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages",
        data=json.dumps({"content": format_discord_message(transcript, reply)}).encode(),
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "LunaTranscriptRelay/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            if response.status not in (200, 201):
                raise RuntimeError(f"Discord returned HTTP {response.status}")
    except HTTPError as err:
        raise RuntimeError(f"Discord returned HTTP {err.code}") from err
    except URLError as err:
        raise RuntimeError("Discord request failed") from err


class TranscriptHandler(BaseHTTPRequestHandler):
    """HA-only JSON endpoint."""

    server_version = "LunaTranscriptRelay/1.0"

    def log_message(self, format: str, *args: object) -> None:
        LOG.info("%s - %s", self.client_address[0], format % args)

    def _respond(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/luna-transcript":
            self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not is_allowed_source(self.client_address[0]):
            self._respond(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if not 0 < size <= MAX_BODY_BYTES:
            self._respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "invalid_size"})
            return
        try:
            payload = json.loads(self.rfile.read(size))
            transcript = payload["transcript"]
            reply = payload["reply"]
            if not isinstance(transcript, str) or not isinstance(reply, str):
                raise ValueError("transcript/reply must be strings")
            post_to_discord(transcript, reply)
        except (ValueError, KeyError, json.JSONDecodeError):
            self._respond(HTTPStatus.BAD_REQUEST, {"error": "invalid_payload"})
            return
        except Exception:
            LOG.exception("Unable to post Luna transcript")
            self._respond(HTTPStatus.BAD_GATEWAY, {"error": "discord_unavailable"})
            return
        self._respond(HTTPStatus.CREATED, {"status": "posted"})


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), TranscriptHandler)
    LOG.info("Listening on %s:%d for Home Assistant transcripts", BIND_HOST, BIND_PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
