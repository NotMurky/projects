# Prominence Permanent Damage & Boss Contribution Tracker

**Status:** Discovery/specification only. No tracker mod has been built or installed.

**Purpose:** Preserve the confirmed server facts and user requirements so a future LLM can continue the work without rediscovering the modpack, boss IDs, or product decisions.

**Discovery date:** 2026-08-30

---

## 1. Hard user requirements

### 1.1 Scope

Build a **server-side Fabric damage tracker** for Prominence II that covers:

1. Every boss in the quest progression.
2. Vanilla bosses, explicitly including the Wither and Ender Dragon.
3. Side bosses found across the world, including the Old Champion.
4. A permanent all-damage ledger as a fallback, not only boss damage.

This is **not** limited to the Nether Gauntlet.

### 1.2 Boss fight sessions

- A fight begins when a qualifying boss entity **spawns**.
- Each actual entity instance is a separate fight, keyed by its UUID. Two bosses of the same type active concurrently must produce distinct sessions.
- A fight remains open until **that entity dies or despawns**. There is no inactivity timeout.
- On death/despawn, publish the fight result to both:
  - global in-game chat; and
  - the Prominence Discord channel through the existing <BOT_NAME_REDACTED> bridge.
- Store boss-fight summaries permanently.

### 1.3 Damage attribution

Credit damage to the player who caused it, including:

- direct melee;
- player-fired projectiles;
- spells;
- abilities;
- summoned entities;
- lingering/persistent effects.

The implementation must follow ownership/caster chains and credit the actual originating player whenever resolvable. It must **not** guess using “last player to hit.”

If player attribution cannot be resolved, retain the event and explicitly indicate it in the boss report, for example:

```text
Damage Done by Dark Mage (untraceable damage)
```

Use the actual source/entity display name where available. Never silently discard or falsely assign this damage.

### 1.4 `/damage` command semantics

All players may run damage commands.

- `/damage <minutes>` (e.g. `/damage 30`) is shown only to the in-game command sender.
- It reports a per-player leaderboard with **three values**:
  1. total damage;
  2. damage done to players;
  3. damage done to non-player entities.
- `/damage <minutes> <player>` (e.g. `/damage 30 Murky`) returns that player’s three totals, and this targeted form is publicly visible to everyone.
- Discord equivalent: command/result should be publicly visible to the Prominence Discord channel.

### 1.5 Retention

- Keep **every raw hit forever**.
- Also keep permanent compact aggregate tables for fast reporting.
- This is intended to support lifetime/server-lifespan records.

### 1.6 Edge-case decisions (confirmed)

#### Delayed environmental / trap damage

- Credit TNT, lava, fire, traps, placed blocks, and similar delayed environmental damage to a player **only when ownership can be identified with confidence**.
- Implement ownership metadata for player-caused sources where technically possible (for example, primed TNT owner and tracked block placement where supported).
- If ownership cannot be proven, retain the damage event and classify it as **Untracked/Untraceable**; never guess a player.

#### Boss-linked secondary entities

Anything linked to a tracked boss is treated as part of that boss's fight session. This includes boss parts, shields, transformations/phases, linked secondary forms, and spawned minions where a verifiable parent/owner relationship exists.

Damage to linked entities must be rolled into the parent boss's contribution session rather than starting a separate fight.

#### Despawn reporting

- On boss despawn/removal, publish a result only if at least one player has player-attributed damage in that session.
- If there are no player-attributed contributors, quietly persist/close the session without an announcement.
- Untraceable damage by itself does not create a player-attributed contributor.

#### Unloaded bosses and restarts

- Keep a boss session open indefinitely across chunk unloads and server restarts.
- Temporary absence from loaded chunks is **not** a despawn.
- Close only on confirmed death or a confirmed true despawn/removal event.

#### Player-versus-player damage

Record PvP damage with both identities:

- attacking player UUID + last-known name;
- receiving player UUID + last-known name;
- timestamp, actual post-mitigation damage, damage-source attribution, and dimension.

`/damage` reports exactly these three values per attacking player:

1. **Total damage** = PvP damage + player-to-entity damage;
2. **Player-to-player damage**;
3. **Player-to-entity damage**.

The permanent raw ledger must additionally support recipient-side queries/reports such as “who damaged this player, when, and how much.”

### 1.8 Final command and presentation rules (confirmed)

