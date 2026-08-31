package com.prominence.damage.fabric;

import com.prominence.damage.boss.BossLinkRegistry;
import com.prominence.damage.boss.BossRegistry;
import com.prominence.damage.boss.DefaultBossIds;
import com.prominence.damage.domain.*;
import com.prominence.damage.storage.SqliteDamageRepository;
import net.fabricmc.api.DedicatedServerModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerEntityEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.event.player.AttackEntityCallback;
import net.minecraft.entity.Entity;
import net.minecraft.entity.LivingEntity;
import net.minecraft.entity.Ownable;
import net.minecraft.entity.TntEntity;
import net.minecraft.entity.projectile.ProjectileEntity;
import net.minecraft.entity.damage.DamageSource;
import net.minecraft.entity.mob.MobEntity;
import net.minecraft.entity.passive.TameableEntity;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.registry.Registries;
import net.minecraft.server.MinecraftServer;
import net.minecraft.util.Identifier;
import net.minecraft.util.math.Vec3d;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.SQLException;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

public final class ProminenceDamageMod implements DedicatedServerModInitializer {
    public static final String MOD_ID = "prominence_damage";
    private static final Logger LOG = LoggerFactory.getLogger(MOD_ID);
    private static ProminenceDamageMod INSTANCE;

    private SqliteDamageRepository repository;
    private BossRegistry bossRegistry;
    private final Map<UUID, BossSession> activeSessions = new ConcurrentHashMap<>();
    // boss uuid -> contributor uuid -> total damage
    private final Map<UUID, Map<UUID, Double>> sessionContributions = new ConcurrentHashMap<>();
    private final Map<UUID, String> uuidToName = new ConcurrentHashMap<>();
    private final AttributionResolver resolver = new AttributionResolver();
    private final ProvenanceTracker provenance = new ProvenanceTracker(System::currentTimeMillis);
    private final BossLinkRegistry bossLinks = new BossLinkRegistry();
    private MinecraftServer server;
    private long tickCounter;

    @Override
    public void onInitializeServer() {
        INSTANCE = this;
        ServerLifecycleEvents.SERVER_STARTING.register(this::onServerStarting);
        ServerLifecycleEvents.SERVER_STOPPING.register(this::onServerStopping);
        ServerEntityEvents.ENTITY_LOAD.register(this::onEntityLoad);
        ServerEntityEvents.ENTITY_UNLOAD.register(this::onEntityUnload);
        ServerTickEvents.END_SERVER_TICK.register(this::onServerTick);
        AttackEntityCallback.EVENT.register((player, world, hand, entity, hit) -> net.minecraft.util.ActionResult.PASS);
        DamageCommand.register();
        DamageBossCommand.register();
        HoursCommand.register();
    }

    private void onServerStarting(MinecraftServer s) {
        this.server = s;
        Path runDir = s.getRunDirectory().toPath();
        try {
            Path dir = runDir.resolve("prominence-damage");
            Files.createDirectories(dir);
            this.repository = new SqliteDamageRepository(dir.resolve("damage.db"));
        } catch (Exception e) {
            LOG.error("Failed to initialize damage repository", e);
            return;
        }
        // Load persisted operator boss overrides so manual add/remove survives restarts.
        Path overridesFile = runDir.resolve("config/prominence-damage/overrides.properties");
        DamageBossCommand.Overrides overrides = DamageBossCommand.loadOverrides(overridesFile);
        DamageBossCommand.initFrom(overridesFile, overrides);

        Set<String> tagged = new HashSet<>();
        try {
            var tag = net.minecraft.registry.tag.TagKey.of(Registries.ENTITY_TYPE.getKey(), new Identifier("c", "bosses"));
            Registries.ENTITY_TYPE.iterateEntries(tag).forEach(e -> tagged.add(Registries.ENTITY_TYPE.getId(e.value()).toString()));
        } catch (Exception e) {
            LOG.warn("Could not read c:bosses tag: {}", e.toString());
        }
        this.bossRegistry = new BossRegistry(DefaultBossIds.ALL, tagged, overrides.additions(), overrides.removals());
        try {
            for (BossSession session : repository.activeBossSessions()) {
                UUID id = session.bossEntityUuid();
                activeSessions.put(id, session);
                Map<UUID, Double> restored = new ConcurrentHashMap<>(repository.contributionsForSession(id));
                sessionContributions.put(id, restored);
                // Restore contributor display names so pre-restart players aren't
                // rendered as raw UUID prefixes in the final boss report.
                uuidToName.putAll(repository.contributorNamesForSession(id));
            }
        } catch (SQLException e) {
            LOG.warn("Could not restore boss sessions: {}", e.toString());
        }
        LOG.info("Prominence damage tracker ready ({} bosses tracked, {} open sessions)",
                bossRegistry.all().size(), activeSessions.size());
    }

