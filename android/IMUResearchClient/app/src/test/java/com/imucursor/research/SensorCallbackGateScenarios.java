package com.imucursor.research;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.FutureTask;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * Shared behavioral cases for JUnit and a dependency-free JVM runner.
 * Exercises the production gate with real threads and queues, without Android.
 */
final class SensorCallbackGateScenarios {
    private static final long TIMEOUT_SECONDS = 5L;

    static void stopWaitsBeforeEitherQueueReceivesTheAdmittedSample() throws Exception {
        runPausedCallback(false, false);
    }

    static void stopWaitsBetweenLocalAndNetworkOffers() throws Exception {
        runPausedCallback(true, false);
    }

    static void interruptionCannotBypassTheCallbackBarrier() throws Exception {
        runPausedCallback(true, true);
    }

    private static void runPausedCallback(boolean localOfferedFirst, boolean interruptStop)
            throws Exception {
        SensorCallbackGate gate = new SensorCallbackGate();
        LinkedBlockingQueue<String> local = new LinkedBlockingQueue<>();
        LinkedBlockingQueue<String> network = new LinkedBlockingQueue<>();
        CountDownLatch callbackPaused = new CountDownLatch(1);
        CountDownLatch releaseCallback = new CountDownLatch(1);
        CountDownLatch admissionClosed = new CountDownLatch(1);
        gate.open();

        FutureTask<Void> callback = new FutureTask<>(() -> {
            check(gate.tryEnter(), "Recording callback was rejected");
            try {
                if (localOfferedFirst) {
                    local.offer("sample-1");
                }
                callbackPaused.countDown();
                await(releaseCallback, "Callback was not released");
                if (!localOfferedFirst) {
                    local.offer("sample-1");
                }
                network.offer("sample-1");
            } finally {
                gate.exit();
            }
            return null;
        });

        FutureTask<List<List<String>>> stop = new FutureTask<>(() -> {
            gate.close();
            admissionClosed.countDown();
            gate.awaitIdle();
            check(Thread.currentThread().isInterrupted() == interruptStop,
                    "Barrier did not preserve the stop thread's interrupt status");
            List<String> saved = new ArrayList<>();
            List<String> sent = new ArrayList<>();
            local.drainTo(saved);
            network.drainTo(sent);
            return Arrays.asList(saved, sent);
        });

        Thread callbackThread = worker(callback, "test-sensor-callback");
        Thread stopThread = worker(stop, "test-stop-drain");
        try {
            callbackThread.start();
            await(callbackPaused, "Callback did not reach its controlled pause");
            stopThread.start();
            await(admissionClosed, "STOP did not close admission promptly");
            boolean lateAdmission = gate.tryEnter();
            if (lateAdmission) {
                gate.exit();
            }
            check(!lateAdmission, "STOP accepted a new callback after closing admission");
            assertWaitingForCallback(stopThread, stop);
            if (interruptStop) {
                stopThread.interrupt();
                try {
                    // The callback stays held by its latch for this entire window.
                    // Observe completion directly: a WAITING state snapshot could
                    // still describe the old wait before interruption was handled.
                    stop.get(1L, TimeUnit.SECONDS);
                    throw new AssertionError("Interrupted STOP bypassed its unfinished callback");
                } catch (TimeoutException expected) {
                    // STOP must remain incomplete until releaseCallback below.
                }
            }
            releaseCallback.countDown();
            callback.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
            List<List<String>> drained = stop.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
            check(drained.equals(Arrays.asList(
                    Arrays.asList("sample-1"), Arrays.asList("sample-1"))),
                    "STOP finalized before both offers completed: " + drained);
            check(local.isEmpty() && network.isEmpty(), "Sample stranded after drain");
        } finally {
            releaseCallback.countDown();
            finish(callbackThread);
            finish(stopThread);
        }
    }

    static void stopWaitsForEveryAdmittedCallback() throws Exception {
        SensorCallbackGate gate = new SensorCallbackGate();
        gate.open();
        check(gate.tryEnter(), "First callback was rejected");
        check(gate.tryEnter(), "Second callback was rejected");
        gate.close();
        FutureTask<Void> stop = new FutureTask<>(() -> {
            gate.awaitIdle();
            return null;
        });
        Thread stopThread = worker(stop, "test-two-callbacks");
        boolean firstExited = false;
        boolean secondExited = false;
        try {
            stopThread.start();
            assertWaitingForCallback(stopThread, stop);
            gate.exit();
            firstExited = true;
            assertWaitingForCallback(stopThread, stop);
            gate.exit();
            secondExited = true;
            stop.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
        } finally {
            if (!firstExited) {
                gate.exit();
            }
            if (!secondExited) {
                gate.exit();
            }
            finish(stopThread);
        }
    }

    static void aNewSessionCannotOpenOverAnUnfinishedCallback() {
        SensorCallbackGate gate = new SensorCallbackGate();
        check(!gate.tryEnter(), "Callback admitted before session start");
        gate.open();
        check(gate.tryEnter(), "Started session rejected its callback");
        gate.close();
        gate.close(); // Repeated closure must preserve the outstanding callback.
        boolean rejected = false;
        try {
            gate.open();
        } catch (IllegalStateException expected) {
            rejected = true;
        } finally {
            gate.exit();
        }
        check(rejected, "New session opened while an old callback was still active");
        gate.awaitIdle();
        gate.open();
        check(gate.tryEnter(), "New session was not admitted after the prior barrier");
        gate.exit();
        gate.close();
        gate.awaitIdle();
        check(!gate.tryEnter(), "Closed second session still accepts callbacks");
    }

    private static void assertWaitingForCallback(Thread thread, FutureTask<?> task) {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(TIMEOUT_SECONDS);
        while (!task.isDone() && thread.getState() != Thread.State.WAITING
                && System.nanoTime() < deadline) {
            Thread.yield();
        }
        check(!task.isDone(), "STOP drained while an admitted callback was paused");
        check(thread.getState() == Thread.State.WAITING,
                "STOP did not reach the callback barrier");
    }

    private static Thread worker(FutureTask<?> task, String name) {
        Thread thread = new Thread(task, name);
        thread.setDaemon(true); // A failing test must not pin the Gradle worker JVM.
        return thread;
    }

    private static void finish(Thread thread) throws InterruptedException {
        thread.join(TimeUnit.SECONDS.toMillis(TIMEOUT_SECONDS));
        if (thread.isAlive()) {
            thread.interrupt();
            throw new AssertionError("Test thread did not finish: " + thread.getName());
        }
    }

    private static void await(CountDownLatch latch, String message) throws InterruptedException {
        check(latch.await(TIMEOUT_SECONDS, TimeUnit.SECONDS), message);
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        stopWaitsBeforeEitherQueueReceivesTheAdmittedSample();
        stopWaitsBetweenLocalAndNetworkOffers();
        interruptionCannotBypassTheCallbackBarrier();
        stopWaitsForEveryAdmittedCallback();
        aNewSessionCannotOpenOverAnUnfinishedCallback();
        System.out.println("SensorCallbackGate: 5 behavioral scenarios passed");
    }
}
