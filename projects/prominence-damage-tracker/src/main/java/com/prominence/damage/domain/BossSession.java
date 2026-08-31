package com.prominence.damage.domain;
import java.time.Instant;
import java.util.UUID;
public record BossSession(UUID bossEntityUuid,String bossTypeId,String bossDisplayName,Instant spawnedAt,String spawnDimension,String spawnPosition,Instant endedAt,String endReason) {}
