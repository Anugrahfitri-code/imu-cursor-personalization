package com.imucursor.research;

import org.junit.Test;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;


public class ClockSyncServerTest {

    @Test
    public void validRequestGetsTimestampedResponse()
            throws Exception {

        int port = findFreeUdpPort();

        AtomicLong clock =
                new AtomicLong(
                        1_000_000L
                );

        ClockSyncServer server =
                new ClockSyncServer(
                        port,
                        () -> clock.getAndAdd(
                                100L
                        )
                );

        DatagramSocket client = null;

        try {
            server.start();

            assertTrue(
                    "Server did not become ready",
                    server.awaitReady(
                            1000L
                    )
            );

            assertTrue(
                    server.isRunning()
            );

            client =
                    new DatagramSocket();

            client.setSoTimeout(
                    1000
            );

            send(
                    client,
                    port,
                    "SYNC_REQ,1,17,"
                            + "583021455812300"
            );

            String response =
                    receive(client);

            waitForValidCount(
                    server,
                    1L
            );

            assertEquals(
                    "SYNC_RESP,1,"
                            + "17,"
                            + "583021455812300,"
                            + "1000000,"
                            + "1000100",
                    response
            );

            assertEquals(
                    1L,
                    server
                            .getValidRequestCount()
            );

            assertEquals(
                    0L,
                    server
                            .getMalformedRequestCount()
            );

            assertEquals(
                    0L,
                    server
                            .getSendErrorCount()
            );

        } finally {

            if (client != null) {
                client.close();
            }

            server.stop();
        }
    }


    @Test
    public void malformedRequestDoesNotKillServer()
            throws Exception {

        int port = findFreeUdpPort();

        AtomicLong clock =
                new AtomicLong(
                        2_000_000L
                );

        ClockSyncServer server =
                new ClockSyncServer(
                        port,
                        () -> clock.getAndAdd(
                                100L
                        )
                );

        DatagramSocket client = null;

        try {
            server.start();

            assertTrue(
                    "Server did not become ready",
                    server.awaitReady(
                            1000L
                    )
            );

            assertTrue(
                    server.isRunning()
            );

            client =
                    new DatagramSocket();

            client.setSoTimeout(
                    1000
            );

            /*
             * Malformed packet still consumes
             * t2 because t2 is intentionally
             * captured immediately after receive
             * and before request parsing.
             */
            send(
                    client,
                    port,
                    "THIS_IS_NOT_A_VALID_REQUEST"
            );

            waitForMalformedCount(
                    server,
                    1L
            );

            /*
             * Only send valid request after
             * malformed request is known to have
             * been processed. This makes the
             * deterministic fake-clock sequence
             * unambiguous.
             */
            send(
                    client,
                    port,
                    "SYNC_REQ,1,21,9000"
            );

            String response =
                    receive(client);

            waitForValidCount(
                    server,
                    1L
            );

            /*
             * Fake-clock sequence:
             *
             * malformed:
             * t2 = 2000000
             *
             * valid:
             * t2 = 2000100
             * t3 = 2000200
             */
            assertEquals(
                    "SYNC_RESP,1,"
                            + "21,"
                            + "9000,"
                            + "2000100,"
                            + "2000200",
                    response
            );

            assertEquals(
                    1L,
                    server
                            .getMalformedRequestCount()
            );

            assertEquals(
                    1L,
                    server
                            .getValidRequestCount()
            );

            assertEquals(
                    0L,
                    server
                            .getSendErrorCount()
            );

            assertTrue(
                    server.isRunning()
            );

        } finally {

            if (client != null) {
                client.close();
            }

            server.stop();
        }
    }


    @Test
    public void stopTerminatesServerCleanly()
            throws Exception {

        int port = findFreeUdpPort();

        ClockSyncServer server =
                new ClockSyncServer(
                        port,
                        System::nanoTime
                );

        server.start();

        assertTrue(
                "Server did not become ready",
                server.awaitReady(
                        1000L
                )
        );

        assertTrue(
                server.isRunning()
        );

        server.stop();

        assertFalse(
                server.isRunning()
        );

        /*
         * stop() must remain safe if called
         * repeatedly by Android lifecycle
         * cleanup.
         */
        server.stop();

        assertFalse(
                server.isRunning()
        );
    }


    private static void waitForMalformedCount(
            ClockSyncServer server,
            long expected
    ) throws Exception {

        long deadline =
                System.nanoTime()
                        + 1_000_000_000L;

        while (
                server
                        .getMalformedRequestCount()
                        < expected
        ) {

            if (
                    System.nanoTime()
                            >= deadline
            ) {

                throw new AssertionError(
                        "Timed out waiting for "
                                + "malformed request count "
                                + expected
                                + ", actual="
                                + server
                                .getMalformedRequestCount()
                );
            }

            Thread.sleep(
                    1L
            );
        }
    }


    private static void waitForValidCount(
            ClockSyncServer server,
            long expected
    ) throws Exception {

        long deadline =
                System.nanoTime()
                        + 1_000_000_000L;

        while (
                server
                        .getValidRequestCount()
                        < expected
        ) {

            if (
                    System.nanoTime()
                            >= deadline
            ) {

                throw new AssertionError(
                        "Timed out waiting for "
                                + "valid request count "
                                + expected
                                + ", actual="
                                + server
                                .getValidRequestCount()
                );
            }

            Thread.sleep(
                    1L
            );
        }
    }


    private static int findFreeUdpPort()
            throws Exception {

        try (
                DatagramSocket socket =
                        new DatagramSocket(0)
        ) {

            return socket
                    .getLocalPort();
        }
    }


    private static void send(
            DatagramSocket socket,
            int port,
            String message
    ) throws Exception {

        byte[] bytes =
                message.getBytes(
                        StandardCharsets.UTF_8
                );

        DatagramPacket packet =
                new DatagramPacket(
                        bytes,
                        bytes.length,
                        InetAddress.getByName(
                                "127.0.0.1"
                        ),
                        port
                );

        socket.send(
                packet
        );
    }


    private static String receive(
            DatagramSocket socket
    ) throws Exception {

        byte[] buffer =
                new byte[1024];

        DatagramPacket packet =
                new DatagramPacket(
                        buffer,
                        buffer.length
                );

        socket.receive(
                packet
        );

        return new String(
                packet.getData(),
                packet.getOffset(),
                packet.getLength(),
                StandardCharsets.UTF_8
        );
    }
}