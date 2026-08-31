package com.prominence.damage.domain;

import java.util.Locale;

/** Formats a raw half-hearts-based HP damage figure as "hearts" (1 heart = 2 HP). */
public final class HeartFormat {
    private HeartFormat() {}

    public static String hearts(double hp) {
        double hearts = hp / 2.0;
        // Round to one decimal place; drop a trailing .0 so whole hearts read cleanly.
        double rounded = Math.round(hearts * 10.0) / 10.0;
        String number;
        if (rounded == Math.floor(rounded)) {
            number = String.format(Locale.ROOT, "%,d", (long) rounded);
        } else {
            number = String.format(Locale.ROOT, "%,.1f", rounded);
        }
        String unit = (rounded == 1.0) ? "heart" : "hearts";
        return number + " " + unit;
    }
}