- Only Minecraft **server operators** may add, remove, or otherwise edit automatic boss entity types/configuration.
- A completed boss report shows **every contributor**, not just a top-N subset.
- Discord damage queries must use a **`/damage` Discord slash command**.
- <BOT_NAME_REDACTED> has an existing externally configured Discord Interactions Endpoint. The `/damage` Discord implementation must be added to that existing endpoint/handler; do not register a competing gateway handler or replace/hijack the endpoint.

### 1.9 Boss list management

The built mod must include administrative in-game commands to:

- add an entity type to the automatic boss tracking list; and
- list all entity types currently tracked as bosses.

The initial list must be populated from:

1. bosses referenced by quest progression;
2. `c:bosses` tag supplied by installed mods;
3. vanilla boss IDs; and
4. discovered side-boss IDs.

---

## 2. Server / deployment facts

### 2.1 Minecraft instance

- Server root:
  `/data/compose/13/docker/servers/50a6d163-0309-4832-986f-106668768b3d`
- Platform: **Fabric 1.20.1**.
- Fabric API installed: `fabric-api-0.92.11+1.20.1.jar`.
- Server is launched under Crafty; a server-side mod belongs in the backend server `mods/` directory, not Velocity’s plugin directory.
- Velocity is the public proxy; it runs the existing Discord bridge.

### 2.2 Discord bridge

- The correct Discord identity is **<BOT_NAME_REDACTED>**, not MurkyTheHermes.
- It is provided by the Velocity plugin:
  `VelocityDiscord-1.9.0.jar`.
- Its config is under Velocity’s `plugins/discord/config.toml`.
- The bridge already relays regular Minecraft chat/events to the Prominence Discord channel.
- Do not expose tokens in logs, code, documents, or chat.
- Do not replace/hijack Personal’s existing Discord interactions endpoint.

### 2.3 Existing hours tracker (separate feature)

Existing unrelated services:

- `prominence-hours-tracker.service`
- `prominence-hours-discord.service`

The hours tracker uses RCON and SQLite. Do **not** try to implement damage tracking by RCON/log scraping: RCON cannot observe individual damage events or reliably reconstruct attribution.

---

## 3. Installed boss sources and confirmed IDs

### 3.1 Shared `c:bosses` tag

The installed pack already has seven mods that publish `data/c/tags/entity_types/bosses.json`. Use the runtime Fabric entity-type tag, not hardcoded jar scanning, as the normal automatic detection mechanism.

#### AdventureZ (`adventurez-1.4.20.jar`)

- `adventurez:blackstone_golem`
- `adventurez:the_eye`
- `adventurez:void_shadow`

#### Archon Renewed (`Archon-1.1.5.jar`)

- `minecraft:wither`
- `minecraft:ender_dragon`
- `minecraft:elder_guardian`
- `minecraft:warden`
- `archon:tar`
- `archon:ayla`
- `archon:leven`
- `archon:inigo`
- `archon:null`

#### Bosses of Mass Destruction (`BOMD-1.7.5-1.20.1.jar`)

- `bosses_of_mass_destruction:lich`
- `bosses_of_mass_destruction:obsidilith`
- `bosses_of_mass_destruction:gauntlet`
- `bosses_of_mass_destruction:void_blossom`

#### Botania (`Botania-1.20.1-453-FABRIC.jar`)

- `botania:doppleganger`

#### Minecells (`minecells-2.0.0.jar`)

- `minecells:conjunctivius`

#### Marium’s Soulslike Weaponry (`soulslike-weaponry-1.3.1-1.20.1-fabric.jar`)

- `minecraft:ender_dragon`
- `minecraft:wither`
- `soulsweapons:accursed_lord_boss`
- `soulsweapons:draugr_boss`
- `soulsweapons:night_shade`
- `soulsweapons:returning_knight`
- `soulsweapons:chaos_monarch`
- `soulsweapons:moonknight`
- `soulsweapons:day_stalker`
- `soulsweapons:night_prowler`

#### The Bumblezone (`the_bumblezone-7.9.10+1.20.1-fabric.jar`)

- `the_bumblezone:cosmic_crystal_entity`

### 3.2 Old Champion provenance

The “Old Champion” is from Marium’s Soulslike Weaponry:

