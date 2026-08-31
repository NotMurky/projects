package com.prominence.damage.storage;

import static org.junit.jupiter.api.Assertions.*;

import com.prominence.damage.domain.*;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class WindowLeaderboardTest {
    @TempDir Path temp;

    @Test void windowLeaderboardSplitsCategoriesAndRespectsWindow() throws Exception {
        UUID a = UUID.randomUUID(), b = UUID.randomUUID(), victim = UUID.randomUUID();
        Instant t0 = Instant.parse("2026-08-31T00:00:00Z");
        try (SqliteDamageRepository repo = new SqliteDamageRepository(temp.resolve("d.db"))) {
            // A: 10 to entity + 4 to player = 14 total, inside window
            repo.record(new DamageEvent(t0.plusSeconds(10), a, "Aylin", "DIRECT", null, UUID.randomUUID(), null, "minecraft:zombie", TargetCategory.ENTITY, "d", 10.0, null, "player"));
            repo.record(new DamageEvent(t0.plusSeconds(20), a, "Aylin", "DIRECT", null, victim, "V", "minecraft:player", TargetCategory.PLAYER, "d", 4.0, null, "player"));
            // B: 30 to entity, inside window
            repo.record(new DamageEvent(t0.plusSeconds(30), b, "Borin", "DIRECT", null, UUID.randomUUID(), null, "minecraft:skeleton", TargetCategory.ENTITY, "d", 30.0, null, "player"));
            // A: 999 but OUTSIDE the window (long before)
            repo.record(new DamageEvent(t0.minusSeconds(9999), a, "Aylin", "DIRECT", null, UUID.randomUUID(), null, "minecraft:cow", TargetCategory.ENTITY, "d", 999.0, null, "player"));
            // untraceable must not appear
            repo.record(new DamageEvent(t0.plusSeconds(40), null, null, "UNTRACEABLE", "Mob", UUID.randomUUID(), null, "minecraft:cow", TargetCategory.ENTITY, "d", 50.0, null, "mob"));
            repo.flush();

            List<SqliteDamageRepository.LeaderRow> rows =
                    repo.windowLeaderboard(t0, t0.plusSeconds(3600), 10);
            assertEquals(2, rows.size());
            // B ranks first (30 > 14)
            assertEquals(b, rows.get(0).uuid());
            assertEquals(30.0, rows.get(0).total(), 1e-6);
            assertEquals(0.0, rows.get(0).toPlayers(), 1e-6);
            assertEquals(30.0, rows.get(0).toEntities(), 1e-6);
            // A second: 14 total, split 4 players / 10 entities (999 excluded by window)
            assertEquals(a, rows.get(1).uuid());
            assertEquals(14.0, rows.get(1).total(), 1e-6);
            assertEquals(4.0, rows.get(1).toPlayers(), 1e-6);
            assertEquals(10.0, rows.get(1).toEntities(), 1e-6);
            assertEquals("Aylin", rows.get(1).name());
        }
    }

    @Test void contributorNamesRestoreLatestNamePerSession() throws Exception {
        UUID boss = UUID.randomUUID(), p = UUID.randomUUID();
        Instant t0 = Instant.parse("2026-08-31T00:00:00Z");
        try (SqliteDamageRepository repo = new SqliteDamageRepository(temp.resolve("n.db"))) {
            repo.record(new DamageEvent(t0, p, "OldName", "DIRECT", null, boss, null, "minecraft:wither", TargetCategory.ENTITY, "d", 5.0, boss, "player"));
            repo.record(new DamageEvent(t0.plusSeconds(5), p, "NewName", "DIRECT", null, boss, null, "minecraft:wither", TargetCategory.ENTITY, "d", 7.0, boss, "player"));
            repo.flush();
            Map<UUID, String> names = repo.contributorNamesForSession(boss);
            assertEquals("NewName", names.get(p));
        }
    }
}
