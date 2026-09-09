package com.imucursor.research;

import java.util.Locale;

/**
 * Pure-Java elapsed-time formatting used by the recording UI.
 */
public final class RecordingTimeFormatter {

    private RecordingTimeFormatter() {
        // Utility class.
    }

    public static String formatElapsed(long elapsedMs) {
        long safeMs = Math.max(0L, elapsedMs);
        long totalSeconds = safeMs / 1000L;
        long hours = totalSeconds / 3600L;
        long minutes = (totalSeconds % 3600L) / 60L;
        long seconds = totalSeconds % 60L;

        return String.format(
                Locale.US,
                "%02d:%02d:%02d",
                hours,
                minutes,
                seconds
        );
    }
}