    private void onServerStopping(MinecraftServer s) {
        try { if (repository != null) repository.close(); }
        catch (SQLException e) { LOG.warn("Repository close failed: {}", e.toString()); }
    }

    private void onServerTick(MinecraftServer s) {
        if (++tickCounter % 100 != 0) return;
        try { if (repository != null) repository.flush(); }
        catch (SQLException e) { LOG.warn("Flush failed: {}", e.toString()); }
        provenance.purgeExpired();
    }

    private void onEntityLoad(Entity entity, net.minecraft.server.world.ServerWorld world) {
        if (!(entity instanceof LivingEntity living) || entity instanceof PlayerEntity) return;
        String id = Registries.ENTITY_TYPE.getId(living.getType()).toString();
        // Boss-linked entity discovery: if this entity's owner chain leads to an
        // active boss, roll its damage into that boss session rather than tracking
        // it separately. Verified by ownership only — never by proximity.
        UUID linkedParent = resolveBossParent(living);
        if (linkedParent != null) bossLinks.link(living.getUuid(), linkedParent);

        if (bossRegistry == null || !bossRegistry.isBoss(id)) return;
        UUID bossId = living.getUuid();
        if (activeSessions.containsKey(bossId)) return;
        Vec3d p = living.getPos();
        String pos = String.format(Locale.ROOT, "%.1f,%.1f,%.1f", p.x, p.y, p.z);
        BossSession session = new BossSession(bossId, id, living.getDisplayName().getString(),
                Instant.now(), world.getRegistryKey().getValue().toString(), pos, null, null);
        activeSessions.put(bossId, session);
        sessionContributions.put(bossId, new ConcurrentHashMap<>());
        try { repository.openBossSession(session); }
        catch (SQLException e) { LOG.warn("openBossSession failed: {}", e.toString()); }
    }

    /** Resolve the active boss session an owned entity belongs to, following its
     * owner chain. Returns null when no owner resolves to an active boss. */
    private UUID resolveBossParent(Entity entity) {
        int depth = 0;
        Entity cur = entity;
        Set<UUID> seen = new HashSet<>();
        while (cur != null && depth++ < 8 && seen.add(cur.getUuid())) {
            Entity owner = null;
            if (cur instanceof Ownable ownable) owner = ownable.getOwner();
            else if (cur instanceof ProjectileEntity proj) owner = proj.getOwner();
            if (owner == null) owner = ReflectiveOwnerResolver.resolve(cur); // modded summons (e.g. Botania pixie summoner)
            if (owner == null) break;
            if (activeSessions.containsKey(owner.getUuid())) return owner.getUuid();
            cur = owner;
        }
        return null;
    }

    private void onEntityUnload(Entity entity, net.minecraft.server.world.ServerWorld world) {
        if (!(entity instanceof LivingEntity living)) return;
        UUID bossId = living.getUuid();
        provenance.forget(bossId);
        bossLinks.unlink(bossId);
        BossSession session = activeSessions.get(bossId);
        if (session == null) return;
        Entity.RemovalReason reason = living.getRemovalReason();
        // Only end the session on a genuine death or discard. Chunk/dimension unloads
        // keep the session open so a boss fight survives players leaving the area or a restart.
        if (reason == Entity.RemovalReason.KILLED) {
            endSession(bossId, "death");
        } else if (reason == Entity.RemovalReason.DISCARDED) {
            endSession(bossId, "despawn");
        }
        // UNLOADED_TO_CHUNK / UNLOADED_WITH_PLAYER / CHANGED_DIMENSION: leave session active.
    }