- Entity ID: `soulsweapons:draugr_boss`
- Display localization: `Old Champion's Remains`
- The mod also describes the Old Moon Altar encounter as fighting the Old Champion again.

This ID is already in `c:bosses` and should be automatically covered.

### 3.3 Explicit vanilla coverage

Always seed these as boss types even if tags change:

- `minecraft:ender_dragon`
- `minecraft:wither`

The current `c:bosses` tag additionally recognizes the Elder Guardian and Warden via Archon. Whether they are conceptually treated as “boss sessions” should remain configurable, but the default discovered list should include them.

### 3.4 Known boss-related installed mods

Other relevant sources found in the pack:

- `rpg-minibosses` — ANARCHY RPG Minibosses
- `archon` — Archon Renewed
- `graveyard` — The Graveyard
- `soulsweapons` — Marium’s Soulslike Weaponry
- `prominent` — Prominent
- `zenith` — Zenith Renewed

Quest configuration is at:

`config/ftbquests/quests/`

Important quest chapters include:

- `main_story.snbt`
- `elhasturian_era.snbt`
- `the_nether.snbt`
- `to_the_end.snbt`
- `archon.snbt`
- `gear_mariums_soulslike_weaponry.snbt`
- `botania.snbt`
- `deeper_and_darker.snbt`

A build phase must parse these SNBT quest chapters and reconcile their entity/objective IDs against the tag-derived list. Add explicit missing quest bosses to the persistent configured boss list.

---

## 4. Spell / ability attribution discovery

The modpack has a substantial spell/ability ecosystem. Relevant installed mods include:

- `spell_engine` 0.15.12
- `spell_power` 0.12.0
- `spellbladenext` 2.3.0
- `wizards` 1.4.1
- `paladins` 1.4.0
- `rogues` 1.2.0
- `archers` 1.3.0
- `archers_expansion` 0.2.6
- `bards_rpg`
- `forcemaster_rpg`
- `death_knights`
- `soulmaster`
- `invoke`
- `runes`
- `sortilege`
- `simplyskills`
- `extraspellattributes`

### Required attribution approach

The mod must use Minecraft’s server-side `DamageSource` / attacker / source chain first, resolving in this order where applicable:

1. direct `ServerPlayerEntity` attacker;
2. `DamageSource.getAttacker()` if it is a player;
3. projectile owner (`ProjectileEntity.getOwner()`), recursively when needed;
4. persistent projectile / spell projectile owner;
5. summon or tameable owner;
6. spell-engine/mod-specific caster metadata/components when the normal chain is absent;
7. source entity display name plus untraceable record if unresolved.

The attribution implementation must be verified against representative attacks from each actual spell/ability family, especially Spell Engine and its dependent RPG Series mods. Do not claim support merely from generic `DamageSource` assumptions.

---

## 5. Technical assessment and recommended architecture

### 5.1 Why RCON/log parsing is insufficient

RCON can query entity state and run commands, but cannot capture every combat event or trace spell ownership. Server logs do not retain enough per-hit data/ownership to rebuild correct history.

This requires a custom **server-side Fabric mod**.

### 5.2 Existing BMD internals

BMD contains these internal classes:

- `DamageMemory`
- `DamageMemory$DamageHistory`
- `CompositeDamageHandler`
- `StagedDamageHandler`
- `ServerGauntletDeathHandler`

`DamageMemory$DamageHistory` stores `amount`, `DamageSource`, and age-at-hit. This proves BMD processes individual damage events, but it is not a general persistent player leaderboard and cannot satisfy the all-entity fallback. Avoid depending on BMD private internals for the core implementation.

### 5.3 Generic post-damage hook requirement

Fabric API’s `ServerLivingEntityEvents.ALLOW_DAMAGE` fires before armor and other mitigation. It reports attempted/pre-mitigation damage, not the actual damage removed from health.

For honest totals, use a narrow mixin around the final server `LivingEntity.damage(DamageSource, float)` flow:

- capture target health before application;
- allow vanilla/modded damage pipeline to finish;
- measure actual positive health reduction after the pipeline;
- record only successful actual damage;
- resolve attribution from the final `DamageSource` chain.

This avoids inflated values from armor, resistance, immunity, boss shields, or cancelled attacks.

Note: BMD bosses can regenerate. A boss contribution total can exceed the boss’s nominal configured health. This is correct: it represents actual damage dealt during the encounter, not net health loss from spawn to death.

