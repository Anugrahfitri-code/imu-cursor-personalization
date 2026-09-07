package com.imucursor.research;


public final class ClockSyncProtocol {

    public static final int VERSION = 1;


    private ClockSyncProtocol() {
        // Utility class.
    }


    public static final class Request {

        public final long seq;
        public final long t1PcNs;


        public Request(
                long seq,
                long t1PcNs
        ) {

            if (seq < 0) {
                throw new IllegalArgumentException(
                        "Negative sequence"
                );
            }

            if (t1PcNs < 0) {
                throw new IllegalArgumentException(
                        "Negative t1 timestamp"
                );
            }

            this.seq = seq;
            this.t1PcNs = t1PcNs;
        }
    }


    public static Request parseRequest(
            String message
    ) {

        if (message == null) {
            throw new IllegalArgumentException(
                    "Message must not be null"
            );
        }

        String[] parts =
                message.trim().split(
                        ",",
                        -1
                );

        if (parts.length != 4) {
            throw new IllegalArgumentException(
                    "Expected 4 fields"
            );
        }

        if (!"SYNC_REQ".equals(
                parts[0]
        )) {
            throw new IllegalArgumentException(
                    "Invalid message type"
            );
        }

        final int version;
        final long seq;
        final long t1PcNs;

        try {

            version =
                    Integer.parseInt(
                            parts[1]
                    );

            seq =
                    Long.parseLong(
                            parts[2]
                    );

            t1PcNs =
                    Long.parseLong(
                            parts[3]
                    );

        } catch (
                NumberFormatException e
        ) {

            throw new IllegalArgumentException(
                    "Numeric parse error",
                    e
            );
        }

        if (version != VERSION) {
            throw new IllegalArgumentException(
                    "Unsupported protocol version"
            );
        }

        return new Request(
                seq,
                t1PcNs
        );
    }


    public static String buildResponse(
            Request request,
            long t2PhoneNs,
            long t3PhoneNs
    ) {

        if (request == null) {
            throw new IllegalArgumentException(
                    "Request must not be null"
            );
        }

        if (t2PhoneNs < 0) {
            throw new IllegalArgumentException(
                    "Negative t2 timestamp"
            );
        }

        if (t3PhoneNs < 0) {
            throw new IllegalArgumentException(
                    "Negative t3 timestamp"
            );
        }

        if (t3PhoneNs < t2PhoneNs) {
            throw new IllegalArgumentException(
                    "t3 before t2"
            );
        }

        return "SYNC_RESP,"
                + VERSION
                + ","
                + request.seq
                + ","
                + request.t1PcNs
                + ","
                + t2PhoneNs
                + ","
                + t3PhoneNs;
    }
}