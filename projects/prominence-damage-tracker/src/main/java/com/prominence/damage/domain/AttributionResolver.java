package com.prominence.damage.domain;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public final class AttributionResolver {
    public Attribution resolve(SourceNode source) {
        if (source == null) return Attribution.untraceable("Unknown");
        String original = source.displayName();
        Set<SourceNode> visited = Collections.newSetFromMap(new IdentityHashMap<>());
        int depth = 0;
        for (SourceNode node = source; node != null && visited.add(node) && depth < 32; node = node.owner(), depth++) {
            if (node.playerUuid() != null) {
                Attribution.Kind kind = depth == 0 ? Attribution.Kind.DIRECT : Attribution.Kind.OWNER_CHAIN;
                return new Attribution(node.playerUuid(), node.playerName(), kind, original);
            }
        }
        return Attribution.untraceable(original == null || original.isBlank() ? "Unknown" : original);
    }
}
