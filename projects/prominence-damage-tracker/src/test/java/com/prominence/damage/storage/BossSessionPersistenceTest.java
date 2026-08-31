package com.prominence.damage.storage;

import static org.junit.jupiter.api.Assertions.*;
import com.prominence.damage.domain.*;
import java.nio.file.Path;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class BossSessionPersistenceTest {
 @TempDir Path temp;
 @Test void concurrentSameTypeSessionsSurviveRestartAndCloseIndependently() throws Exception {
  Path db=temp.resolve("boss.db"); UUID first=UUID.randomUUID(), second=UUID.randomUUID(); Instant spawn=Instant.parse("2026-08-30T12:00:00Z");
  try(SqliteDamageRepository repo=new SqliteDamageRepository(db)){
   repo.openBossSession(new BossSession(first,"soulsweapons:draugr_boss","Old Champion's Remains",spawn,"minecraft:overworld","1,64,2",null,null));
   repo.openBossSession(new BossSession(second,"soulsweapons:draugr_boss","Old Champion's Remains",spawn,"minecraft:overworld","5,64,6",null,null));
  }
  try(SqliteDamageRepository repo=new SqliteDamageRepository(db)){
   assertEquals(2,repo.activeBossSessions().size());
   repo.closeBossSession(first,spawn.plusSeconds(30),"death"); repo.flush();
   assertEquals(1,repo.activeBossSessions().size());
   assertEquals(second,repo.activeBossSessions().get(0).bossEntityUuid());
   assertEquals("death",repo.bossSession(first).orElseThrow().endReason());
  }
 }
}
