package com.prominence.damage.domain;

import java.util.UUID;

public record Attribution(UUID playerUuid, String playerName, Kind kind, String sourceName) {
    public enum Kind { DIRECT, OWNER_CHAIN, UNTRACEABLE }
    public static Attribution untraceable(String source) { return new Attribution(null, null, Kind.UNTRACEABLE, source); }
}
