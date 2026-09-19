package com.imucursor.research;

import org.junit.Test;

public class SensorCallbackGateTest {
    @Test(timeout = 20000L)
    public void stopWaitsBeforeEitherQueueReceivesTheAdmittedSample() throws Exception {
        SensorCallbackGateScenarios.stopWaitsBeforeEitherQueueReceivesTheAdmittedSample();
    }

    @Test(timeout = 20000L)
    public void stopWaitsBetweenLocalAndNetworkOffers() throws Exception {
        SensorCallbackGateScenarios.stopWaitsBetweenLocalAndNetworkOffers();
    }

    @Test(timeout = 20000L)
    public void interruptionCannotBypassTheCallbackBarrier() throws Exception {
        SensorCallbackGateScenarios.interruptionCannotBypassTheCallbackBarrier();
    }

    @Test(timeout = 20000L)
    public void stopWaitsForEveryAdmittedCallback() throws Exception {
        SensorCallbackGateScenarios.stopWaitsForEveryAdmittedCallback();
    }

    @Test(timeout = 20000L)
    public void aNewSessionCannotOpenOverAnUnfinishedCallback() {
        SensorCallbackGateScenarios.aNewSessionCannotOpenOverAnUnfinishedCallback();
    }
}
