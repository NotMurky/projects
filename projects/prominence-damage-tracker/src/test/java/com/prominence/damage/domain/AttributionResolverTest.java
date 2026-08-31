package com.prominence.damage.domain;

import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import org.junit.jupiter.api.Test;

class AttributionResolverTest {
    @Test void followsOwnershipChainToPlayerWithoutGuessing() {
        UUID player = UUID.randomUUID();
        SourceNode root = SourceNode.owned("spell projectile", SourceNode.owned("summon", SourceNode.player(player, "Murky")));
        Attribution result = new AttributionResolver().resolve(root);
        assertEquals(player, result.playerUuid());
        assertEquals("Murky", result.playerName());
        assertEquals(Attribution.Kind.OWNER_CHAIN, result.kind());
    }

    @Test void unresolvedSourceRetainsDisplayName() {
        Attribution result = new AttributionResolver().resolve(SourceNode.unowned("Dark Mage"));
        assertNull(result.playerUuid());
        assertEquals("Dark Mage", result.sourceName());
        assertEquals(Attribution.Kind.UNTRACEABLE, result.kind());
    }

    @Test void ownershipCyclesRemainUntraceable() {
        SourceNode cyclic = SourceNode.cyclic("looping effect");
        Attribution result = new AttributionResolver().resolve(cyclic);
        assertNull(result.playerUuid());
        assertEquals(Attribution.Kind.UNTRACEABLE, result.kind());
    }
}
