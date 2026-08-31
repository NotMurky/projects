package com.prominence.damage.domain;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.LongSupplier;

/**
 * Records provenance for <em>delayed</em> player-caused damage whose runtime
 * {@link net.minecraft.entity.damage.DamageSource} no longer carries the
 * originating player: burning applied by a player, damaging status effects
 * (poison, wither, bleed, decay), lingering spell clouds, primed TNT, and
 * similar. Attribution is recorded at the moment the effect is <em>applied</em>
 * (where the causing player is still known) and consumed later when the
 * anonymous per-tick damage lands on the target.
 *
 * <p>Entries expire so that unrelated environmental damage occurring long after
 * a player-applied effect wears off is never falsely credited. This class holds
 * no Minecraft references and is fully unit-testable. Never guesses "last player
 * to hit": if no live, unexpired record matches, resolution returns empty and the
 * caller must record the hit as untraceable.
 */
public final class ProvenanceTracker {
    /** Provenance categories keyed independently per target so fire and a
     * status effect can coexist without clobbering each other. */
    public static final String FIRE = "fire";
    public static final String EFFECT = "effect";      // damaging status effects applied by a player
    public static final String EXPLOSIVE = "explosive"; // primed TNT etc.
    public static final String AREA_PREFIX = "area:";     // + cloud/aoe id

    private record Record(UUID playerUuid, String playerName, long expiresAtMillis) {}

    // target entity uuid -> category key -> record
    private final Map<UUID, Map<String, Record>> byTarget = new ConcurrentHashMap<>();
    private final LongSupplier clock;

    public ProvenanceTracker(LongSupplier clockMillis) {
        this.clock = clockMillis;
    }

    /**
     * Record that {@code player} is responsible for future {@code category}
     * damage to {@code target} for the next {@code ttlMillis}. A fresh call
     * refreshes the expiry (e.g. reapplying fire), so the most recent applier wins.
     */
    public void record(UUID target, String category, UUID playerUuid, String playerName, long ttlMillis) {
        if (target == null || category == null || playerUuid == null || ttlMillis <= 0) return;
        long expiry = clock.getAsLong() + ttlMillis;
        byTarget.computeIfAbsent(target, k -> new ConcurrentHashMap<>())
                .put(category, new Record(playerUuid, playerName, expiry));
    }

    /** Resolve the player responsible for {@code category} damage to {@code target}, if a live record exists. */
    public Optional<PlayerRef> resolve(UUID target, String category) {
        if (target == null || category == null) return Optional.empty();
        Map<String, Record> m = byTarget.get(target);
        if (m == null) return Optional.empty();
        Record r = m.get(category);
        if (r == null) return Optional.empty();
        if (r.expiresAtMillis() <= clock.getAsLong()) {
            m.remove(category);
            if (m.isEmpty()) byTarget.remove(target);
            return Optional.empty();
        }
        return Optional.of(new PlayerRef(r.playerUuid(), r.playerName()));
    }

    /** Drop every record for a target — call when the entity dies or is removed. */
    public void forget(UUID target) {
        if (target != null) byTarget.remove(target);
    }

    /** Remove all expired records across all targets. Cheap to call periodically. */
    public void purgeExpired() {
        long now = clock.getAsLong();
        byTarget.values().forEach(m -> m.values().removeIf(r -> r.expiresAtMillis() <= now));
        byTarget.entrySet().removeIf(e -> e.getValue().isEmpty());
    }

    /** Effect category key (all damaging status effects share one bucket per target). */
    public static String effect(String effectId) { return EFFECT; }
    /** Area/cloud category key for a source identifier. */
    public static String area(String areaId) { return AREA_PREFIX + areaId; }

    // Visible for tests.
    public int trackedTargets() { return byTarget.size(); }
}