### 5.4 Fight-session model

Persist sessions in SQLite, keyed by `boss_entity_uuid`:

```text
boss_entity_uuid
boss_type_id
boss_display_name
spawn_timestamp
spawn_dimension
spawn_position
ended_timestamp nullable
end_reason: death | despawn
```

At boss spawn, create/open a session. At each attributed or untraceable actual-damage event to that UUID, add a contribution row. At death/despawn, close exactly that session and produce the final leaderboard.

Persist open sessions so a server restart does not erase an active boss encounter. On world/server load, reconcile sessions against loaded entity UUIDs. If the entity no longer exists, close the session as `despawn` rather than pretending it was killed.

### 5.5 Permanent all-damage ledger

Retain every raw actual-damage event forever:

```text
id
occurred_at
attacker_player_uuid nullable
attacker_last_known_name nullable
attribution_kind
untraceable_source_name nullable
target_entity_uuid
target_type_id
target_category: player | entity
dimension
actual_damage
boss_session_uuid nullable
```

Maintain aggregate tables at the same time for fast queries, e.g. player + minute bucket + target category. Raw events remain the audit trail; aggregates make `/damage 30` fast across the server lifespan.

Use SQLite in WAL mode and batch inserts/aggregates. Do not run one filesystem transaction per hit.

### 5.6 Suggested command set

Player commands:

```text
/damage <minutes>
/damage <minutes> <player>
```

Admin commands (exact syntax may be refined):

```text
/damageboss add <entity_type_id>
/damageboss remove <entity_type_id>
/damageboss list
/damageboss sessions [active|recent]
```

Commands should validate entity type IDs through the live registry and persist manual additions/removals in the tracker’s config/database.

---

## 6. Presentation requirements

### Completed boss fight

Show player-attributed contributors ordered by actual damage, and separately show untraceable contributions. Suggested output:

```text
[Boss Damage] Nether Gauntlet defeated
1. PlayerA — 534.8 damage (59.4%)
2. PlayerB — 278.1 damage (30.9%)
Untraceable: Dark Mage — 87.1 damage
```

Use the regular Minecraft broadcast path so <BOT_NAME_REDACTED>’s existing Velocity Discord bridge posts it in the Prominence Discord channel too.

### `/damage 30`

Show per-player rows with:

```text
Player | Total | To players | To entities
```

In-game no-player form: private to command sender.

Target-player form: publicly visible.

Discord equivalent: publicly visible in the Prominence channel.

---

## 7. Current implementation/access reference

This section is a read-only audit of the live setup, intended to tell a future implementer exactly where changes would belong and what must **not** be changed accidentally.

### 7.1 Runtime target

| Item | Current value |
|---|---|
| Minecraft | `1.20.1` |
| Loader | Fabric Loader `0.19.3` |
| Fabric installer / launcher | `fabric.jar`, Fabric Installer `1.1.2` |
| Runtime Java | OpenJDK `17.0.20` |
| Required Java major | 17 |
| Fabric API mod | `fabric-api-0.92.11+1.20.1.jar` |
| Installed mod count | 366 jars |
| World size at audit | ~12 GB |

### 7.2 Live backend server paths

```text
Server root:
/data/compose/13/docker/servers/50a6d163-0309-4832-986f-106668768b3d

Server-side mod deployment directory:
.../mods/

Server mod configuration directory:
.../config/

World data:
.../world/

FTB Quests:
.../config/ftbquests/quests/

Pack-level datapacks:
.../datapacks/

World-local datapacks:
.../world/datapacks/

Server launcher:
.../start.sh

Runtime/version selection:
.../variables.txt
```

The server root, `mods/`, `config/`, and `world/` are owned `<USERNAME_REDACTED>:root` and are group-writable/setgid. The service does not need to run as root merely to install a validated mod, but do not change ownership/ACLs as part of this project.

The actual server launcher is a ServerPackCreator-generated Fabric script. It launches `fabric.jar`; Fabric Loader/version configuration comes from the protected `variables.txt` above.

### 7.3 Crafty/container topology

Crafty runs as the host-networked `crafty_container`.

```text
Host: /data/compose/13/docker/servers
Container: /crafty/servers

Host: /data/compose/13/docker/config
Container: /crafty/app/config
```

