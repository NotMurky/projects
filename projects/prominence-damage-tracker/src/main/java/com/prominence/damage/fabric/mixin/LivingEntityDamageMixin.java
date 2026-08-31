package com.prominence.damage.fabric.mixin;

import com.prominence.damage.fabric.ProminenceDamageMod;
import net.minecraft.entity.LivingEntity;
import net.minecraft.entity.damage.DamageSource;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * Captures the actual post-mitigation damage dealt to a LivingEntity by measuring
 * health delta across the vanilla damage method. Server-side only.
 *
 * <p>Uses a per-thread depth-indexed stack of pre-hit health rather than a single
 * field: modded effects can call {@code damage()} re-entrantly on the same entity
 * (thorns, lifesteal, chained procs), and a single field would be overwritten by
 * the nested call, corrupting the outer delta. The stack pairs each HEAD capture
 * with its matching RETURN.
 */
@Mixin(LivingEntity.class)
public abstract class LivingEntityDamageMixin {
    @org.spongepowered.asm.mixin.Unique
    private static final ThreadLocal<java.util.ArrayDeque<Float>> prominence_damage$stack =
            ThreadLocal.withInitial(java.util.ArrayDeque::new);

    @Inject(method = "damage", at = @At("HEAD"))
    private void prominence_damage$captureBefore(DamageSource source, float amount, CallbackInfoReturnable<Boolean> cir) {
        LivingEntity self = (LivingEntity) (Object) this;
        if (self.getWorld() == null || self.getWorld().isClient) return;
        prominence_damage$stack.get().push(self.getHealth());
    }

    @Inject(method = "damage", at = @At("RETURN"))
    private void prominence_damage$captureAfter(DamageSource source, float amount, CallbackInfoReturnable<Boolean> cir) {
        LivingEntity self = (LivingEntity) (Object) this;
        if (self.getWorld() == null || self.getWorld().isClient) return;
        java.util.ArrayDeque<Float> stack = prominence_damage$stack.get();
        if (stack.isEmpty()) return; // defensive: unmatched RETURN
        float preHealth = stack.pop();
        if (!Boolean.TRUE.equals(cir.getReturnValue())) return;
        float actual = preHealth - self.getHealth();
        if (actual <= 0.0f || !Float.isFinite(actual)) return;
        ProminenceDamageMod.onActualDamage(self, source, actual);
    }
}
