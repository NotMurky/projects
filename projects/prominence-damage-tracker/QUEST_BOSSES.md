# Quest boss entity inventory

This is a read-only reconciliation of the live Prominence II Fabric 1.20.1 server's FTB Quests SNBT and installed mod assets. The live server tree was **not modified**.

- Live quest source: `/data/compose/13/docker/servers/50a6d163-0309-4832-986f-106668768b3d/config/ftbquests/quests/chapters/`
- Installed asset source: the same server's `mods/*.jar`
- Additional live cross-check: `config/boss_level_definitions.json5`
- Default output: `src/main/resources/default-bosses.json`
- Confirmed default count: **34 unique entity type IDs**

## Inclusion rule

An ID is in the default file when at least one of these is true:

1. it occurs literally in an FTB Quest `type: "kill"` boss/progression objective;
2. an installed jar supplies it in `data/c/tags/entity_types/bosses.json`;
3. it is one of the required vanilla seeds (`minecraft:wither`, `minecraft:ender_dragon`); or
4. it is a clearly named side/story boss with a literal quest kill entity ID.

A quest's ordinary mob-kill task, item task, icon, image, or spawn egg alone is **not** treated as proof that the entity is a boss. Those uncertain cases are separated below.

## Confirmed quest/story entity IDs not supplied by `c:bosses`

| Entity ID | Quest evidence | Installed-asset reconciliation |
|---|---|---|
| `aquamirae:captain_cornelia` | `main_story.snbt` quest `569B422A5AE03E53`: “Defeat the Ghost of Captain Cornelia”; also a singleton kill in `collectibles.snbt` | `Aquamirae 6.jar`: `entity.aquamirae.captain_cornelia` = “Ghost of Captain Cornelia” |
| `derelict:arachne` | `elhasturian_era.snbt` quest `07F912CCB09E8B1C`: “Defeat Arachne”; description calls Arachne a terrifying boss-arena beast | `derelict-2.1.0.jar`: `entity.derelict.arachne` = “Arachne” |
| `eldritch_end:eye` | `main_story.snbt` quest `0E567E587E669BED`: “Kill The Eldritch Eye” | `Eldritch_End-FABRIC-MC1.20.1-0.3.4.jar`: `entity.eldritch_end.eye` = “The Eldritch Eye” |
| `eldritch_end:the_faceless` | `main_story.snbt` quest `69574BA63A9F05E8`: “Summon and fight against The Faceless One” | Eldritch End language key resolves it as “The Faceless”; also present in live `boss_level_definitions.json5` |
| `prominent:amagul` | `elhasturian_era.snbt` quest `1B7B89009822EDC3`: “Defeat Ama'gul” with explicit boss mechanics in the description | `Prominent-GLOBAL-MC1.20.1-4.0.2.jar`: `entity.prominent.amagul` = “Ama'gul” |
| `sbprom:hasturmagus` | `elhasturian_era.snbt` quest `2D24C45915E27222`: “Defeat the Resurrected Magus, Gu'mas” | Exact ID is also in live `boss_level_definitions.json5` and embedded in Prominent's `BossLevels` / `GumasEncounterManager` classes; no `en_us` entity key was found |
| `spellbladenext:magus` | `main_story.snbt` quest `3A8C4B633BAF1EFF`: “Defeat the Archmage Magus” | `spellbladenext-2.3.0+1.20.1.jar`: `entity.spellbladenext.magus` = “Magus”; also in live boss-level config |

Important collision: `eldritch_end:eye` is the literal Eldritch Eye quest target. `adventurez:the_eye` is a different installed entity supplied by AdventureZ's `c:bosses` tag. Both are retained.

## Exact installed `c:bosses` inventory

Seven installed jars supply 29 tag entries, deduplicating to **27 IDs**. Every entry below is in the default file.

### AdventureZ — `adventurez-1.4.20.jar`