This backend must be restarted through Crafty, not by killing the Java process or manually invoking `start.sh` while Crafty supervises it.

The backend currently listens on `<INTERNAL_IP_REDACTED>.11:30001`. RCON is currently present at `<INTERNAL_IP_REDACTED>.11:25575`; it belongs to the hours-tracker setup and is not a viable source of per-hit damage events.

### 7.4 Update/deployment protections

Prominence updates are managed by:

```text
/home/<USERNAME_REDACTED>/prominence-updater/
```

The updater contract is:

```text
/home/<USERNAME_REDACTED>/prominence-updater/UPDATE-CONTRACT.md
```

Important updater facts:

- Normal pack application requires zero players, enters maintenance, backs up/stages, restarts via Crafty, performs a health check, then clears maintenance.
- `fabric.jar`, `server.properties`, `variables.txt`, all world data, and named protected paths are immutable under pack updates.
- Current custom user-protected entries include several specific mods, `variables.txt`, `world/`, and `worldnopregen/`.

**Future deployment requirement:** after the damage tracker jar is accepted and installed in `mods/`, protect the jar through the Prominence updater’s Protected Files UI/API. Otherwise a subsequent pack update could remove it. This is an implementation-side effect and requires explicit user approval at that time.

### 7.5 Custom mod/project state

There is currently **no local custom Fabric mod source project**, Gradle wrapper, Maven project, Gradle executable, Maven executable, JDK compiler (`javac`), or Java `jar` utility on this host.

Available:

```text
git: /usr/bin/git
java runtime: /usr/bin/java (Java 17)
```

Unavailable at audit:

```text
javac
jar
gradle
mvn
existing Fabric-Loom project
```

Recommended build approach:

1. Create an isolated repository outside the live server tree, e.g. `/home/<USERNAME_REDACTED>/prominence-damage-tracker/`.
2. Use Fabric Loom configured for Minecraft `1.20.1`, Fabric Loader `0.19.3`, Java 17, and the installed Fabric API compatibility line.
3. Before downloading Gradle, Fabric Loom, mappings, or any dependency, inspect source/provenance/checksums according to the user’s download-safety requirement.
4. Build and unit/integration-test the jar outside the live server tree.
5. Do not copy anything into `mods/` or restart the server until the user explicitly approves a deployment window.

### 7.6 What a future implementation must create

A new server-only Fabric mod should create:

```text
Fabric entrypoint:
- command registration
- lifecycle hooks for entity spawn, death, unload/removal/reload reconciliation

Mixin layer:
- narrow post-damage actual-health-delta capture
- safely captures final damage after mod/vanilla mitigation

Attribution layer:
- direct player, projectile, summon, tameable, spell/effect owner resolution
- explicit untraceable fallback
- adapters validated against installed Spell Engine/RPG mods

Boss registry layer:
- runtime c:bosses tag ingestion
- vanilla seed list
- quest-derived seed list
- persistent operator-managed additions/removals
- parent/child boss-link resolver

Persistence layer:
- SQLite raw events forever
- permanent aggregate tables
- persistent open boss sessions keyed by boss UUID
- migration/schema version management

Command layer:
- player /damage <minutes>
- public targeted /damage <minutes> <player>
- operator-only boss add/remove/list commands

Announcement layer:
- global Minecraft broadcast formatted for VelocityDiscord bridging
```

Suggested mod config/data location after deployment:

```text
.../config/prominence_damage_tracker.json
```

Suggested database location:

```text
.../world/data/prominence_damage_tracker.db
```

Rationale: world data travels with the world backup and makes the permanent-lifetime ledger harder to separate accidentally from server history. The mod must use SQLite WAL safely and include a startup integrity/migration check.

### 7.7 Quest and data sources that must be parsed

Quest definitions are FTB Quest SNBT, not a generated runtime boss registry. Parse/reconcile these files before initial production configuration:

```text
config/ftbquests/quests/chapters/main_story.snbt
config/ftbquests/quests/chapters/elhasturian_era.snbt
config/ftbquests/quests/chapters/the_nether.snbt
config/ftbquests/quests/chapters/to_the_end.snbt
config/ftbquests/quests/chapters/archon.snbt
config/ftbquests/quests/chapters/gear_mariums_soulslike_weaponry.snbt
config/ftbquests/quests/chapters/botania.snbt
config/ftbquests/quests/chapters/deeper_and_darker.snbt
config/ftbquests/quests/chapters/4trophy_collection.snbt
```