    private void endSession(UUID bossId, String reason) {
        BossSession session = activeSessions.remove(bossId);
        Map<UUID, Double> contribs = sessionContributions.remove(bossId);
        bossLinks.unlinkChildrenOf(bossId);
        if (session == null || repository == null) return;
        // Persist the closure and COMMIT before announcing, so we never broadcast a
        // result that a crash could leave uncommitted.
        double unattributed = 0.0;
        try {
            repository.closeBossSession(bossId, Instant.now(), reason);
            repository.flush();
            unattributed = repository.unattributedForSession(bossId);
        } catch (SQLException e) {
            LOG.warn("closeBossSession/flush failed: {}", e.toString());
        }
        boolean hasPlayerContributor = contribs != null && !contribs.isEmpty();
        // On despawn, only announce when at least one player actually contributed.
        // Untraceable damage alone never triggers a despawn announcement.
        if (reason.equals("despawn") && !hasPlayerContributor) return;
        broadcastBossEnd(session, reason, contribs, unattributed);
    }

    private void broadcastBossEnd(BossSession session, String reason, Map<UUID, Double> contribs, double unattributed) {
        if (server == null || contribs == null) return;
        java.util.function.DoubleFunction<String> hearts = com.prominence.damage.domain.HeartFormat::hearts;

        List<Map.Entry<UUID, Double>> ranked = new ArrayList<>(contribs.entrySet());
        ranked.sort(Map.Entry.<UUID, Double>comparingByValue().reversed());
        double attributed = ranked.stream().mapToDouble(Map.Entry::getValue).sum();
        double grandTotal = attributed + Math.max(0.0, unattributed);

        StringBuilder sb = new StringBuilder();
        sb.append("§8§m                                        §r\n");
        if (reason.equals("death")) {
            sb.append("§6§l☠ ").append(session.bossDisplayName()).append(" defeated!§r\n");
        } else {
            sb.append("§e§l⚠ ").append(session.bossDisplayName()).append(" despawned§r §7(attributed damage)§r\n");
        }
        if (grandTotal > 0) {
            sb.append("§7Total damage: §f").append(hearts.apply(grandTotal)).append("§r\n");
        }
        if (ranked.isEmpty()) {
            sb.append("§7No player damage was recorded.\n");
        } else {
            sb.append("§7Damage by player:§r\n");
            int rank = 1;
            for (Map.Entry<UUID, Double> e : ranked) {
                String name = uuidToName.getOrDefault(e.getKey(), e.getKey().toString().substring(0, 8));
                double dmg = e.getValue();
                double pct = grandTotal > 0 ? (dmg / grandTotal) * 100.0 : 0.0;
                String medal = switch (rank) { case 1 -> "§e①"; case 2 -> "§7②"; case 3 -> "§c③"; default -> "§8" + rank + "."; };
                sb.append(String.format(Locale.ROOT, "  %s §b%s§r — §a%s§r §7(%.0f%%)§r\n",
                        medal, name, hearts.apply(dmg), pct));
                rank++;
            }
        }
        // Only show the unaccounted line when there actually is unattributed damage.
        if (unattributed > 0.0001) {
            double pct = grandTotal > 0 ? (unattributed / grandTotal) * 100.0 : 0.0;
            sb.append(String.format(Locale.ROOT, "  §8✦ §7unattributed — %s (%.0f%%)§r\n",
                    hearts.apply(unattributed), pct));
        }
        sb.append("§8§m                                        §r");
        server.getPlayerManager().broadcast(net.minecraft.text.Text.literal(sb.toString()), false);
    }

