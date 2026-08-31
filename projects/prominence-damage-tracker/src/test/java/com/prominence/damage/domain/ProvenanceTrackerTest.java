package com.prominence.damage.domain;

import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;

class ProvenanceTrackerTest {
    @Test void resolvesLivePlayerRecordAndExpires() {
        AtomicLong now = new AtomicLong(1_000);
        ProvenanceTracker t = new ProvenanceTracker(now::get);
        UUID target = UUID.randomUUID(), player = UUID.randomUUID();
        t.record(target, ProvenanceTracker.FIRE, player, "Murky", 5_000);
        assertEquals(player, t.resolve(target, ProvenanceTracker.FIRE).orElseThrow().uuid());
        now.set(6_500); // past expiry (1000 + 5000)
        assertTrue(t.resolve(target, ProvenanceTracker.FIRE).isEmpty());
        assertEquals(0, t.trackedTargets()); // lazily purged on miss
    }

    @Test void categoriesAreIndependentPerTarget() {
        AtomicLong now = new AtomicLong(0);
        ProvenanceTracker t = new ProvenanceTracker(now::get);
        UUID target = UUID.randomUUID(), a = UUID.randomUUID(), b = UUID.randomUUID();
        t.record(target, ProvenanceTracker.FIRE, a, "A", 10_000);
        t.record(target, ProvenanceTracker.EFFECT, b, "B", 10_000);
        assertEquals(a, t.resolve(target, ProvenanceTracker.FIRE).orElseThrow().uuid());
        assertEquals(b, t.resolve(target, ProvenanceTracker.EFFECT).orElseThrow().uuid());
    }

    @Test void mostRecentApplierWins() {
        AtomicLong now = new AtomicLong(0);
        ProvenanceTracker t = new ProvenanceTracker(now::get);
        UUID target = UUID.randomUUID(), a = UUID.randomUUID(), b = UUID.randomUUID();
        t.record(target, ProvenanceTracker.EFFECT, a, "A", 10_000);
        now.set(100);
        t.record(target, ProvenanceTracker.EFFECT, b, "B", 10_000);
        assertEquals(b, t.resolve(target, ProvenanceTracker.EFFECT).orElseThrow().uuid());
    }

    @Test void forgetDropsAllCategories() {
        ProvenanceTracker t = new ProvenanceTracker(() -> 0L);
        UUID target = UUID.randomUUID(), p = UUID.randomUUID();
        t.record(target, ProvenanceTracker.FIRE, p, "P", 10_000);
        t.forget(target);
        assertTrue(t.resolve(target, ProvenanceTracker.FIRE).isEmpty());
    }

    @Test void neverGuessesWithoutRecord() {
        ProvenanceTracker t = new ProvenanceTracker(() -> 0L);
        assertTrue(t.resolve(UUID.randomUUID(), ProvenanceTracker.EFFECT).isEmpty());
    }
}
