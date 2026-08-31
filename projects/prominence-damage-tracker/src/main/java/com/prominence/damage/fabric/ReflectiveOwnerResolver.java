package com.prominence.damage.fabric;

import net.minecraft.entity.Entity;
import net.minecraft.server.world.ServerWorld;

import java.lang.reflect.Field;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Last-resort owner resolution for modded summons that keep their owner in a
 * private field and expose no {@code Ownable}/{@code Projectile}/{@code Tameable}
 * interface — e.g. Botania's {@code PixieEntity.summoner}, which Gaia Guardian
 * sets to itself. Reads a small set of conventional owner field names by
 * reflection.
 *
 * <p>Mods on this pack are shipped unobfuscated, so the source field names
 * ({@code summoner}, {@code owner}, ...) are the real runtime names. The
 * resolved {@link Field} (or its confirmed absence) is cached per entity class,
 * so each class pays the reflective lookup at most once; steady-state cost is a
 * map get plus one field read. Any reflection failure resolves to {@code null}
 * so attribution stays untraceable rather than guessing.
 */
public final class ReflectiveOwnerResolver {
    private ReflectiveOwnerResolver() {}

    private static final String[] FIELD_NAMES = {
            "summoner", "owner", "caster",
            "ownerEntity", "casterEntity",
            "ownerUuid", "ownerUUID", "casterUuid"
    };

    // Sentinel meaning "this class has no usable owner field" so we don't re-scan.
    private static final Field NONE;
    static {
        try { NONE = ReflectiveOwnerResolver.class.getDeclaredField("NONE"); }
        catch (NoSuchFieldException e) { throw new ExceptionInInitializerError(e); }
    }

    private static final Map<Class<?>, Field> CACHE = new ConcurrentHashMap<>();

    /** Resolve the owning entity of {@code entity} via a cached owner field, or null. */
    public static Entity resolve(Entity entity) {
        if (entity == null) return null;
        Field f = CACHE.computeIfAbsent(entity.getClass(), ReflectiveOwnerResolver::findField);
        if (f == NONE) return null;
        try {
            Object v = f.get(entity);
            if (v instanceof Entity owner) return owner;
            if (v instanceof UUID uuid && entity.getWorld() instanceof ServerWorld sw) {
                return sw.getEntity(uuid);
            }
        } catch (Throwable ignored) {
            // Reflection blocked or field shape changed: give up quietly.
        }
        return null;
    }

    private static Field findField(Class<?> cls) {
        for (Class<?> c = cls; c != null && c != Object.class; c = c.getSuperclass()) {
            for (String name : FIELD_NAMES) {
                try {
                    Field f = c.getDeclaredField(name);
                    Class<?> t = f.getType();
                    if (Entity.class.isAssignableFrom(t) || t == UUID.class) {
                        f.setAccessible(true);
                        return f;
                    }
                } catch (NoSuchFieldException ignored) {
                    // try next name
                } catch (Throwable t) {
                    return NONE; // e.g. SecurityException — stop scanning this class
                }
            }
        }
        return NONE;
    }
}
