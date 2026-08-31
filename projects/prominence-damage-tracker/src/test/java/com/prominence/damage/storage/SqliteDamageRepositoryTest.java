package com.prominence.damage.storage;

import static org.junit.jupiter.api.Assertions.*;

import com.prominence.damage.domain.*;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SqliteDamageRepositoryTest {
    @TempDir Path temp;

    @Test void rawLedgerAggregatesAttackerTotalsAndRetainsPvpRecipient() throws Exception {
        UUID attacker = UUID.randomUUID(), recipient = UUID.randomUUID();
        try (SqliteDamageRepository repo = new SqliteDamageRepository(temp.resolve("damage.db"))) {
            Instant now = Instant.parse("2026-08-30T12:34:10Z");
            repo.record(new DamageEvent(now, attacker, "Murky", "DIRECT", null, recipient, "Victim", "minecraft:player", TargetCategory.PLAYER, "minecraft:overworld", 5.5, null, "player attack"));
            repo.record(new DamageEvent(now.plusSeconds(2), attacker, "Murky", "OWNER_CHAIN", null, UUID.randomUUID(), null, "minecraft:zombie", TargetCategory.ENTITY, "minecraft:overworld", 7.25, null, "arrow"));
            repo.record(new DamageEvent(now.plusSeconds(3), null, null, "UNTRACEABLE", "Dark Mage", UUID.randomUUID(), null, "minecraft:zombie", TargetCategory.ENTITY, "minecraft:overworld", 2.0, null, "magic"));

            assertEquals(3, repo.rawEventCount());
            DamageTotals totals = repo.totalsFor(attacker, now.minusSeconds(1), now.plusSeconds(60));
            assertEquals(12.75, totals.total(), 0.0001);
            assertEquals(5.5, totals.toPlayers(), 0.0001);
            assertEquals(7.25, totals.toEntities(), 0.0001);
            List<DamageEvent> received = repo.damageReceivedBy(recipient, now.minusSeconds(1), now.plusSeconds(60));
            assertEquals(1, received.size());
            assertEquals(attacker, received.get(0).attackerPlayerUuid());
        }
    }
}
