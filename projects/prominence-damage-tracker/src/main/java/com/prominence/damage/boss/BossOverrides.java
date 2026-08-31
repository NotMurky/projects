package com.prominence.damage.boss;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.TreeSet;

/**
 * Pure parser/serializer for the operator boss-override file
 * ({@code config/prominence-damage/overrides.properties}). Lines are "+id"
 * (force-add) or "-id" (force-remove); blanks and '#' comments are ignored.
 * No Minecraft references, so it is fully unit-testable and safe to load in
 * the build's test JVM.
 */
public final class BossOverrides {
    private BossOverrides() {}

    public record Parsed(Set<String> additions, Set<String> removals) {}

    /** Read overrides from disk. Missing file yields empty sets; an unreadable
     * file is reported to stderr and treated as empty (must not abort startup). */
    public static Parsed load(Path file) {
        Set<String> add = new TreeSet<>(), rem = new TreeSet<>();
        try {
            if (Files.exists(file)) parse(Files.readAllLines(file), add, rem);
        } catch (IOException e) {
            System.err.println("[prominence_damage] could not read overrides " + file + ": " + e);
        }
        return new Parsed(add, rem);
    }

    static void parse(Iterable<String> lines, Set<String> add, Set<String> rem) {
        for (String raw : lines) {
            String line = raw.trim();
            if (line.isEmpty() || line.startsWith("#")) continue;
            char sign = line.charAt(0);
            String id = line.substring(1).trim();
            if (id.isEmpty()) continue;
            if (sign == '+') { add.add(id); rem.remove(id); }
            else if (sign == '-') { rem.add(id); add.remove(id); }
        }
    }

    /** Serialize override sets to the on-disk line format (with a header comment). */
    public static java.util.List<String> serialize(Set<String> additions, Set<String> removals) {
        java.util.List<String> lines = new java.util.ArrayList<>();
        lines.add("# prominence-damage boss overrides — '+id' force-add, '-id' force-remove");
        additions.forEach(a -> lines.add("+" + a));
        removals.forEach(r -> lines.add("-" + r));
        return lines;
    }
}
