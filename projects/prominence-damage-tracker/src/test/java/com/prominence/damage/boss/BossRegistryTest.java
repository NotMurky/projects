package com.prominence.damage.boss;

import static org.junit.jupiter.api.Assertions.*;
import java.util.Set;
import org.junit.jupiter.api.Test;

class BossRegistryTest {
 @Test void combinesSeedsRuntimeTagAndManualOverridesConservatively(){
  BossRegistry registry=new BossRegistry(DefaultBossIds.ALL,Set.of("mod:tagged"),Set.of("mod:added"),Set.of("minecraft:warden","mod:tagged"));
  assertTrue(registry.isBoss("minecraft:wither"));
  assertTrue(registry.isBoss("soulsweapons:draugr_boss"));
  assertTrue(registry.isBoss("mod:added"));
  assertFalse(registry.isBoss("minecraft:warden"));
  assertFalse(registry.isBoss("mod:tagged"));
 }
}
