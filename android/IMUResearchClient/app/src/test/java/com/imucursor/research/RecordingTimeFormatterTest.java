package com.imucursor.research;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class RecordingTimeFormatterTest {

    @Test
    public void zeroFormatsAsZeroTime() {
        assertEquals(
                "00:00:00",
                RecordingTimeFormatter.formatElapsed(0L)
        );
    }

    @Test
    public void elapsedTimeFormatsHoursMinutesAndSeconds() {
        assertEquals(
                "01:02:03",
                RecordingTimeFormatter.formatElapsed(3_723_999L)
        );
    }

    @Test
    public void hoursDoNotWrapAfterTwentyFourHours() {
        assertEquals(
                "27:00:05",
                RecordingTimeFormatter.formatElapsed(
                        27L * 3_600_000L + 5_000L
                )
        );
    }

    @Test
    public void negativeElapsedTimeIsClampedToZero() {
        assertEquals(
                "00:00:00",
                RecordingTimeFormatter.formatElapsed(-10L)
        );
    }
}
