# Smartphone IMU Cursor Personalization

Research prototype for investigating personalized free-space cursor control using smartphone inertial sensors.

The project studies whether short user calibration can improve smartphone-motion cursor control and whether a temporal learned controller provides practically meaningful HCI benefits over a simpler low-dimensional parametric controller.

## Research Scope

The planned human evaluation compares four cursor-control conditions:

- **P0** — global parametric controller without computational personalization from the user's 2C calibration;
- **P2C** — low-dimensional parametric controller personalized using the user's 2C calibration;
- **L0** — global temporal learned controller;
- **L2C** — temporal learned controller with parameter-efficient user-specific latent adaptation.

The primary HCI outcome is planned to be sequence-level **Fitts-law throughput** in a controlled free-space pointing task.

The temporal learned branch is planned around a causal Conv1D-family model. The learned model and human-study stages are not yet frozen.

## Research Design Boundary

The study is designed as an end-to-end comparison between system families rather than as a claim that personalization itself is novel.

The core comparisons are planned as:

```text
RQ1:
P2C vs P0
→ benefit of short parametric personalization

RQ2:
L2C vs P2C
→ whether the added temporal learned/deep-learning complexity
  provides practically meaningful HCI benefit under matched
  user calibration burden

RQ3:
L2C vs L0
+ differential personalization gain
+ performance / adaptation / complexity / latency trade-offs
```

The matched user calibration is referred to as **2C** and is intended to use the same calibration episode, duration, and raw recording for the parametric and learned personalized branches.

## Current Engineering Status

### M0 — Device and Sensor Validation

**PASS on engineering-development device**

Development device:

- Samsung SM-A066B
- Android 16
- Bosch `bmi3xy acc`
- Bosch `bmi3xy gyro`

The original Oppo candidate was rejected because its reported gyroscope was a virtual/pseudo gyro.

### M1 — Sensor Acquisition

**PASS / FROZEN**

Validated characteristics include:

- `SensorEvent.timestamp` preserved as the primary sensor timestamp;
- accelerometer XYZ logging;
- gyroscope XYZ logging;
- global and per-sensor sequence numbers;
- callback monotonic timestamp logging;
- asynchronous local writer;
- metadata logging;
- requested sampling period of 10,000 µs (~100 Hz);
- local validation archive.

M1 freeze tag:

```text
m1-sensor-freeze
```

### M2.1 — Real-Time UDP Streaming

**PASS**

The Android acquisition path streams IMU DATA to the PC using UDP protocol v1.

Primary IMU transport:

```text
Android
→ UDP 5005
→ PC
```

The frozen DATA protocol preserves sensor timestamps and sequence numbers rather than substituting PC arrival time for sensor time.

### M2.2 — UDP Reliability

**ENGINEERING FREEZE COMPLETED on Samsung SM-A066B**

Reliability work included:

- exact sequence accounting;
- loss detection;
- duplicate detection;
- out-of-order detection;
- longest missing-burst calculation;
- Android sender queue/drop/error diagnostics;
- multi-duration bench characterization.

M2.2 freeze tag:

```text
m2.2-reliability-freeze
```

The Samsung SM-A066B results remain engineering-development evidence.

### Cursor Engineering Preview

**IMPLEMENTED**

A Pygame virtual-cursor preview is available for engineering use.

It is not a participant experiment and is not one of the final P0/P2C/L0/L2C evaluation conditions.

The preview currently provides an engineering path for validating:

- smartphone orientation assumptions;
- gyro-axis mapping;
- cursor direction signs;
- dead-zone behavior;
- sensitivity/gain behavior;
- UDP input handling;
- stale-data behavior.

### M2.3 — Clock Synchronization

**IMPLEMENTED THROUGH M2.3-R1 — FINAL FREEZE PENDING**

Clock synchronization uses a dedicated control path:

```text
PC
→ UDP 5006
→ Android

PC
← UDP 5006
← Android
```

Clock domains:

```text
Android:
SystemClock.elapsedRealtimeNanos()

PC:
time.monotonic_ns()
```

The model is:

```text
t_PC = alpha * t_phone + beta
```

M2.3-R1 background synchronization uses:

