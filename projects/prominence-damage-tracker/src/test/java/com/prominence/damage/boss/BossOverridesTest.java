package com.prominence.damage.boss;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.TreeSet;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class BossOverridesTest {
    @TempDir Path temp;

    @Test void loadsAddAndRemoveLines() throws Exception {
        Path f = temp.resolve("overrides.properties");
        Files.write(f, List.of(
                "# comment",
                "+mymod:custom_boss",
                "-minecraft:zombie",
                "",
                "  +another:boss  "));
        var o = BossOverrides.load(f);
        assertTrue(o.additions().contains("mymod:custom_boss"));
        assertTrue(o.additions().contains("another:boss"));
        assertTrue(o.removals().contains("minecraft:zombie"));
        assertEquals(2, o.additions().size());
        assertEquals(1, o.removals().size());
    }

    @Test void missingFileYieldsEmpty() {
        var o = BossOverrides.load(temp.resolve("nope.properties"));
        assertTrue(o.additions().isEmpty());
        assertTrue(o.removals().isEmpty());
    }

    @Test void lastSignWinsForSameId() throws Exception {
        Path f = temp.resolve("o2.properties");
        Files.write(f, List.of("+x:y", "-x:y"));
        var o = BossOverrides.load(f);
        assertTrue(o.removals().contains("x:y"));
        assertFalse(o.additions().contains("x:y"));
    }

    @Test void serializeRoundTrips() {
        var add = new TreeSet<>(List.of("mod:a", "mod:b"));
        var rem = new TreeSet<>(List.of("minecraft:zombie"));
        List<String> lines = BossOverrides.serialize(add, rem);
        var add2 = new TreeSet<String>(); var rem2 = new TreeSet<String>();
        BossOverrides.parse(lines, add2, rem2);
        assertEquals(add, add2);
        assertEquals(rem, rem2);
    }
}
