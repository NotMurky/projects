package com.prominence.damage.fabric;

import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.prominence.damage.domain.DamageTotals;
import com.prominence.damage.domain.HeartFormat;
import com.prominence.damage.storage.SqliteDamageRepository;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.minecraft.command.argument.GameProfileArgumentType;
import net.minecraft.server.command.CommandManager;
import net.minecraft.server.command.ServerCommandSource;
import net.minecraft.server.network.ServerPlayerEntity;
import net.minecraft.text.Text;

import java.time.Instant;
import java.util.*;

public final class DamageCommand {
    public static void register() {
        CommandRegistrationCallback.EVENT.register((dispatcher, registry, env) -> {
            // Own command name — no collision with vanilla /damage, so no permission gate.
            dispatcher.register(CommandManager.literal("pdamage").requires(s -> true)
                .then(CommandManager.argument("minutes", IntegerArgumentType.integer(1, 10080))
                    .executes(ctx -> executeSelf(ctx.getSource(), IntegerArgumentType.getInteger(ctx, "minutes")))
                    .then(CommandManager.argument("player", GameProfileArgumentType.gameProfile())
                        .executes(ctx -> executeOther(ctx.getSource(), IntegerArgumentType.getInteger(ctx, "minutes"),
                                GameProfileArgumentType.getProfileArgument(ctx, "player").iterator().next())))));
            // Lifetime damage leaderboard — broadcasts server-wide, usable by everyone.
            dispatcher.register(CommandManager.literal("pdamagetotal").requires(s -> true)
                .executes(ctx -> leaderboard(ctx.getSource())));
        });
    }

    private static int leaderboard(ServerCommandSource source) {
        var repo = ProminenceDamageMod.repository();
        if (repo == null) { source.sendError(Text.literal("Tracker offline")); return 0; }
        try {
            List<SqliteDamageRepository.LeaderRow> rows = repo.lifetimeLeaderboard(10);
            StringBuilder sb = new StringBuilder("§6§lProminence lifetime damage leaderboard§r");
            if (rows.isEmpty()) {
                sb.append("\n§7No damage recorded yet.");
            } else {
                int rank = 1;
                for (SqliteDamageRepository.LeaderRow r : rows) {
                    sb.append(String.format(Locale.ROOT,
                            "\n§e%2d.§r §b%s§r — §a%s§r §7(players %s, entities %s)",
                            rank++, r.name() == null ? "?" : r.name(),
                            HeartFormat.hearts(r.total()),
                            HeartFormat.hearts(r.toPlayers()), HeartFormat.hearts(r.toEntities())));
                }
            }
            Text text = Text.literal(sb.toString());
            if (source.getServer() != null) source.getServer().getPlayerManager().broadcast(text, false);
            else source.sendFeedback(() -> text, false);
            return 1;
        } catch (Exception e) {
            source.sendError(Text.literal("Leaderboard failed: " + e.getMessage()));
            return 0;
        }
    }

    private static int executeSelf(ServerCommandSource source, int minutes) {
        // No-player form: PRIVATE per-player leaderboard for the last <minutes>,
        // with the three required columns (total / to players / to entities).
        var repo = ProminenceDamageMod.repository();
        if (repo == null) { source.sendError(Text.literal("Tracker offline")); return 0; }
        Instant now = Instant.now();
        Instant from = now.minusSeconds(minutes * 60L);
        try {
            List<SqliteDamageRepository.LeaderRow> rows = repo.windowLeaderboard(from, now, 25);
            StringBuilder sb = new StringBuilder(String.format(Locale.ROOT,
                    "§6§lDamage leaderboard — last %dm§r §7(total | to players | to entities)§r", minutes));
            if (rows.isEmpty()) {
                sb.append("\n§7No damage recorded in this window.");
            } else {
                int rank = 1;
                for (SqliteDamageRepository.LeaderRow r : rows) {
                    sb.append(String.format(Locale.ROOT,
                            "\n§e%2d.§r §b%s§r — §a%s§r §7(§c%s§7 / §a%s§7)§r",
                            rank++, r.name() == null ? "?" : r.name(),
                            HeartFormat.hearts(r.total()),
                            HeartFormat.hearts(r.toPlayers()), HeartFormat.hearts(r.toEntities())));
                }
            }
            Text text = Text.literal(sb.toString());
            source.sendFeedback(() -> text, false); // private to the sender
            return 1;
        } catch (Exception e) {
            source.sendError(Text.literal("Leaderboard failed: " + e.getMessage()));
            return 0;
        }
    }

    private static int executeOther(ServerCommandSource source, int minutes, com.mojang.authlib.GameProfile profile) {
        report(source, profile.getId(), profile.getName(), minutes, true);
        return 1;
    }

    private static void report(ServerCommandSource source, UUID uuid, String name, int minutes, boolean broadcast) {
        var repo = ProminenceDamageMod.repository();
        if (repo == null) { source.sendError(Text.literal("Tracker offline")); return; }
        Instant now = Instant.now();
        Instant from = now.minusSeconds(minutes * 60L);
        try {
            DamageTotals t = repo.totalsFor(uuid, from, now);
            String msg = String.format(Locale.ROOT, "§6%s§r last %dm — total §e%s§r (players §c%s§r, entities §a%s§r)",
                    name, minutes, HeartFormat.hearts(t.total()),
                    HeartFormat.hearts(t.toPlayers()), HeartFormat.hearts(t.toEntities()));
            Text text = Text.literal(msg);
            if (broadcast && source.getServer() != null) {
                source.getServer().getPlayerManager().broadcast(text, false);
            } else {
                source.sendFeedback(() -> text, false);
            }
        } catch (Exception e) {
            source.sendError(Text.literal("Query failed: " + e.getMessage()));
        }
    }
}
