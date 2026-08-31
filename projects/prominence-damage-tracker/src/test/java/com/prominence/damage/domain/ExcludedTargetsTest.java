package com.prominence.damage.domain;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ExcludedTargetsTest {
    @Test void targetDummyIsExcluded() {
        assertTrue(ExcludedTargets.isExcluded("dummmmmmy:target_dummy"));
    }

    @Test void normalMobsAreNotExcluded() {
        assertFalse(ExcludedTargets.isExcluded("minecraft:zombie"));
        assertFalse(ExcludedTargets.isExcluded("minecraft:player"));
        assertFalse(ExcludedTargets.isExcluded("botania:doppleganger"));
    }

    @Test void armorStandsAndSilverfishAreExcluded() {
        assertTrue(ExcludedTargets.isExcluded("minecraft:armor_stand"));
        assertTrue(ExcludedTargets.isExcluded("minecraft:silverfish"));
    }

    @Test void nullIsNotExcluded() {
        assertFalse(ExcludedTargets.isExcluded(null));
    }
}
