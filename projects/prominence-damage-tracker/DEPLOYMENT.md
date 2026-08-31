# Prominence Damage Tracker — Deployment (v1.0.0)

Server: `/data/compose/13/docker/servers/50a6d163-0309-4832-986f-106668768b3d`
Crafty ID: `50a6d163-0309-4832-986f-106668768b3d`
Target: MC 1.20.1 / Fabric Loader 0.19.3 / Fabric API 0.92.11 / Java 17
Artifact: `~/prominence-damage-tracker/build/libs/prominence-damage-tracker-1.0.0.jar` (~14 MB, sqlite-jdbc bundled via Fabric JiJ)

## What the mod does
- Narrow `LivingEntity.damage` mixin captures actual post-mitigation health delta (server-only).
- Conservative attacker attribution: direct player → DamageSource attacker/source → recursive projectile owner → tameable owner. Nothing else is attributed to a player.
- Raw ledger + minute aggregates in `world/prominence-damage/damage.db` (SQLite WAL).
- Boss sessions UUID-keyed; seeded from `DefaultBossIds` + runtime `c:bosses` tag; op-mutable via `/damageboss`. Sessions restored on restart.
- Commands: `/pdamage <minutes>` (self, private, **all players**), `/pdamage <minutes> <player>` (broadcast), `/damageboss add|remove|list` (op).
- Broadcast on boss death (all contributors) and on despawn (attributed contributors only).

## Explicitly UNVERIFIED
- Mod-specific Spell Engine/spell-power adapters (spells that create their own DamageSource without preserving the caster) may be recorded as untraceable.
- Runtime validation against the live modpack has NOT been performed. First deploy is the smoke test.

## Preflight (must all be true)
1. `TOKEN=$(sudo cat /etc/prominence-daily-restart.token); curl -sk -H "Authorization: Bearer $TOKEN" https://127.0.0.1:8443/api/v2/servers/50a6d163-0309-4832-986f-106668768b3d/stats` → `running=True`.
2. RCON `list` shows **0 online players** (deploy only during zero-player window; else warn users first).
3. Backup produced (see below).

## Backup (before any file change)
```
SRV=/data/compose/13/docker/servers/50a6d163-0309-4832-986f-106668768b3d
STAMP=$(date +%Y%m%d-%H%M%S)
BAK=~/prominence-backups/damage-deploy-$STAMP
mkdir -p "$BAK"
cp -a "$SRV/mods" "$BAK/mods"
cp -a "$SRV/Dontdeleteimportantmods/mods" "$BAK/pin-mods"
```

## Maintenance on
Set MOTD/maintenance via existing VelocityDiscord + Velocity — user prefers to do this from <BOT_NAME_REDACTED> before restart. If scripted:
```
cd ~/prominence-updater && /usr/bin/python3 -c "from updater_core import VelocityMaintenanceToggle; VelocityMaintenanceToggle().enable()"
```

## Deploy (both directories — updater's `Dontdeleteimportantmods` overlay is what protects the jar against pack updates)
```
JAR=~/prominence-damage-tracker/build/libs/prominence-damage-tracker-1.0.0.jar
SRV=/data/compose/13/docker/servers/50a6d163-0309-4832-986f-106668768b3d
install -m 0644 "$JAR" "$SRV/Dontdeleteimportantmods/mods/prominence-damage-tracker-1.0.0.jar"
install -m 0644 "$JAR" "$SRV/mods/prominence-damage-tracker-1.0.0.jar"
sha256sum "$SRV/mods/prominence-damage-tracker-1.0.0.jar" "$SRV/Dontdeleteimportantmods/mods/prominence-damage-tracker-1.0.0.jar"
```

## Restart via Crafty (never `docker restart` directly)
```
TOKEN=$(sudo cat /etc/prominence-daily-restart.token)
curl -sk -H "Authorization: Bearer $TOKEN" -X POST \
  https://127.0.0.1:8443/api/v2/servers/50a6d163-0309-4832-986f-106668768b3d/action/restart_server
```

## Post-restart verification
1. Tail startup: `docker logs --tail 200 -f mc-prominence 2>&1 | grep -i "prominence damage\|damage_tracker\|mixin"` (log line: `Prominence damage tracker ready (N bosses tracked)`).
2. Via RCON: `/damageboss list` returns non-empty. `/damage 60` returns a total (initially 0).
3. Confirm `world/prominence-damage/damage.db` exists and is being written.
4. No new `mixin apply` errors in the log.

## Maintenance off
Reverse the maintenance toggle above.

## Rollback (any failure)
```
SRV=/data/compose/13/docker/servers/50a6d163-0309-4832-986f-106668768b3d
rm -f "$SRV/mods/prominence-damage-tracker-1.0.0.jar" \
      "$SRV/Dontdeleteimportantmods/mods/prominence-damage-tracker-1.0.0.jar"
# restart via Crafty as above
```
No world edits happen; damage.db is only read by the mod, so leaving it is safe.

## Discord `/damage` slash-command
<BOT_NAME_REDACTED>'s interactions endpoint lives outside Serpine (per prior audit). The in-game `/damage` command works standalone; the Discord command hookup is a separate change on the interactions host and is not part of this deployment.
