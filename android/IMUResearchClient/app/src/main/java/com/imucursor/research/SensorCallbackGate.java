package com.imucursor.research;

/**
 * Separates closing sensor admission from waiting for admitted callbacks.
 * A successful tryEnter() must be paired with exit() in the caller's finally.
 * close() is short; awaitIdle() belongs on the stop worker for a normal STOP.
 */
final class SensorCallbackGate {
    private boolean accepting;
    private int activeCallbacks;

    synchronized void open() {
        if (accepting || activeCallbacks != 0) {
            throw new IllegalStateException("Previous sensor admission has not closed and drained");
        }
        accepting = true;
    }

    synchronized boolean tryEnter() {
        if (!accepting) {
            return false;
        }
        activeCallbacks++;
        return true;
    }

    synchronized void exit() {
        if (activeCallbacks <= 0) {
            throw new IllegalStateException("No admitted sensor callback to release");
        }
        activeCallbacks--;
        if (activeCallbacks == 0) {
            notifyAll();
        }
    }

    synchronized void close() {
        accepting = false;
    }

    synchronized void awaitIdle() {
        boolean interrupted = false;
        while (activeCallbacks != 0) {
            try {
                wait();
            } catch (InterruptedException e) {
                // Interruption must not allow consumers to finalize ahead of a producer.
                interrupted = true;
            }
        }
        if (interrupted) {
            Thread.currentThread().interrupt();
        }
    }
}
