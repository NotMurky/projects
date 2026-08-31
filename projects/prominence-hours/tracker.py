"""Prominence playtime tracker daemon.

Polls the Minecraft server over RCON every POLL_INTERVAL seconds. For each
online player it reads position + look-direction. A player who has not changed
BOTH position and rotation for AFK_THRESHOLD seconds flips to AFK, and the time
they spend AFK is credited to afk_seconds instead of active_seconds. Any change
in position OR rotation resets the idle timer and returns them to active.

Design notes:
- online-mode=false, so players are keyed by username.
- Time is credited by wall-clock delta between polls (robust to jitter and to
  the loop being slow), not by counting ticks.
- AFK detection ignores clicks/XP/damage by construction: only Pos+Rotation are
  read, so an auto-clicker standing at a farm is correctly counted AFK.
"""
from __future__ import annotations

import logging
import os
import re
import signal
import sys
import threading
import time

from mcrcon import MCRcon, RconError
from store import Store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("prominence.hours.tracker")

RCON_HOST = os.environ.get("RCON_HOST", "<INTERNAL_IP_REDACTED>.11")
RCON_PORT = int(os.environ.get("RCON_PORT", "25575"))
RCON_PASSWORD_FILE = os.environ.get("RCON_PASSWORD_FILE", "/home/<USERNAME_REDACTED>/prominence-hours/rcon.pass")
DB_PATH = os.environ.get("HOURS_DB", "/home/<USERNAME_REDACTED>/prominence-hours/hours.db")
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "20"))
AFK_THRESHOLD = float(os.environ.get("AFK_THRESHOLD", "300"))  # 5 minutes
# A tiny movement deadband so floating-point noise / server rounding doesn't
# count as "activity". 0.01 blocks = 1cm.
POS_EPSILON = float(os.environ.get("POS_EPSILON", "0.02"))
ROT_EPSILON = float(os.environ.get("ROT_EPSILON", "0.5"))  # degrees

_LIST_RE = re.compile(r"players online:\s*(.*)$")
_DATA_RE = re.compile(r"following entity data:\s*(.*)$")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def load_password() -> str:
    with open(RCON_PASSWORD_FILE) as fh:
        return fh.read().strip()


def parse_list(resp: str) -> list[str]:
    """'There are N of a max of M players online: a, b, c' -> [a,b,c]."""
    m = _LIST_RE.search(resp)
    if not m:
        return []
    tail = m.group(1).strip()
    if not tail:
        return []
    return [p.strip() for p in tail.split(",") if p.strip()]


def parse_vec(resp: str) -> tuple[float, ...] | None:
    """Parse '... entity data: [0.5d, 100.0d, 0.5d]' -> (0.5,100.0,0.5)."""
    m = _DATA_RE.search(resp)
    if not m:
        return None
    nums = _NUM_RE.findall(m.group(1))
    if not nums:
        return None
    return tuple(float(n) for n in nums)


class PlayerState:
    __slots__ = ("pos", "rot", "last_active_ts", "is_afk", "last_poll_ts", "afk_since")

    def __init__(self, pos, rot, now):
        self.pos = pos
        self.rot = rot
        self.last_active_ts = now
        self.last_poll_ts = now
        self.is_afk = False
        self.afk_since = None


def _fmt_away(seconds: float) -> str:
    total = int(seconds)
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m" if m else f"{h}h"
    if m:
        return f"{m}m {s}s" if s else f"{m}m"
    return f"{s}s"