- `adventurez:blackstone_golem` — Blackstone Golem
- `adventurez:the_eye` — The Eye
- `adventurez:void_shadow` — Void Shadow

### Archon Renewed — `Archon-1.1.5.jar`

- `minecraft:wither`
- `minecraft:ender_dragon`
- `minecraft:elder_guardian`
- `minecraft:warden`
- `archon:tar` — Tar / Earth Elemental quest target
- `archon:ayla` — Ayla / Sky Elemental quest target
- `archon:leven` — Leven / Water Elemental quest target
- `archon:inigo` — Inigo / Fire Elemental quest target
- `archon:null` — Null

### Bosses of Mass Destruction — `BOMD-1.7.5-1.20.1.jar`

- `bosses_of_mass_destruction:lich` — Night Lich
- `bosses_of_mass_destruction:obsidilith` — Obsidilith
- `bosses_of_mass_destruction:gauntlet` — Nether Gauntlet
- `bosses_of_mass_destruction:void_blossom` — Void Blossom

### Botania — `Botania-1.20.1-453-FABRIC.jar`

- `botania:doppleganger` — Guardian of Gaia (the registry path is spelled `doppleganger`)

The Botania chapter describes the Gaia fight through item/advancement objectives rather than a literal entity kill task; the installed boss tag supplies the exact entity ID.

### Minecells — `minecells-2.0.0.jar`

- `minecells:conjunctivius` — Conjunctivius

### Marium's Soulslike Weaponry — `soulslike-weaponry-1.3.1-1.20.1-fabric.jar`

- `minecraft:ender_dragon`
- `minecraft:wither`
- `soulsweapons:accursed_lord_boss` — The Decaying King
- `soulsweapons:draugr_boss` — **Old Champion's Remains**
- `soulsweapons:night_shade` — Frenzied Shade
- `soulsweapons:returning_knight` — Returning Knight
- `soulsweapons:chaos_monarch` — Monarch of Chaos
- `soulsweapons:moonknight` — Fallen Icon
- `soulsweapons:day_stalker` — Day Stalker
- `soulsweapons:night_prowler` — Night Prowler

Old Champion is exact, not inferred: `main_story.snbt` quest `759AA6DD39277704` has kill entity `soulsweapons:draugr_boss`, title “The Remains of an Old Champion,” and the jar language value “Old Champion's Remains.”

### The Bumblezone — `the_bumblezone-7.9.10+1.20.1-fabric.jar`

- `the_bumblezone:cosmic_crystal_entity` — Cosmic Crystal Entity

## Vanilla seeds

These are explicitly seeded even though both also occur in installed `c:bosses` files:

- `minecraft:ender_dragon` — direct `main_story.snbt` kill target (`48AADA398DC4E940`)
- `minecraft:wither` — required vanilla coverage; `to_the_end.snbt` also identifies the Wither as the source of `endrem:wither_eye`

`minecraft:elder_guardian` and `minecraft:warden` are included because the installed Archon boss tag lists them. The Warden additionally has an explicit “Bossfight” kill quest in `deeper_and_darker.snbt`.

## Other quest kill IDs requiring manual review

These IDs are real literal kill-task targets, but the quest data does not unambiguously classify them as bosses and no installed `c:bosses` tag confirms them. They are deliberately **not** in the 34-ID default list.

Likely side boss/miniboss candidates to review first:

- `aquamirae:maze_mother` — singleton “Terrors of the Ice Maze” target; same quest also requires ordinary `aquamirae:anglerfish`
- `adventurez:blaze_guardian` — singleton Blaze Guardian target
- `adventurez:necromancer` — singleton Nether Fortress target
- `adventurez:soul_reaper` — singleton Soul Reaper target
- `deeperdarker:stalker` — singleton rare Ancient Vase target
- `mutantmonsters:mutant_enderman` — singleton “Kill the Mutant” target
- `soulsweapons:evil_forlorn`, `soulsweapons:withered_demon` — singleton elite Soulslike targets, but not in that mod's boss tag

