package com.prominence.damage.domain;

import java.time.Instant;
import java.util.UUID;

public record DamageEvent(Instant occurredAt, UUID attackerPlayerUuid, String attackerLastKnownName,
 String attributionKind, String untraceableSourceName, UUID targetEntityUuid, String targetPlayerLastKnownName,
 String targetTypeId, TargetCategory targetCategory, String dimension, double actualDamage,
 UUID bossSessionUuid, String damageSourceName) {
 public DamageEvent { if (actualDamage <= 0 || !Double.isFinite(actualDamage)) throw new IllegalArgumentException("actualDamage must be finite and positive"); }
}
