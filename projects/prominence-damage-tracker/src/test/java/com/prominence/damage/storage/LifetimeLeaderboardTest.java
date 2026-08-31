package com.prominence.damage.storage;

import static org.junit.jupiter.api.Assertions.*;

import com.prominence.damage.domain.*;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class LifetimeLeaderboardTest {
    @TempDir Path temp;

    @Test void ranksByLifetimeTotalWithLatestNameAndCategorySplit() throws Exception {
        UUID a = UUID.randomUUID(), b = UUID.randomUUID();
        try (SqliteDamageRepository repo = new SqliteDamageRepository(temp.resolve("d.db"))) {
            Instant t0 = Instant.parse("2026-01-01T00:00:00Z");
            // Player A: 10 to entities, 4 to players = 14 total, renamed AoldA -> Anew
            repo.record(new DamageEvent(t0, a, "Aold", "DIRECT", null, UUID.randomUUID(), null, "minecraft:zombie", TargetCategory.ENTITY, "d", 10.0, null, "x"));
            repo.record(new DamageEvent(t0.plusSeconds(5), a, "Anew", "DIRECT", null, UUID.randomUUID(), "V", "minecraft:player", TargetCategory.PLAYER, "d", 4.0, null, "x"));
            // Player B: 20 to entities = 20 total (should rank first)
            repo.record(new DamageEvent(t0.plusSeconds(1), b, "Bee", "DIRECT", null, UUID.randomUUID(), null, "minecraft:creeper", TargetCategory.ENTITY, "d", 20.0, null, "x"));
            // Untraceable damage must not appear as a player row
            repo.record(new DamageEvent(t0.plusSeconds(2), null, null, "UNTRACEABLE", "Mob", UUID.randomUUID(), null, "minecraft:cow", TargetCategory.ENTITY, "d", 99.0, null, "x"));

            List<SqliteDamageRepository.LeaderRow> rows = repo.lifetimeLeaderboard(10);
            assertEquals(2, rows.size());
            assertEquals(b, rows.get(0).uuid());
            assertEquals("Bee", rows.get(0).name());
            assertEquals(20.0, rows.get(0).total(), 1e-6);
            assertEquals(a, rows.get(1).uuid());
            assertEquals("Anew", rows.get(1).name(), "latest known name should win");
            assertEquals(14.0, rows.get(1).total(), 1e-6);
            assertEquals(4.0, rows.get(1).toPlayers(), 1e-6);
            assertEquals(10.0, rows.get(1).toEntities(), 1e-6);
        }
    }
}
