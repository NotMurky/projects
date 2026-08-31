package com.prominence.damage.fabric.mixin;

import com.prominence.damage.fabric.ProminenceDamageMod;
import net.minecraft.entity.Entity;
import net.minecraft.server.world.ServerWorld;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * Deterministic boss-add linking. While the server ticks an entity, we remember
 * it (per thread). If that entity spawns another entity during its tick, and it
 * is a tracked active boss, the newborn is registered as a linked child of that
 * boss's fight — so its damage rolls into the parent session.
 *
 * <p>This is general, not boss-specific: any boss mod that spawns minions/adds
 * from within its own AI tick is covered, with no proximity guessing. Bosses
 * whose adds carry an explicit owner field are also caught by the owner-chain
 * resolver; this handles the ones that carry no back-reference at all
 * (e.g. Gaia Guardian's vanilla witches/skeletons).
 */
@Mixin(ServerWorld.class)
public abstract class ServerWorldSpawnMixin {
    @Unique private static final ThreadLocal<Entity> prominence_damage$ticking = new ThreadLocal<>();

    @Inject(method = "tickEntity", at = @At("HEAD"))
    private void prominence_damage$enterTick(Entity entity, CallbackInfo ci) {
        prominence_damage$ticking.set(entity);
    }

    @Inject(method = "tickEntity", at = @At("RETURN"))
    private void prominence_damage$exitTick(Entity entity, CallbackInfo ci) {
        prominence_damage$ticking.remove();
    }

    @Inject(method = "spawnEntity", at = @At("HEAD"))
    private void prominence_damage$onSpawn(Entity entity, CallbackInfoReturnable<Boolean> cir) {
        Entity spawner = prominence_damage$ticking.get();
        if (spawner != null && entity != null) {
            ProminenceDamageMod.onEntitySpawnedDuringTick(spawner, entity);
        }
    }
}
