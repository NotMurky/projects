package com.prominence.damage.boss;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Tracks verifiable parent/child relationships between an active boss and its
 * linked secondary entities — boss parts, shields, transformations/phase forms,
 * and spawned minions with a provable owner chain. Damage to a linked entity is
 * rolled into the parent boss's contribution session instead of opening a new one.
 *
 * <p>Links are only added when a genuine ownership/parent relationship is proven
 * by the caller (e.g. {@code Ownable.getOwner()} resolving to a tracked boss, or a
 * boss-part whose parent entity is a tracked boss). This class never guesses by
 * proximity. Fully unit-testable; holds no Minecraft references.
 */
public final class BossLinkRegistry {
    // linked child entity uuid -> parent boss entity (session) uuid
    private final Map<UUID, UUID> childToParent = new ConcurrentHashMap<>();

    /** Link {@code child} to the boss session {@code parent}. Idempotent. */
    public void link(UUID child, UUID parent) {
        if (child == null || parent == null || child.equals(parent)) return;
        childToParent.put(child, parent);
    }

    /**
     * Resolve the boss session a hit against {@code targetUuid} belongs to.
     * If the target is itself an active boss, returns it. If it is a linked
     * child of an active boss, returns the parent. Otherwise empty.
     *
     * @param targetUuid       the entity that was damaged
     * @param isActiveSession  predicate: is this uuid an open boss session?
     */
    public Optional<UUID> sessionForTarget(UUID targetUuid, java.util.function.Predicate<UUID> isActiveSession) {
        if (targetUuid == null) return Optional.empty();
        if (isActiveSession.test(targetUuid)) return Optional.of(targetUuid);
        UUID parent = childToParent.get(targetUuid);
        if (parent != null && isActiveSession.test(parent)) return Optional.of(parent);
        // Parent session already closed: drop the stale link.
        if (parent != null) childToParent.remove(targetUuid);
        return Optional.empty();
    }

    /** Remove one link (child died/removed). */
    public void unlink(UUID child) {
        if (child != null) childToParent.remove(child);
    }

    /** Drop every link pointing at a parent whose session just ended. */
    public void unlinkChildrenOf(UUID parent) {
        if (parent == null) return;
        childToParent.entrySet().removeIf(e -> e.getValue().equals(parent));
    }

    public boolean isLinked(UUID child) { return childToParent.containsKey(child); }
    public int linkCount() { return childToParent.size(); }
}
