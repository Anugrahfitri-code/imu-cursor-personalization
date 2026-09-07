package com.imucursor.research;

import android.os.SystemClock;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;


public final class ClockSyncServer {

    public static final int DEFAULT_PORT = 5006;

    private static final int BUFFER_SIZE = 1024;
    private static final int SOCKET_TIMEOUT_MS = 250;


    @FunctionalInterface
    public interface NanoClock {
        long nowNs();
    }


    private final int port;
    private final NanoClock nanoClock;


    private final AtomicLong validRequestCount =
            new AtomicLong();

    private final AtomicLong malformedRequestCount =
            new AtomicLong();

    private final AtomicLong sendErrorCount =
            new AtomicLong();


    private volatile boolean running = false;
    private volatile boolean ready = false;

    private volatile DatagramSocket socket;

    private volatile CountDownLatch readyLatch =
            new CountDownLatch(1);

    private Thread thread;


    public ClockSyncServer(
            int port
    ) {
        this(
                port,
                SystemClock::elapsedRealtimeNanos
        );
    }


    public ClockSyncServer(
            int port,
            NanoClock nanoClock
    ) {

        if (
                port <= 0
                        || port > 65535
        ) {
            throw new IllegalArgumentException(
                    "Port must be in 1..65535"
            );
        }

        if (nanoClock == null) {
            throw new IllegalArgumentException(
                    "NanoClock must not be null"
            );
        }

        this.port = port;
        this.nanoClock = nanoClock;
    }


    public synchronized void start() {

        if (running) {
            return;
        }

        ready = false;

        readyLatch =
                new CountDownLatch(1);

        running = true;

        thread =
                new Thread(
                        this::runLoop,
                        "ClockSyncServer"
                );

        thread.start();
    }


    public boolean awaitReady(
            long timeoutMs
    ) throws InterruptedException {

        if (timeoutMs <= 0) {
            throw new IllegalArgumentException(
                    "timeoutMs must be > 0"
            );
        }

        CountDownLatch latch =
                readyLatch;

        boolean signaled =
                latch.await(
                        timeoutMs,
                        TimeUnit.MILLISECONDS
                );

        return signaled
                && ready
                && running;
    }


    public synchronized void stop() {

        running = false;
        ready = false;

        DatagramSocket currentSocket =
                socket;

        if (currentSocket != null) {
            currentSocket.close();
        }

        Thread currentThread =
                thread;

        if (currentThread != null) {

            try {

                currentThread.join(
                        1500L
                );

            } catch (
                    InterruptedException e
            ) {

                Thread.currentThread()
                        .interrupt();
            }
        }

        thread = null;
        socket = null;
    }


    public boolean isRunning() {
        return running;
    }


    public boolean isReady() {
        return ready;
    }


    public long getValidRequestCount() {
        return validRequestCount.get();
    }


    public long getMalformedRequestCount() {
        return malformedRequestCount.get();
    }


    public long getSendErrorCount() {
        return sendErrorCount.get();
    }


    private void runLoop() {

        try (
                DatagramSocket localSocket =
                        new DatagramSocket(
                                port
                        )
        ) {

            socket = localSocket;

            localSocket.setSoTimeout(
                    SOCKET_TIMEOUT_MS
            );

            ready = true;

            readyLatch.countDown();


            byte[] buffer =
                    new byte[
                            BUFFER_SIZE
                            ];


            while (running) {

                DatagramPacket requestPacket =
                        new DatagramPacket(
                                buffer,
                                buffer.length
                        );


                try {

                    localSocket.receive(
                            requestPacket
                    );

                } catch (
                        SocketTimeoutException e
                ) {

                    continue;

                } catch (
                        SocketException e
                ) {

                    if (!running) {
                        break;
                    }

                    throw e;
                }


                long t2PhoneNs =
                        nanoClock.nowNs();


                String requestText =
                        new String(
                                requestPacket
                                        .getData(),
                                requestPacket
                                        .getOffset(),
                                requestPacket
                                        .getLength(),
                                StandardCharsets.UTF_8
                        );


                final ClockSyncProtocol.Request
                        request;


                try {

                    request =
                            ClockSyncProtocol
                                    .parseRequest(
                                            requestText
                                    );

                } catch (
                        IllegalArgumentException e
                ) {

                    malformedRequestCount
                            .incrementAndGet();

                    continue;
                }


                long t3PhoneNs =
                        nanoClock.nowNs();


                String responseText =
                        ClockSyncProtocol
                                .buildResponse(
                                        request,
                                        t2PhoneNs,
                                        t3PhoneNs
                                );


                byte[] responseBytes =
                        responseText.getBytes(
                                StandardCharsets.UTF_8
                        );


                DatagramPacket responsePacket =
                        new DatagramPacket(
                                responseBytes,
                                responseBytes.length,
                                requestPacket
                                        .getAddress(),
                                requestPacket
                                        .getPort()
                        );


                try {

                    localSocket.send(
                            responsePacket
                    );

                    validRequestCount
                            .incrementAndGet();

                } catch (
                        IOException e
                ) {

                    sendErrorCount
                            .incrementAndGet();
                }
            }

        } catch (
                IOException e
        ) {

            if (running) {
                sendErrorCount
                        .incrementAndGet();
            }

        } finally {

            ready = false;
            running = false;
            socket = null;

            readyLatch.countDown();
        }
    }
}