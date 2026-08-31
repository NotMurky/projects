package com.prominence.damage.domain;

import java.util.UUID;

/** A resolved player identity: stable UUID plus last-known display name. */
public record PlayerRef(UUID uuid, String name) {
    public PlayerRef {
        if (uuid == null) throw new IllegalArgumentException("player uuid must not be null");
    }
}
