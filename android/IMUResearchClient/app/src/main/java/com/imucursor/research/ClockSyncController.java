package com.imucursor.research;

import android.util.Log;


public final class ClockSyncController {

    private static final String TAG =
            "ClockSyncController";

    private static final long READY_TIMEOUT_MS =
            1000L;


    private ClockSyncServer server;


    public synchronized void start() {

        if (
                server != null
                        && server.isRunning()
        ) {
            return;
        }

        ClockSyncServer newServer =
                new ClockSyncServer(
                        ClockSyncServer.DEFAULT_PORT
                );

        newServer.start();


        try {

            boolean ready =
                    newServer.awaitReady(
                            READY_TIMEOUT_MS
                    );

            if (!ready) {

                Log.e(
                        TAG,
                        "Clock sync server failed "
                                + "to become ready on UDP "
                                + ClockSyncServer.DEFAULT_PORT
                );

                newServer.stop();

                return;
            }

        } catch (
                InterruptedException e
        ) {

            Thread.currentThread()
                    .interrupt();

            newServer.stop();

            Log.e(
                    TAG,
                    "Interrupted while waiting "
                            + "for clock sync server",
                    e
            );

            return;
        }


        server = newServer;


        Log.i(
                TAG,
                "Clock sync server READY on UDP "
                        + ClockSyncServer.DEFAULT_PORT
        );
    }


    public synchronized void stop() {

        if (server == null) {
            return;
        }


        long valid =
                server
                        .getValidRequestCount();

        long malformed =
                server
                        .getMalformedRequestCount();

        long errors =
                server
                        .getSendErrorCount();


        server.stop();


        Log.i(
                TAG,
                "Clock sync server stopped"
                        + " valid="
                        + valid
                        + " malformed="
                        + malformed
                        + " sendErrors="
                        + errors
        );


        server = null;
    }


    public synchronized boolean isRunning() {

        return server != null
                && server.isRunning();
    }


    public synchronized boolean isReady() {

        return server != null
                && server.isReady();
    }


    public synchronized long getValidRequestCount() {

        if (server == null) {
            return 0L;
        }

        return server
                .getValidRequestCount();
    }


    public synchronized long getMalformedRequestCount() {

        if (server == null) {
            return 0L;
        }

        return server
                .getMalformedRequestCount();
    }


    public synchronized long getSendErrorCount() {

        if (server == null) {
            return 0L;
        }

        return server
                .getSendErrorCount();
    }
}