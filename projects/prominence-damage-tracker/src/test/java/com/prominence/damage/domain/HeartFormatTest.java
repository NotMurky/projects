package com.prominence.damage.domain;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class HeartFormatTest {
    @Test void halfHeartAndWholeHearts() {
        assertEquals("2.5 hearts", HeartFormat.hearts(5.0));   // 5 hp = 2.5 hearts
        assertEquals("5 hearts", HeartFormat.hearts(10.0));    // whole hearts drop the .0
        assertEquals("0.5 hearts", HeartFormat.hearts(1.0));
        assertEquals("1 heart", HeartFormat.hearts(2.0));      // singular
    }

    @Test void largeValuesUseGrouping() {
        assertEquals("617.3 hearts", HeartFormat.hearts(1234.5)); // 1234.5/2 = 617.25 -> 617.3
        assertEquals("5,000 hearts", HeartFormat.hearts(10000.0));
    }

    @Test void zeroIsZeroHearts() {
        assertEquals("0 hearts", HeartFormat.hearts(0.0));
    }
}