Other non-default kill-task IDs (ordinary/mass objectives or supporting entities):

- `ad_astra:corrupted_lunarian`, `ad_astra:glacian_ram`, `ad_astra:martian_raptor`, `ad_astra:mogler`, `ad_astra:pygro`, `ad_astra:star_crawler`
- `aquamirae:anglerfish`
- `betterend:end_slime`, `betterend:shadow_walker`, `betternether:naga`
- `deeperdarker:shattered`, `deeperdarker:shriek_worm`
- `eldritch_end:aberration`, `eldritch_end:dendler`, `eldritch_end:ominous_eye`
- `minecraft:blaze`, `minecraft:enderman`, `minecraft:magma_cube`, `minecraft:phantom`, `minecraft:piglin`, `minecraft:piglin_brute`, `minecraft:shulker`, `minecraft:wither_skeleton`
- `soulsweapons:dark_sorcerer`, `soulsweapons:remnant`

The Soulslike “Fallen Puppet” quest combines `soulsweapons:remnant`, `soulsweapons:dark_sorcerer`, and `soulsweapons:returning_knight`; only `returning_knight` is confirmed by the installed boss tag.

## Spawn egg and item clues (not promoted by themselves)

Eight `_spawn_egg`-looking resource IDs appear across quest SNBT:

- `artifacts:mimic_spawn_egg` → installed entity `artifacts:mimic`
- `eldritch_end:aberration_spawn_egg` → installed entity `eldritch_end:aberration`
- `minecraft:bat_spawn_egg` → vanilla bat
- `prominent:dwarf_spawn_egg` → installed entity `prominent:dwarf`
- `prominent:serkonid_spawn_egg` → installed entity `prominent:serkonid`
- `prominent:skellak_spawn_egg` → installed entity `prominent:skellak`; quest text says “New content coming by v5.0,” so this is not an active kill objective
- `the_bumblezone:bee_queen_spawn_egg` → installed entity `the_bumblezone:bee_queen`; used as a Bee House quest icon
- `prominent:item/skellak_spawn_egg` → a resource-path-shaped reference, not a valid inferred entity ID

None was added solely from the egg/icon reference. Likewise, boss drops such as Lord Souls, Obsidian Heart, Wither Eye, Guardian Eye, Gaia items, and trophies were used as corroborating context, not as substitutes for a registry entity ID.

## Complete default IDs

The machine-readable file is a sorted JSON array of these 34 IDs:

- `adventurez:blackstone_golem`
- `adventurez:the_eye`
- `adventurez:void_shadow`
- `aquamirae:captain_cornelia`
- `archon:ayla`
- `archon:inigo`
- `archon:leven`
- `archon:null`
- `archon:tar`
- `bosses_of_mass_destruction:gauntlet`
- `bosses_of_mass_destruction:lich`
- `bosses_of_mass_destruction:obsidilith`
- `bosses_of_mass_destruction:void_blossom`
- `botania:doppleganger`
- `derelict:arachne`
- `eldritch_end:eye`
- `eldritch_end:the_faceless`
- `minecells:conjunctivius`
- `minecraft:elder_guardian`
- `minecraft:ender_dragon`
- `minecraft:warden`
- `minecraft:wither`
- `prominent:amagul`
- `sbprom:hasturmagus`
- `soulsweapons:accursed_lord_boss`
- `soulsweapons:chaos_monarch`
- `soulsweapons:day_stalker`
- `soulsweapons:draugr_boss`
- `soulsweapons:moonknight`
- `soulsweapons:night_prowler`
- `soulsweapons:night_shade`
- `soulsweapons:returning_knight`
- `spellbladenext:magus`
- `the_bumblezone:cosmic_crystal_entity`

## Runtime note

At runtime, the tracker should still ingest the live `c:bosses` entity-type tag and layer operator additions/removals over these seeds. This file is the reviewed initial allow-list, not a replacement for runtime tag lookup.