    /** Called by the effect mixin when a damaging status effect is applied with a known source. */
    public static void onEffectApplied(LivingEntity target, Entity source, long ttlMillis) {
        if (INSTANCE == null) return;
        INSTANCE.recordEffectProvenance(target, source, ttlMillis);
    }

    private void recordEffectProvenance(LivingEntity target, Entity source, long ttlMillis) {
        PlayerRef ref = resolveOwningPlayer(source);
        if (ref == null) return;
        provenance.record(target.getUuid(), ProvenanceTracker.EFFECT, ref.uuid(), ref.name(), ttlMillis);
    }

    public static void onActualDamage(LivingEntity target, DamageSource source, float actual) {
        if (INSTANCE == null || INSTANCE.repository == null) return;
        INSTANCE.record(target, source, actual);
    }

    /**
     * Called when a boss (or any entity currently mid-tick) spawns another entity.
     * If the spawning entity is a tracked, active boss session, the newborn is
     * registered as a linked child so its damage rolls into that boss's fight.
     * Deterministic: we know the parent because we captured the entity the server
     * is ticking, not by proximity.
     */
    public static void onEntitySpawnedDuringTick(net.minecraft.entity.Entity spawner, net.minecraft.entity.Entity spawned) {
        if (INSTANCE == null || spawner == null || spawned == null) return;
        if (spawner == spawned) return;
        if (!INSTANCE.activeSessions.containsKey(spawner.getUuid())) return;
        INSTANCE.bossLinks.link(spawned.getUuid(), spawner.getUuid());
    }

    private void record(LivingEntity target, DamageSource source, float actual) {
        String targetType = Registries.ENTITY_TYPE.getId(target.getType()).toString();
        // Damage to training/target dummies is never tracked.
        if (com.prominence.damage.domain.ExcludedTargets.isExcluded(targetType)) return;
        UUID targetUuid = target.getUuid();

        // Live source-chain attribution first (direct, projectile owner, tameable, recursive).
        SourceNode node = buildSourceNode(source);
        Attribution attribution = resolver.resolve(node);

        // Capture fire/explosive provenance at the moment it's caused by a player,
        // so later anonymous ticks resolve. (Effects are captured in the effect mixin.)
        captureDelayedProvenance(target, source);

        // If the live chain failed, try deferred provenance for known delayed sources.
        if (attribution.kind() == Attribution.Kind.UNTRACEABLE) {
            String category = DelayedDamageClassifier.categoryFor(source.getName());
            if (category != null) {
                Optional<PlayerRef> deferred = provenance.resolve(targetUuid, category);
                if (deferred.isPresent()) {
                    PlayerRef ref = deferred.get();
                    attribution = new Attribution(ref.uuid(), ref.name(), Attribution.Kind.OWNER_CHAIN, source.getName());
                }
            }
        }

        TargetCategory cat = target instanceof PlayerEntity ? TargetCategory.PLAYER : TargetCategory.ENTITY;
        String targetName = target instanceof PlayerEntity ? target.getName().getString() : null;
        // Boss session: the target itself, or its linked boss parent (minions/parts/phases).
        // Minions often have their owner set AFTER entity-load, so resolve the owner
        // chain lazily here and record the link the first time we see attributable damage.
        if (!activeSessions.containsKey(targetUuid) && !bossLinks.isLinked(targetUuid)) {
            UUID lateParent = resolveBossParent(target);
            if (lateParent != null) bossLinks.link(targetUuid, lateParent);
        }
        UUID bossSession = bossLinks.sessionForTarget(targetUuid, activeSessions::containsKey).orElse(null);
        String dim = target.getWorld().getRegistryKey().getValue().toString();
        DamageEvent event = new DamageEvent(Instant.now(),
                attribution.playerUuid(), attribution.playerName(),
                attribution.kind().name(),
                attribution.kind() == Attribution.Kind.UNTRACEABLE ? attribution.sourceName() : null,
                targetUuid, targetName, targetType, cat, dim, actual, bossSession,
                source.getName());
        try { repository.record(event); }
        catch (SQLException e) { LOG.warn("record failed: {}", e.toString()); return; }
        if (attribution.playerUuid() != null) {
            uuidToName.put(attribution.playerUuid(), attribution.playerName());
        }
        if (bossSession != null && attribution.playerUuid() != null) {
            sessionContributions.computeIfAbsent(bossSession, k -> new ConcurrentHashMap<>())
                    .merge(attribution.playerUuid(), (double) actual, Double::sum);
        }
    }

