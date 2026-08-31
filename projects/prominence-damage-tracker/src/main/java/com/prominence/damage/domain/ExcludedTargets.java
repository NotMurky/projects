package com.prominence.damage.domain;

import java.util.Set;

/**
 * Entity type IDs whose damage must NOT be tracked at all — training/target
 * dummies and similar practice entities. Damage dealt to these is dropped
 * before it reaches the ledger, minute aggregates, or boss sessions.
 */
public final class ExcludedTargets {
    private ExcludedTargets() {}

    private static final Set<String> EXCLUDED = Set.of(
        "dummmmmmy:target_dummy", // MmmMmmMmmMmm target dummy — players hit it for practice
        "minecraft:armor_stand",  // decorative / practice stands, not real combat
        "minecraft:silverfish"    // infest-spam mobs, excluded by request
    );

    public static boolean isExcluded(String entityTypeId) {
        return entityTypeId != null && EXCLUDED.contains(entityTypeId);
    }
}
