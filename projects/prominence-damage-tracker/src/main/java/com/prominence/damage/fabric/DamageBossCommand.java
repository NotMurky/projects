package com.prominence.damage.fabric;

import com.mojang.brigadier.arguments.StringArgumentType;
import com.prominence.damage.boss.BossOverrides;
import com.prominence.damage.boss.BossRegistry;
import com.prominence.damage.boss.DefaultBossIds;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.minecraft.registry.Registries;
import net.minecraft.server.command.CommandManager;
import net.minecraft.text.Text;
import net.minecraft.util.Identifier;

import java.io.IOException;
import java.nio.file.*;
import java.util.*;

/**
 * OP-only /damageboss add|remove|list — mutates the runtime BossRegistry and
 * persists overrides to config/prominence-damage/overrides.properties. The same
 * override file is loaded at server start so manual boss-list changes survive
 * restarts.
 */
public final class DamageBossCommand {
    private static final Set<String> additions = new TreeSet<>();
    private static final Set<String> removals = new TreeSet<>();
    private static Path overridesPath; // set once the server run directory is known

    /** Parsed override file contents. */
    public record Overrides(Set<String> additions, Set<String> removals) {}

    /**
     * Read the persisted override file. Delegates to the Minecraft-free
     * {@link BossOverrides} parser.
     */
    public static Overrides loadOverrides(Path file) {
        BossOverrides.Parsed p = BossOverrides.load(file);
        return new Overrides(p.additions(), p.removals());
    }

    /** Prime the in-memory override sets and remember where to persist them. */
    public static void initFrom(Path file, Overrides loaded) {
        overridesPath = file;
        additions.clear(); additions.addAll(loaded.additions());
        removals.clear();  removals.addAll(loaded.removals());
    }

    public static void register() {
        CommandRegistrationCallback.EVENT.register((dispatcher, registry, env) -> {
            dispatcher.register(CommandManager.literal("damageboss")
                .requires(s -> s.hasPermissionLevel(2))
                .then(CommandManager.literal("list").executes(ctx -> {
                    var r = ProminenceDamageMod.bossRegistry();
                    if (r == null) { ctx.getSource().sendError(Text.literal("Tracker offline")); return 0; }
                    ctx.getSource().sendFeedback(() -> Text.literal("Bosses (" + r.all().size() + "): " + String.join(", ", r.all())), false);
                    return 1;
                }))
                .then(CommandManager.literal("add").then(CommandManager.argument("id", StringArgumentType.greedyString())
                    .executes(ctx -> mutate(ctx.getSource(), StringArgumentType.getString(ctx, "id"), true))))
                .then(CommandManager.literal("remove").then(CommandManager.argument("id", StringArgumentType.greedyString())
                    .executes(ctx -> mutate(ctx.getSource(), StringArgumentType.getString(ctx, "id"), false)))));
        });
    }

    private static int mutate(net.minecraft.server.command.ServerCommandSource src, String rawId, boolean add) {
        Identifier id;
        try { id = new Identifier(rawId.trim()); }
        catch (Exception e) { src.sendError(Text.literal("Invalid id: " + rawId)); return 0; }
        // Validate against the live entity-type registry so typos are rejected.
        if (!Registries.ENTITY_TYPE.containsId(id)) {
            src.sendError(Text.literal("Unknown entity type: " + id + " (not in the loaded registry)"));
            return 0;
        }
        String s = id.toString();
        if (add) { additions.add(s); removals.remove(s); }
        else { removals.add(s); additions.remove(s); }
        var current = ProminenceDamageMod.bossRegistry();
        Set<String> tagged = current == null ? new HashSet<>() : new HashSet<>(current.all());
        tagged.removeAll(DefaultBossIds.ALL);
        tagged.removeAll(additions);
        ProminenceDamageMod.setBossRegistry(new BossRegistry(DefaultBossIds.ALL, tagged, additions, removals));
        // Persist and only confirm success if the file actually wrote.
        try {
            persist();
            src.sendFeedback(() -> Text.literal((add ? "Added " : "Removed ") + s + " (saved)"), true);
            return 1;
        } catch (IOException e) {
            src.sendError(Text.literal("Applied in memory but FAILED to save overrides: " + e.getMessage()
                    + " — change will not survive a restart."));
            return 0;
        }
    }

    private static void persist() throws IOException {
        if (overridesPath == null) throw new IOException("override path not initialized");
        Files.createDirectories(overridesPath.getParent());
        List<String> lines = BossOverrides.serialize(additions, removals);
        Path tmp = overridesPath.resolveSibling(overridesPath.getFileName() + ".tmp");
        Files.write(tmp, lines);
        Files.move(tmp, overridesPath, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
    }
}