    /** When a hit is directly caused by a player, remember them as responsible for
     * subsequent fire/explosion damage to the same target. */
    private void captureDelayedProvenance(LivingEntity target, DamageSource source) {
        PlayerRef player = resolveOwningPlayer(source.getAttacker());
        if (player == null) player = resolveOwningPlayer(source.getSource());
        if (player == null) return;
        UUID t = target.getUuid();
        // If the target is currently on fire, or this hit is a fire/explosive source,
        // credit the causing player for the burning window / explosion.
        if (target.isOnFire() || DelayedDamageClassifier.categoryFor(source.getName()) != null) {
            provenance.record(t, ProvenanceTracker.FIRE, player.uuid(), player.name(), 12000L);
        }
        // Primed TNT owned by a player: attribute its explosion.
        Entity direct = source.getSource();
        if (direct instanceof TntEntity tnt && tnt.getOwner() instanceof PlayerEntity) {
            provenance.record(t, ProvenanceTracker.EXPLOSIVE, player.uuid(), player.name(), 8000L);
        }
    }

    /** Resolve an entity to the player responsible for it, following owner chains
     * (projectiles, tameables, spell clouds, generic Ownable, TNT, and modded
     * summons with a private owner field). Null if none. */
    private PlayerRef resolveOwningPlayer(Entity entity) {
        int depth = 0;
        Entity cur = entity;
        Set<UUID> seen = new HashSet<>();
        while (cur != null && depth++ < 12 && seen.add(cur.getUuid())) {
            if (cur instanceof PlayerEntity p) return new PlayerRef(p.getUuid(), p.getName().getString());
            Entity next = null;
            if (cur instanceof Ownable ownable) next = ownable.getOwner();
            else if (cur instanceof ProjectileEntity proj) next = proj.getOwner();
            else if (cur instanceof TameableEntity tame) next = tame.getOwner();
            else if (cur instanceof TntEntity tnt) next = tnt.getOwner();
            if (next == null) next = ReflectiveOwnerResolver.resolve(cur); // modded summons
            if (next == null || next == cur) break;
            cur = next;
        }
        return null;
    }

    private SourceNode buildSourceNode(DamageSource source) {
        Entity attacker = source.getAttacker();
        Entity direct = source.getSource();
        String name = source.getName();
        if (attacker instanceof PlayerEntity p) {
            return SourceNode.player(p.getUuid(), p.getName().getString());
        }
        if (direct instanceof PlayerEntity p) {
            return SourceNode.player(p.getUuid(), p.getName().getString());
        }
        // Recursive owner-chain resolution covering projectiles, tameables, spell
        // clouds (Ownable), TNT, and nested summons.
        PlayerRef owner = resolveOwningPlayer(direct);
        if (owner == null) owner = resolveOwningPlayer(attacker);
        if (owner != null) return SourceNode.owned(name, SourceNode.player(owner.uuid(), owner.name()));
        return SourceNode.unowned(name == null ? "unknown" : name);
    }

    public static SqliteDamageRepository repository() { return INSTANCE == null ? null : INSTANCE.repository; }
    public static BossRegistry bossRegistry() { return INSTANCE == null ? null : INSTANCE.bossRegistry; }
    public static void setBossRegistry(BossRegistry r) { if (INSTANCE != null) INSTANCE.bossRegistry = r; }
    public static Map<UUID, BossSession> activeSessions() { return INSTANCE == null ? Map.of() : INSTANCE.activeSessions; }
}