```text
30 startup probes @ 50 ms

background:
5 probes @ 50 ms
every 10 s

30 shutdown probes @ 50 ms
```

For each scheduled background microburst, one minimum-delay valid probe is selected using scheduled probe-sequence identity.

The affine model uses centered ordinary least squares with an intercept and fixed residual-MAD screening.

Engineering characterization has been completed on the Samsung SM-A066B for valid 2-minute and 10-minute R1 runs.

Example 10-minute engineering result:

```text
valid responses : 360 / 360
response rate   : 100%

skew_ppm        : -12.466825

absolute residual:
P50             : 0.249263 ms
P95             : 0.916532 ms
max             : 1.480909 ms

first-half skew : -10.832414 ppm
second-half skew: -12.499537 ppm
```

These values are engineering observations from the development device, not universal acceptance thresholds.

M2.3 is **not yet tagged as frozen** because the final research smartphone is being changed.

## Final Research Device Transition

The Samsung SM-A066B is retained as the **engineering-development device**.

The candidate final research device is:

```text
Samsung Galaxy A17 4G
```

The A17 has **not yet been qualified** in this repository.

Before participant work begins, the A17 must repeat device-dependent qualification:

```text
M0
→ sensor/device qualification

M1
→ acquisition rate and timestamp validation

M2.1
→ UDP smoke verification

M2.2
→ reliability characterization

M2.3
→ 2 / 10 / 25 minute clock-sync qualification

→ timing-quality thresholds frozen

→ final engineering freeze
```

Historical A06 results will not be silently treated as A17 qualification evidence.

The intention is to use one final smartphone model consistently for pilot and evaluation participants in order to avoid device-related confounding.

## Timing Boundary

The project distinguishes sensor timestamps from packet-arrival timestamps.

PC receive time must not replace Android sensor time.

Clock synchronization exists to map Android monotonic timing into the PC monotonic domain.

Instrumented latency components may later include:

- phone callback delay;
- phone send delay;
- transport/scheduling age;
- PC preprocessing time;
- model-inference time;
- cursor-update timing.

The project does **not** claim sensor-to-photon latency without appropriate display-side instrumentation.

## Human-Study Boundary

No final participant experiment should begin until:

- the Samsung A17 4G is qualified;
- the final acquisition/transport/timing configuration is frozen;
- applicable institutional/ethics requirements are satisfied;
- pilot protocol is finalized;
- statistical analysis rules are documented.

The current design targets:

```text
active smartphone pointing ≤ 10 minutes
```

within a longer session that may also contain explanation, calibration, breaks, and transitions.

## Repository Structure

```text
android/
└── IMUResearchClient/
    └── Android IMU acquisition,
        UDP DATA streaming,
        and clock-sync responder

pc/
├── receiver/
│   └── UDP IMU receiver and reliability accounting
│
├── cursor_preview/
│   └── engineering-only virtual cursor preview
│
└── clock_sync/
    ├── protocol.py
    ├── sync_client.py
    ├── clock_model.py
    ├── analyze_sync.py
    └── tests/

docs/
└── superpowers/
    ├── specs/
    └── plans/

validation_archive/
└── M1_SENSOR_FREEZE/
```

## Runtime Data Policy

Runtime and participant-sensitive data are intentionally excluded from Git.

Examples include:

```text
bench_data/
pc/receiver/logs/
participant_data/
data/participants/
```

The repository is intended to contain source code, tests, engineering specifications, implementation plans, and selected non-participant validation evidence.

## Research Status

This repository is under active research and engineering development.

Current high-level sequence:

```text
M0–M2.2 engineering foundation
        ↓
M2.3 clock synchronization
        ↓
Samsung A17 4G qualification
        ↓
final timing / transport freeze
        ↓
pointing-task implementation
        ↓
P0 / P2C
        ↓
L0 / L2C temporal learned branch
        ↓
pilot
        ↓
independent human evaluation
        ↓
statistical analysis
        ↓
manuscript
```

No final human-participant dataset is included in this repository.

## Publication

The project is being developed as an empirical HCI / intelligent-system study.

Publication claims will be based on completed experimental evidence rather than engineering-preview behavior alone.