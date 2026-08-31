package com.prominence.damage.fabric;

import com.mojang.brigadier.arguments.StringArgumentType;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.minecraft.server.command.CommandManager;
import net.minecraft.server.command.ServerCommandSource;
import net.minecraft.text.Text;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * In-game /hours, served from a snapshot the playtime tracker pushes over RCON.
 *
 * The hours SQLite DB lives on the host outside the server container, so the mod
 * cannot read it directly. Instead the tracker daemon periodically calls the
 * op-only console command:
 *   hoursdata &lt;name&gt; &lt;activeSeconds&gt; &lt;afkSeconds&gt;
 * which updates one entry in this in-memory table. /hours (all players) renders
 * from that table. Snapshot is ephemeral and rebuilt continuously by the tracker.
 */
public final class HoursCommand {
    private record Entry(long activeSeconds, long afkSeconds, long updatedAtMillis) {}
    private static final Map<String, Entry> SNAPSHOT = new ConcurrentHashMap<>();

    public static void register() {
        CommandRegistrationCallback.EVENT.register((dispatcher, registry, env) -> {
            dispatcher.register(CommandManager.literal("hours").requires(s -> true)
                .executes(ctx -> leaderboard(ctx.getSource()))
                .then(CommandManager.argument("player", StringArgumentType.word())
                    .executes(ctx -> single(ctx.getSource(), StringArgumentType.getString(ctx, "player")))));
            // Op/console-only ingestion endpoint used by the tracker daemon.
            dispatcher.register(CommandManager.literal("hoursdata").requires(s -> s.hasPermissionLevel(4))
                .then(CommandManager.argument("name", StringArgumentType.word())
                    .then(CommandManager.argument("active", com.mojang.brigadier.arguments.LongArgumentType.longArg(0))
                        .then(CommandManager.argument("afk", com.mojang.brigadier.arguments.LongArgumentType.longArg(0))
                            .executes(ctx -> ingest(ctx.getSource(),
                                    StringArgumentType.getString(ctx, "name"),
                                    com.mojang.brigadier.arguments.LongArgumentType.getLong(ctx, "active"),
                                    com.mojang.brigadier.arguments.LongArgumentType.getLong(ctx, "afk")))))));
        });
    }

    private static int ingest(ServerCommandSource src, String name, long active, long afk) {
        SNAPSHOT.put(name.toLowerCase(Locale.ROOT), new Entry(active, afk, System.currentTimeMillis()));
        return 1; // silent; tracker calls this frequently
    }

    static String fmtDuration(long seconds) {
        long m = seconds / 60;
        long h = m / 60; m = m % 60;
        if (h > 0 && m > 0) return h + "h " + m + "m";
        if (h > 0) return h + "h";
        return m + "m";
    }

    private static int single(ServerCommandSource src, String player) {
        Entry e = SNAPSHOT.get(player.toLowerCase(Locale.ROOT));
        if (e == null) {
            src.sendFeedback(() -> Text.literal("§7No tracked active time for §f" + player + "§7 yet."), false);
            return 1;
        }
        String msg = String.format(Locale.ROOT,
                "§6%s§r — §e%s§r active playtime §7(AFK excluded: %s)",
                player, fmtDuration(e.activeSeconds()), fmtDuration(e.afkSeconds()));
        src.sendFeedback(() -> Text.literal(msg), false);
        return 1;
    }

    private static int leaderboard(ServerCommandSource src) {
        if (SNAPSHOT.isEmpty()) {
            src.sendFeedback(() -> Text.literal("§7No playtime recorded yet (tracker warming up)."), false);
            return 1;
        }
        List<Map.Entry<String, Entry>> ordered = new ArrayList<>(SNAPSHOT.entrySet());
        ordered.sort((a, b) -> Long.compare(b.getValue().activeSeconds(), a.getValue().activeSeconds()));
        StringBuilder sb = new StringBuilder("§6§lProminence active-playtime leaderboard§r");
        int rank = 1;
        for (Map.Entry<String, Entry> en : ordered) {
            if (rank > 10) break;
            sb.append(String.format(Locale.ROOT, "\n§e%2d.§r §b%s§r — §a%s§r",
                    rank++, en.getKey(), fmtDuration(en.getValue().activeSeconds())));
        }
        sb.append("\n§7AFK excluded after 5 min without moving or looking around.");
        src.sendFeedback(() -> Text.literal(sb.toString()), false);
        return 1;
    }
}
