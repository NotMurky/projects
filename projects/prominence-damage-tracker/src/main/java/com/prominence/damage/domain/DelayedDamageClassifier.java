package com.prominence.damage.domain;

import java.util.Set;

/**
 * Maps a vanilla/modded {@code DamageSource} name to the {@link ProvenanceTracker}
 * category that would hold its deferred player attribution. Only sources whose
 * runtime damage tick carries no usable attacker are classified here; everything
 * that already exposes an attacker/owner is resolved by the live source chain and
 * must NOT be routed through provenance (that would risk stale credit).
 *
 * <p>Pure and unit-testable — no Minecraft references.
 */
public final class DelayedDamageClassifier {
    private DelayedDamageClassifier() {}

    // Vanilla fire tick source names (player Fire Aspect / flame arrows / ignited blocks).
    private static final Set<String> FIRE_SOURCES = Set.of("onFire", "inFire");

    // Source-less status-effect / lingering tick names. Player attribution for
    // these is captured when the effect is APPLIED (setStatusEffect with a source),
    // then consumed here under the single EFFECT bucket.
    private static final Set<String> EFFECT_SOURCES = Set.of(
            "wither",        // Wither status effect
            "magic",         // Poison / instant-harm / generic spell effect ticks
            "indirectMagic", // lingering potion clouds, some spell fields
            "dragonBreath",  // area dragon breath cloud
            "dragon_mist",   // Soulslike Hallowed Dragon Mist (source-less)
            "bleed",         // mod bleed ticks when source-less
            "decay"          // mod decay ticks when source-less
    );

    // Explosion source names whose damage may originate from a player-primed explosive.
    private static final Set<String> EXPLOSIVE_SOURCES = Set.of("explosion", "explosion.player");

    /** True if this source should be attributed via provenance rather than left untraceable. */
    public static boolean isDelayed(String sourceName) {
        return categoryFor(sourceName) != null;
    }

    /**
     * The {@link ProvenanceTracker} category to look up for a given anonymous
     * source name, or {@code null} if the source is not a deferred, attributable
     * category (leave it untraceable).
     */
    public static String categoryFor(String sourceName) {
        if (sourceName == null) return null;
        if (FIRE_SOURCES.contains(sourceName)) return ProvenanceTracker.FIRE;
        if (EXPLOSIVE_SOURCES.contains(sourceName)) return ProvenanceTracker.EXPLOSIVE;
        if (EFFECT_SOURCES.contains(sourceName)) return ProvenanceTracker.EFFECT;
        return null;
    }
}
