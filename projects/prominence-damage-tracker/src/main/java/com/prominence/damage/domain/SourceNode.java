package com.prominence.damage.domain;

import java.util.UUID;

public final class SourceNode {
    private final String displayName;
    private final UUID playerUuid;
    private final String playerName;
    private SourceNode owner;

    private SourceNode(String displayName, UUID playerUuid, String playerName, SourceNode owner) {
        this.displayName = displayName;
        this.playerUuid = playerUuid;
        this.playerName = playerName;
        this.owner = owner;
    }

    public static SourceNode player(UUID uuid, String name) { return new SourceNode(name, uuid, name, null); }
    public static SourceNode owned(String name, SourceNode owner) { return new SourceNode(name, null, null, owner); }
    public static SourceNode unowned(String name) { return new SourceNode(name, null, null, null); }
    public static SourceNode cyclic(String name) { SourceNode n = unowned(name); n.owner = n; return n; }
    public String displayName() { return displayName; }
    public UUID playerUuid() { return playerUuid; }
    public String playerName() { return playerName; }
    public SourceNode owner() { return owner; }
}
