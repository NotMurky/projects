#!/usr/bin/env python3
"""Apply a pending AFK sensitivity update once Minecraft is empty.

Silent unless it applies or encounters a real error. The marker is removed only
after the tracker service restart succeeds, making the operation retry-safe.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/home/<USERNAME_REDACTED>/prominence-hours")
from mcrcon import MCRcon  # noqa: E402
from tracker import parse_list  # noqa: E402

PENDING = Path("/home/<USERNAME_REDACTED>/prominence-hours/pending-afk-update.json")
PASSWORD = Path("/home/<USERNAME_REDACTED>/prominence-hours/rcon.pass")
DROPIN_DIR = Path("/etc/systemd/system/prominence-hours-tracker.service.d")
DROPIN = DROPIN_DIR / "afk-sensitivity.conf"


def main() -> int:
    if not PENDING.exists():
        return 0
    cfg = json.loads(PENDING.read_text())
    password = PASSWORD.read_text().strip()
    rcon = MCRcon("<INTERNAL_IP_REDACTED>.11", 25575, password)
    try:
        players = parse_list(rcon.command("list"))
    except Exception:
        # Server unavailable/restarting is not proof of an empty, healthy server.
        return 0
    finally:
        rcon.close()
    if players:
        return 0

    threshold = int(cfg["afk_threshold"])
    poll = int(cfg["poll_interval"])
    pos = float(cfg["pos_epsilon"])
    rot = float(cfg["rot_epsilon"])
    if not (30 <= threshold <= 3600 and 2 <= poll <= 60 and 0 <= pos <= 2 and 0 <= rot <= 45):
        raise ValueError("pending AFK settings outside safe bounds")

    DROPIN_DIR.mkdir(parents=True, exist_ok=True)
    DROPIN.write_text(
        "[Service]\n"
        f"Environment=AFK_THRESHOLD={threshold}\n"
        f"Environment=POLL_INTERVAL={poll}\n"
        f"Environment=POS_EPSILON={pos}\n"
        f"Environment=ROT_EPSILON={rot}\n"
    )
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "restart", "prominence-hours-tracker.service"], check=True)
    PENDING.unlink()
    print(
        f"AFK update applied: threshold={threshold}s, poll={poll}s, "
        f"movement={pos} blocks, rotation={rot} degrees"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