Do not assume all quest bosses are present in `c:bosses`; the reconciliation output should produce a reviewable initial allow-list before deployment.

Pack-level datapacks include many spell/combat tuning packs, notably Spell Engine, Spellblade Next, Paladins, Bards, Death Knights, Archers, Soulslike Weaponry, and RPG Series tweaks. These are an additional reason attribution requires a test matrix rather than generic assumptions.

### 7.8 Discord integration current setup

Velocity side:

```text
Velocity root:
/data/compose/13/docker/servers/43ac65de-795f-443f-9cc5-2aecc7447a05

VelocityDiscord jar:
.../plugins/VelocityDiscord-1.9.0.jar

VelocityDiscord config:
.../plugins/discord/config.toml
```

The bridge currently:

- posts normal Minecraft chat to the Prominence Discord channel;
- emits join/leave/proxy messages;
- uses `message_type = "text"`;
- has `show_bot_messages = false`.

The correct strategy for automatic boss results is to emit an ordinary global Minecraft broadcast. VelocityDiscord will relay that to Discord using its existing bot identity, <BOT_NAME_REDACTED>.

<BOT_NAME_REDACTED>’s Discord application has an existing external Interactions Endpoint. It was confirmed reachable by non-mutating HTTP `HEAD`, but its application/source location is **not present on Serpine**. `/damage` slash-command work requires locating the endpoint’s owner/source and adding a verified Discord signature-validation handler there. Do not replace that URL, do not add a competing gateway listener, and do not expose the endpoint URL or token in documentation/logs.

### 7.9 Testing/staging status and access

There is no existing damage-tracker staging mod/project or dedicated test server. The current updater has only pack-file staging; it is not a safe substitute for runtime combat testing.

Before production deployment, create/use an isolated Fabric 1.20.1 test environment with representative versions of:

- Fabric API;
- BMD;
- Spell Engine and dependencies;
- RPG Series classes;
- Soulslike Weaponry;
- any mod whose damage ownership adapter is added.

Run explicit controlled tests for direct, projectile, spell, summon, persistent-effect, TNT/trap, linked-boss-part, boss death/despawn, chunk unload, restart recovery, PvP recipient recording, and raw/aggregate ledger consistency.

### 7.10 Current operational state at audit

- `prominence-updater.service`: active
- `prominence-hours-tracker.service`: active
- `prominence-hours-discord.service`: active
- Minecraft backend listener: active on port 30001
- No changes were made to these services during this damage-tracker implementation audit.

---

## 8. Work still required (do not claim complete)

1. Parse all FTB Quest SNBT files and build an exact quest-boss entity ID inventory.
2. Inspect actual damage source behavior of Spell Engine and every relevant spell/ability/summon family.
3. Decide and implement robust ownership adapters for mod-specific spell effects where vanilla `DamageSource` ownership is insufficient.
4. Create the server-side Fabric mod with mixins, SQLite persistence, boss-session lifecycle, command handling, configuration, and migration/versioning.
5. Create tests:
   - direct melee;
   - arrow/projectile;
   - spell projectile;
   - delayed/lingering effect;
   - summon/tameable damage;
   - unresolved source recording;
   - multiple same-type bosses simultaneously;
   - server restart during fight;
   - death and despawn finalization;
   - `/damage` visibility rules;
   - permanent raw-event and aggregate consistency.
6. Perform controlled live validation on a test boss before production deployment.
7. Per user preference, inspect any downloaded build dependency/tool before download or execution; do not download/install a mod without explicit approval after inspection.

---

## 8. Remaining product decisions

These have not yet been explicitly selected:

1. Exact display/visibility style for automated boss results beyond “global Minecraft + Discord.”
2. Exact syntax and permissions for admin boss-list modification commands.
3. Whether naturally aggressive high-tier entities that are not in `c:bosses` but appear in quests should be automatic boss sessions (recommended: yes, based on parsed quest objective IDs).
4. Whether direct player-vs-player damage should count in `/damage` (current stated report requires a `to players` column, so it should be recorded; whether it is included in all-player total is implied yes but should be confirmed).
5. Whether the no-player `/damage <minutes>` query should have an upper time-window limit for server performance. Raw data is permanent; large windows can be served from aggregates.
