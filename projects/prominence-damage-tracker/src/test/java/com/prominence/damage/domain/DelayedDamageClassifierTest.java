package com.prominence.damage.domain;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class DelayedDamageClassifierTest {
    @Test void fireSourcesMapToFireCategory() {
        assertEquals(ProvenanceTracker.FIRE, DelayedDamageClassifier.categoryFor("onFire"));
        assertEquals(ProvenanceTracker.FIRE, DelayedDamageClassifier.categoryFor("inFire"));
    }

    @Test void effectSourcesMapToEffectCategory() {
        assertEquals(ProvenanceTracker.EFFECT, DelayedDamageClassifier.categoryFor("wither"));
        assertEquals(ProvenanceTracker.EFFECT, DelayedDamageClassifier.categoryFor("magic"));
        assertEquals(ProvenanceTracker.EFFECT, DelayedDamageClassifier.categoryFor("indirectMagic"));
        assertEquals(ProvenanceTracker.EFFECT, DelayedDamageClassifier.categoryFor("dragon_mist"));
    }

    @Test void explosionsMapToExplosiveCategory() {
        assertEquals(ProvenanceTracker.EXPLOSIVE, DelayedDamageClassifier.categoryFor("explosion"));
        assertEquals(ProvenanceTracker.EXPLOSIVE, DelayedDamageClassifier.categoryFor("explosion.player"));
    }

    @Test void ordinaryDirectSourcesAreNotDeferred() {
        assertNull(DelayedDamageClassifier.categoryFor("player"));
        assertNull(DelayedDamageClassifier.categoryFor("arrow"));
        assertNull(DelayedDamageClassifier.categoryFor("fall"));
        assertNull(DelayedDamageClassifier.categoryFor("cactus"));
        assertNull(DelayedDamageClassifier.categoryFor(null));
        assertFalse(DelayedDamageClassifier.isDelayed("fall"));
        assertTrue(DelayedDamageClassifier.isDelayed("onFire"));
    }
}
