"""Boss event → Discord broadcaster for Prominence.

Polls the mod's damage.db (read-only) for boss sessions and posts to the
Prominence Discord channel via the existing <BOT_NAME_REDACTED> bot identity (REST):
  - when a boss spawns (a new open session appears)
  - when a boss is defeated (a session gains end_reason='death'), with a total
    damage summary, per-player contribution, and unattributed damage if any.

Read-only against damage.db; the mod remains the single writer. Cursor state is
persisted so restarts don't replay old events.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

DB_PATH = os.environ.get(
    "DAMAGE_DB",
    "/data/compose/13/docker/servers/50a6d163-0309-4832-986f-106668768b3d/prominence-damage/damage.db",
)
STATE_PATH = Path(os.environ.get("BOSS_WATCH_STATE", "/home/<USERNAME_REDACTED>/prominence-hours/boss-watch-state.json"))
POLL_SECONDS = float(os.environ.get("BOSS_WATCH_POLL", "5"))


def hearts(hp: float) -> str:
    h = hp / 2.0
    rounded = round(h, 1)
    if rounded == int(rounded):
        number = f"{int(rounded):,}"
    else:
        number = f"{rounded:,.1f}"
    unit = "heart" if rounded == 1.0 else "hearts"
    return f"{number} {unit}"


def _connect_ro(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def new_spawns(db_path: str, after_spawn_ms: int) -> list[tuple]:
    """Sessions whose spawned_at > cursor, oldest first. Returns (uuid, type, name, spawned_at)."""
    con = _connect_ro(db_path)
    try:
        rows = con.execute(
            "SELECT boss_entity_uuid,boss_type_id,boss_display_name,spawned_at "
            "FROM boss_sessions WHERE spawned_at > ? ORDER BY spawned_at ASC",
            (after_spawn_ms,),
        ).fetchall()
    finally:
        con.close()
    return [(r["boss_entity_uuid"], r["boss_type_id"], r["boss_display_name"], r["spawned_at"]) for r in rows]


def new_deaths(db_path: str, after_ended_ms: int) -> list[tuple]:
    """Sessions that ended by death with ended_at > cursor, oldest first."""
    con = _connect_ro(db_path)
    try:
        rows = con.execute(
            "SELECT boss_entity_uuid,boss_type_id,boss_display_name,ended_at "
            "FROM boss_sessions WHERE end_reason='death' AND ended_at > ? ORDER BY ended_at ASC",
            (after_ended_ms,),
        ).fetchall()
    finally:
        con.close()
    return [(r["boss_entity_uuid"], r["boss_type_id"], r["boss_display_name"], r["ended_at"]) for r in rows]


def session_summary(db_path: str, boss_uuid: str):
    """Return (total_hp, [(name, hp) desc], unattributed_hp) for a boss session."""
    con = _connect_ro(db_path)
    try:
        contribs = con.execute(
            "SELECT attacker_name AS n, SUM(actual_damage) AS d FROM raw_hits "
            "WHERE boss_session_uuid=? AND attacker_uuid IS NOT NULL GROUP BY attacker_uuid "
            "ORDER BY d DESC",
            (boss_uuid,),
        ).fetchall()
        unattr = con.execute(
            "SELECT COALESCE(SUM(actual_damage),0) FROM raw_hits "
            "WHERE boss_session_uuid=? AND attacker_uuid IS NULL",
            (boss_uuid,),
        ).fetchone()[0]
    finally:
        con.close()
    ranked = [(r["n"], r["d"]) for r in contribs]
    total = sum(d for _, d in ranked) + (unattr or 0.0)
    return total, ranked, (unattr or 0.0)


def render_spawn(name: str) -> str:
    return f"⚔️  **{name}** has spawned! The fight is on."


def render_death(name: str, total_hp: float, ranked: list[tuple], unattributed_hp: float) -> str:
    lines = [f"☠️  **{name} has been defeated!**"]
    if total_hp > 0:
        lines.append(f"Total damage: **{hearts(total_hp)}**")
    if ranked:
        lines.append("**Damage by player:**")
        medals = ["🥇", "🥈", "🥉"]
        for i, (pname, dmg) in enumerate(ranked):
            tag = medals[i] if i < 3 else f"`{i+1}.`"
            pct = (dmg / total_hp * 100.0) if total_hp > 0 else 0.0
            lines.append(f"{tag} **{pname}** — {hearts(dmg)} ({pct:.0f}%)")
    else:
        lines.append("_No player damage was recorded._")
    if unattributed_hp > 0.0001:
        pct = (unattributed_hp / total_hp * 100.0) if total_hp > 0 else 0.0
        lines.append(f"✦ _unattributed_ — {hearts(unattributed_hp)} ({pct:.0f}%)")
    return "\n".join(lines)


# ---- runtime (not exercised by unit tests) --------------------------------
def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(tmp, STATE_PATH)


def _post(token: str, channel_id: int, content: str) -> None:
    import urllib.request

    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        data=json.dumps({"content": content}).encode(),
        method="POST",
        headers={
            "Authorization": "Bot " + token,
            "Content-Type": "application/json",
            "User-Agent": "ProminenceBossWatch/1.0",
        },
    )
    urllib.request.urlopen(req, timeout=15).read()


def main() -> None:
    import logging
    import sys

    from hours_discord import velocity_discord_credentials

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stdout)
    log = logging.getLogger("prominence.boss_watch")
    token, channel_id = velocity_discord_credentials()
    state = _load_state()

    # Baseline on first run: don't replay history.
    if "spawn_cursor" not in state or "death_cursor" not in state:
        con = _connect_ro(DB_PATH)
        try:
            sc = con.execute("SELECT COALESCE(MAX(spawned_at),0) FROM boss_sessions").fetchone()[0]
            dc = con.execute("SELECT COALESCE(MAX(ended_at),0) FROM boss_sessions WHERE end_reason='death'").fetchone()[0]
        finally:
            con.close()
        state = {"spawn_cursor": sc, "death_cursor": dc}
        _save_state(state)
        log.info("boss watch baseline set spawn=%s death=%s", sc, dc)

    log.info("boss watch running against %s -> channel %s", DB_PATH, channel_id)
    while True:
        try:
            for uuid, _type, name, spawned in new_spawns(DB_PATH, state["spawn_cursor"]):
                _post(token, channel_id, render_spawn(name))
                state["spawn_cursor"] = max(state["spawn_cursor"], spawned)
                _save_state(state)
                log.info("announced spawn %s", name)
            for uuid, _type, name, ended in new_deaths(DB_PATH, state["death_cursor"]):
                total, ranked, unattr = session_summary(DB_PATH, uuid)
                _post(token, channel_id, render_death(name, total, ranked, unattr))
                state["death_cursor"] = max(state["death_cursor"], ended)
                _save_state(state)
                log.info("announced death %s", name)
        except Exception:
            log.exception("boss watch cycle error")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