class Tracker:
    def __init__(self):
        self.rcon = MCRcon(RCON_HOST, RCON_PORT, load_password())
        self.store = Store(DB_PATH)
        self.states: dict[str, PlayerState] = {}
        self._stop = threading.Event()

    def stop(self, *_):
        log.info("stop requested")
        self._stop.set()

    def _read_player(self, name: str):
        pos_resp = self.rcon.command(f"data get entity {name} Pos")
        rot_resp = self.rcon.command(f"data get entity {name} Rotation")
        return parse_vec(pos_resp), parse_vec(rot_resp)

    @staticmethod
    def _moved(old, new, eps) -> bool:
        if old is None or new is None or len(old) != len(new):
            return True  # unknown => treat as movement (fail open to "active")
        return any(abs(a - b) > eps for a, b in zip(old, new))

    def poll_once(self, now: float) -> None:
        try:
            online = parse_list(self.rcon.command("list"))
        except (RconError, OSError) as exc:
            log.warning("RCON list failed (server restarting?): %s", exc)
            return

        online_set = set(online)

        # Drop state for players who left (their credited time is already saved).
        for gone in list(self.states.keys()):
            if gone not in online_set:
                del self.states[gone]

        for name in online:
            try:
                pos, rot = self._read_player(name)
            except (RconError, OSError) as exc:
                log.warning("read %s failed: %s", name, exc)
                continue

            st = self.states.get(name)
            if st is None:
                # First observation this session — start the clock, credit nothing yet.
                self.states[name] = PlayerState(pos, rot, now)
                self.store.touch_seen(name)
                log.info("tracking %s (pos=%s rot=%s)", name, pos, rot)
                continue

            # Credit the wall-clock interval that actually elapsed for THIS player
            # since we last observed them (robust to slow/jittery poll cycles).
            interval = now - st.last_poll_ts
            interval_start = st.last_poll_ts
            st.last_poll_ts = now
            if interval <= 0:
                continue
            moved = self._moved(st.pos, pos, POS_EPSILON) or self._moved(st.rot, rot, ROT_EPSILON)

            if moved:
                st.last_active_ts = now
                if st.is_afk:
                    away = now - st.afk_since if st.afk_since else 0.0
                    log.info("%s is back (active) after %.0fs", name, away)
                    self._announce_back(name, away)
                    st.afk_since = None
                st.is_afk = False
                active_credit, afk_credit = interval, 0.0
            else:
                # If the 5-minute deadline falls within this polling interval,
                # split precisely at the deadline instead of rounding a whole
                # 20-second poll to AFK.
                deadline = st.last_active_ts + AFK_THRESHOLD
                if now < deadline:
                    active_credit, afk_credit = interval, 0.0
                else:
                    active_credit = max(0.0, deadline - interval_start)
                    afk_credit = interval - active_credit
                    if not st.is_afk:
                        st.is_afk = True
                        st.afk_since = deadline
                        log.info("%s -> AFK (idle %.0fs)", name, now - st.last_active_ts)
                        self._announce_afk(name)

            self.store.add_time(name, active=active_credit, afk=afk_credit)
            st.pos = pos
            st.rot = rot

        # Push an hours snapshot into the mod so in-game /hours works (the mod
        # cannot read this host-side DB directly). Best-effort; never fatal.
        self._push_hours_snapshot(online)

    def _tellraw_all(self, text_json: str) -> None:
        try:
            self.rcon.command(f"tellraw @a {text_json}")
        except (RconError, OSError) as exc:
            log.warning("tellraw failed: %s", exc)

    def _announce_afk(self, name: str) -> None:
        self._tellraw_all(
            '["",{"text":"%s","color":"yellow"},{"text":" is now AFK.","color":"gray"}]' % name
        )

    def _announce_back(self, name: str, away_seconds: float) -> None:
        self._tellraw_all(
            '["",{"text":"%s","color":"yellow"},{"text":" is back","color":"gray"},'
            '{"text":" (away %s).","color":"gray"}]' % (name, _fmt_away(away_seconds))
        )

    def _push_hours_snapshot(self, online: list[str]) -> None:
        for name in online:
            row = self.store.get(name)
            if not row:
                continue
            active = int(row["active_seconds"])
            afk = int(row["afk_seconds"])
            try:
                self.rcon.command(f"hoursdata {name} {active} {afk}")
            except (RconError, OSError) as exc:
                log.debug("hoursdata push failed for %s: %s", name, exc)

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        log.info(
            "tracker up: poll=%.0fs afk_threshold=%.0fs rcon=%s:%d db=%s",
            POLL_INTERVAL, AFK_THRESHOLD, RCON_HOST, RCON_PORT, DB_PATH,
        )
        # Verify RCON auth up front so a bad config fails loudly and fast.
        try:
            self.rcon.command("list")
        except Exception as exc:
            log.error("initial RCON check failed: %s", exc)
            raise

        while not self._stop.is_set():
            start = time.time()
            try:
                self.poll_once(start)
            except Exception:
                log.exception("poll cycle error")
            # Sleep the remainder of the interval, responsive to shutdown.
            elapsed = time.time() - start
            self._stop.wait(max(1.0, POLL_INTERVAL - elapsed))

        self.rcon.close()
        self.store.close()
        log.info("tracker stopped cleanly")


if __name__ == "__main__":
    Tracker().run()
