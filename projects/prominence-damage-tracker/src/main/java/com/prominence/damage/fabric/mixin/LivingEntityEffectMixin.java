package com.prominence.damage.fabric.mixin;

import com.prominence.damage.fabric.ProminenceDamageMod;
import net.minecraft.entity.Entity;
import net.minecraft.entity.LivingEntity;
import net.minecraft.entity.effect.StatusEffectInstance;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * Captures the player responsible when a damaging status effect is applied with a
 * known source entity. Vanilla's {@code addStatusEffect(instance, source)} carries
 * the applier, but the later per-tick effect damage arrives with a source-less
 * DamageSource. Recording provenance here — at the exact moment the game tells us
 * who applied it — lets those anonymous ticks be credited without any guessing.
 */
@Mixin(LivingEntity.class)
public abstract class LivingEntityEffectMixin {
    @Inject(method = "addStatusEffect(Lnet/minecraft/entity/effect/StatusEffectInstance;Lnet/minecraft/entity/Entity;)Z", at = @At("HEAD"))
    private void prominence_damage$captureEffectSource(StatusEffectInstance effect, Entity source, CallbackInfoReturnable<Boolean> cir) {
        LivingEntity self = (LivingEntity) (Object) this;
        if (self.getWorld() == null || self.getWorld().isClient || source == null) return;
        // Duration is in ticks (20/s). Give a small buffer so the final tick still resolves.
        long ttlMillis = Math.max(0, effect.getDuration()) * 50L + 1000L;
        ProminenceDamageMod.onEffectApplied(self, source, ttlMillis);
    }
}
