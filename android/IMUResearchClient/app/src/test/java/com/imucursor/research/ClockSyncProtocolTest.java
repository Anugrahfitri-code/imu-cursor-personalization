package com.imucursor.research;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.fail;


public class ClockSyncProtocolTest {

    @Test
    public void parseValidRequest() {

        ClockSyncProtocol.Request request =
                ClockSyncProtocol.parseRequest(
                        "SYNC_REQ,1,17,583021455812300"
                );

        assertEquals(
                17L,
                request.seq
        );

        assertEquals(
                583021455812300L,
                request.t1PcNs
        );
    }


    @Test
    public void rejectWrongFieldCount() {

        assertInvalidRequest(
                "SYNC_REQ,1,17"
        );
    }


    @Test
    public void rejectWrongMessageType() {

        assertInvalidRequest(
                "OTHER,1,17,100"
        );
    }


    @Test
    public void rejectWrongProtocolVersion() {

        assertInvalidRequest(
                "SYNC_REQ,2,17,100"
        );
    }


    @Test
    public void rejectNegativeSequence() {

        assertInvalidRequest(
                "SYNC_REQ,1,-1,100"
        );
    }


    @Test
    public void rejectNegativeT1Timestamp() {

        assertInvalidRequest(
                "SYNC_REQ,1,17,-100"
        );
    }


    @Test
    public void rejectNonNumericField() {

        assertInvalidRequest(
                "SYNC_REQ,1,abc,100"
        );
    }


    @Test
    public void buildResponseExactFormat() {

        ClockSyncProtocol.Request request =
                new ClockSyncProtocol.Request(
                        17L,
                        583021455812300L
                );

        String response =
                ClockSyncProtocol.buildResponse(
                        request,
                        62199451233120L,
                        62199451310455L
                );

        assertEquals(
                "SYNC_RESP,1,"
                        + "17,"
                        + "583021455812300,"
                        + "62199451233120,"
                        + "62199451310455",
                response
        );
    }


    @Test
    public void rejectT3BeforeT2() {

        ClockSyncProtocol.Request request =
                new ClockSyncProtocol.Request(
                        17L,
                        100L
                );

        try {

            ClockSyncProtocol.buildResponse(
                    request,
                    300L,
                    299L
            );

            fail(
                    "Expected IllegalArgumentException"
            );

        } catch (
                IllegalArgumentException expected
        ) {
            // Expected.
        }
    }


    private static void assertInvalidRequest(
            String message
    ) {

        try {

            ClockSyncProtocol.parseRequest(
                    message
            );

            fail(
                    "Expected IllegalArgumentException "
                            + "for message: "
                            + message
            );

        } catch (
                IllegalArgumentException expected
        ) {
            // Expected.
        }
    }
}