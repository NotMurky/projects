package com.prominence.damage.boss;

import static org.junit.jupiter.api.Assertions.*;

import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class BossLinkRegistryTest {
    @Test void directBossTargetResolvesToItself() {
        BossLinkRegistry r = new BossLinkRegistry();
        UUID boss = UUID.randomUUID();
        Set<UUID> active = Set.of(boss);
        assertEquals(boss, r.sessionForTarget(boss, active::contains).orElseThrow());
    }

    @Test void linkedMinionRollsIntoParentSession() {
        BossLinkRegistry r = new BossLinkRegistry();
        UUID boss = UUID.randomUUID(), minion = UUID.randomUUID();
        Set<UUID> active = Set.of(boss);
        r.link(minion, boss);
        assertEquals(boss, r.sessionForTarget(minion, active::contains).orElseThrow());
    }

    @Test void staleLinkDroppedWhenParentSessionClosed() {
        BossLinkRegistry r = new BossLinkRegistry();
        UUID boss = UUID.randomUUID(), minion = UUID.randomUUID();
        Set<UUID> active = new HashSet<>(Set.of(boss));
        r.link(minion, boss);
        active.remove(boss); // boss died
        assertTrue(r.sessionForTarget(minion, active::contains).isEmpty());
        assertFalse(r.isLinked(minion)); // stale link pruned
    }

    @Test void unlinkChildrenOfClearsAllChildren() {
        BossLinkRegistry r = new BossLinkRegistry();
        UUID boss = UUID.randomUUID(), m1 = UUID.randomUUID(), m2 = UUID.randomUUID();
        r.link(m1, boss); r.link(m2, boss);
        assertEquals(2, r.linkCount());
        r.unlinkChildrenOf(boss);
        assertEquals(0, r.linkCount());
    }

    @Test void unlinkedNonBossTargetResolvesEmpty() {
        BossLinkRegistry r = new BossLinkRegistry();
        assertTrue(r.sessionForTarget(UUID.randomUUID(), u -> false).isEmpty());
    }

    @Test void selfLinkIgnored() {
        BossLinkRegistry r = new BossLinkRegistry();
        UUID x = UUID.randomUUID();
        r.link(x, x);
        assertFalse(r.isLinked(x));
    }

    @Test void spawnedAddLinksToBossThenRollsIn() {
        // Simulates the deterministic spawn-during-tick path: a boss spawns a
        // vanilla add (no owner reference), we link it, its damage rolls into the boss.
        BossLinkRegistry r = new BossLinkRegistry();
        UUID gaia = UUID.randomUUID(), witch = UUID.randomUUID();
        Set<UUID> active = Set.of(gaia);
        r.link(witch, gaia); // captured at spawn because gaia was the ticking entity
        assertEquals(gaia, r.sessionForTarget(witch, active::contains).orElseThrow());
    }
}
