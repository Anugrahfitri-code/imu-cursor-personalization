# Cursor Engineering Preview — Design Specification

**Project:** IMU Cursor Personalization  
**Date:** 2026-09-05  
**Status:** Design approved in conversation; implementation not started  
**Scope:** Engineering preview only, not experimental P0/P2C/L0/L2C

## 1. Purpose

Build a small PC-side engineering preview that lets a Samsung smartphone move a **virtual cursor inside a dedicated Pygame window** using the already-qualified Wi‑Fi UDP IMU stream.

This preview exists to verify:
- the smartphone can control a pointer in real time;
- the chosen remote-like holding posture is intuitive;
- axis direction/sign is correct;
- stationary behavior is stable enough for further work;
- stream loss/staleness does not create runaway cursor motion;
- the transport boundary can feed a later pointing-task system without modifying the frozen M2.2 validation receiver.

This preview must **not** be used for participant data collection, Fitts-law throughput estimation, confirmatory comparisons, or selection of final personalization parameters.

## 2. Scientific Boundary

The preview is **not P0**.

Preview mapping is a temporary engineering mapping:

```text
gyro → neutral-bias subtraction → dead-zone → fixed gain → cursor velocity
```

The later research baseline remains formally specified as:

```text
v_t = B_0 u_t + b_0
```

and the personalized parametric condition as:

```text
v_t = B_u u_t + b_u
```

Preview gain, dead-zone, axis signs, and subjective sensitivity settings do not automatically become parameters in the final experiment.

## 3. Transport Decision

Primary transport remains:

```text
Samsung → Wi‑Fi UDP protocol v1 → PC
```

Bluetooth is not added in this phase.

Reasons:
- Wi‑Fi UDP has already passed M2.1/M2.2 qualification.
- Adding Bluetooth would reopen the transport layer and create unnecessary scope.
- UDP is well suited to freshness-sensitive real-time pointer control.
- The final experiment should keep the transport fixed across P0/P2C/L0/L2C to avoid a transport confound.

The frozen validation receiver remains unchanged:

```text
pc/receiver/udp_receiver.py
```

The cursor preview must not run simultaneously with the validation receiver because both would bind to UDP port 5005.

## 4. Holding Posture

Use a **remote-like neutral posture**:
- smartphone screen generally faces upward;
- the top edge of the smartphone points toward the monitor;
- the hand is held comfortably, without forcing a precise mechanical angle;
- the device holds still for approximately 2 seconds before pointer activation.

This posture is an engineering convention for the preview. The posture and coordinate convention will be evaluated again before pilot/system freeze.

## 5. Initial Axis Mapping

Candidate preview mapping:

```text
gyro Z → horizontal cursor velocity
gyro X → vertical cursor velocity
gyro Y → unused
```

Axis signs are not assumed. They are verified by a direction sanity check:

```text
top edge right → cursor right
top edge left  → cursor left
top edge up    → cursor up
top edge down  → cursor down
```

Implementation shall use explicit constants:

```text
X_SIGN ∈ {-1, +1}
Y_SIGN ∈ {-1, +1}
```

so inversion does not require architectural changes.

## 6. Cursor Mapping

Use velocity control rather than absolute orientation.

For bias-corrected gyro values:

```text
g'_x = g_x - bias_x
g'_z = g_z - bias_z
```

Apply dead-zone independently:

```text
axis = 0, if |axis| < dead_zone
```

Then:

```text
v_x = X_SIGN × gain × g'_z
v_y = Y_SIGN × gain × g'_x
```

At each render/update frame:

```text
x_new = clamp(x_old + v_x × dt)
y_new = clamp(y_old + v_y × dt)
```

`dt` must be the actual elapsed frame time, not a fixed assumed 1/60 s.

## 7. Neutral Hold

State sequence:

```text
WAITING FOR IMU
→ HOLD STILL
→ READY
```

When a valid GYRO stream first becomes available:
1. collect gyro samples for ~2 seconds;
2. calculate mean gyro bias on X/Y/Z;
3. store that bias for the current preview session;
4. activate pointer movement.

`N` restarts the neutral-hold procedure.

Neutral hold is **not 2C calibration** and is not P2C personalization.

## 8. Dead-zone and Sensitivity

Initial dead-zone:

```text
0.03 rad/s
```

This is an engineering default only.

Sensitivity levels exposed in the UI:

```text
0.5×
1.0×
1.5×
2.0×
3.0×
```

Default:

```text
1.0×
```

Sensitivity is applied to a base gain expressed conceptually in pixels per radian.

No adaptive gain, acceleration curve, low-pass filter, prediction, or learned mapping is included in the first preview.

## 9. Stream Health and Fail-safe Behavior

The latest GYRO arrival time is used only for stream-health status.

Suggested thresholds:

```text
age < 250 ms       → STREAMING
250–1000 ms        → STALE
age > 1000 ms      → DISCONNECTED
```

When the stream is STALE or DISCONNECTED:

```text
cursor velocity = 0
```

The cursor must never continue moving using an old velocity during a network interruption.

When fresh packets resume, control may resume without restarting the application.

## 10. Pygame Window

Initial window:

```text
1200 × 700 px
target render/update rate: 60 Hz
```

The preview window contains:
- title;
- connection/status state;
- received packet count;
- latest gyro X/Y/Z;
- sensitivity level;
- dead-zone status;
- FPS;
- virtual cursor;
- optional central reference crosshair;
- compact keyboard-help text.

The virtual cursor is clamped to the window boundaries.

It does **not** move the Windows system cursor.

## 11. Controls

```text
R       recenter virtual cursor
N       redo neutral hold
↑ / ↓   increase/decrease sensitivity
D       toggle dead-zone
SPACE   freeze/unfreeze pointer motion
ESC     exit cleanly
```

No click action is included.

## 12. Proposed Source Structure

```text
pc/
└── cursor_preview/
    ├── cursor_preview.py
    ├── udp_input.py
    ├── imu_mapping.py
    └── tests/
        ├── test_udp_input.py
        └── test_imu_mapping.py
```

Responsibilities:

### `udp_input.py`
- bind UDP port 5005;
- parse protocol v1 DATA packets;
- accept GYRO packets for pointer state;
- expose latest gyro sample and stream-health information;
- run independently from Pygame rendering.

### `imu_mapping.py`
- neutral bias representation;
- dead-zone;
- axis sign;
- sensitivity/gain;
- velocity calculation;
- cursor integration/clamping;
- pure/testable mapping logic.

### `cursor_preview.py`
- Pygame window;
- application state machine;
- neutral-hold workflow;
- keyboard controls;
- fixed render/update loop;
- UI diagnostics;
- clean shutdown.

## 13. Internal Data Model

A preview-side gyro sample should contain at least:

```text
seq_global
sensor_ts_phone_ns
pc_receive_monotonic_ns
gx
gy
gz
```

The preview must preserve the original phone sensor timestamp even though M2.3 clock synchronization is not yet implemented.

## 14. Concurrency

UDP reception must not block the Pygame render loop.

Recommended design:

```text
UDP receiver thread
      ↓
thread-safe latest-sample state
      ↓
Pygame main/render loop
```

Use bounded/simple shared state rather than an unbounded queue.

The render loop uses the most recent available sample; it does not attempt to replay every UDP packet visually.

## 15. Error Handling

The preview should handle:
- malformed UDP packets → ignore and count;
- unsupported protocol version → ignore/count/report;
- port bind failure → clear startup error and exit;
- no IMU stream → remain in WAITING state;
- stale/disconnected stream → zero velocity;
- window close/ESC → close socket/thread and exit cleanly.

No silent fallback to a different transport.

## 16. Testing Strategy

Use TDD for pure logic and packet parsing.

Minimum automated tests:

### Mapping
- zero gyro → zero velocity;
- gyro inside dead-zone → zero velocity;
- horizontal gyro produces expected signed `v_x`;
- vertical gyro produces expected signed `v_y`;
- 2× sensitivity produces 2× velocity;
- displacement scales with `dt`;
- cursor clamps at every edge;
- stale stream forces zero motion.

### UDP Input
- valid protocol-v1 packet parses correctly;
- malformed field count is rejected;
- unsupported protocol version is rejected;
- GYRO packet updates latest gyro state;
- non-GYRO packet does not alter gyro pointer state.

Pygame rendering itself does not require heavy unit testing for this preview.

## 17. Manual Acceptance Criteria

Preview is engineering-qualified when all are observed:
1. Samsung stream is received in real time.
2. Neutral hold completes.
3. Right motion moves cursor right.
4. Left motion moves cursor left.
5. Up motion moves cursor up.
6. Down motion moves cursor down.
7. Holding still produces approximately stationary cursor behavior.
8. `R` recenters the cursor.
9. `N` restarts neutral calibration.
10. `SPACE` freezes/unfreezes motion.
11. Stream loss/staleness stops the cursor rather than allowing runaway motion.
12. Stream recovery resumes control.
13. `ESC` exits cleanly.

No Fitts throughput or participant-performance metrics are collected in this stage.

## 18. Git Workflow

Create from current `main` after M2.2 freeze:

```text
feature/cursor-engineering-preview
```

Suggested logical commits:

```text
1. Add tested IMU-to-cursor mapping
2. Add UDP input adapter for cursor preview
3. Add Pygame virtual cursor engineering preview
```

After automated tests and manual acceptance pass:

```text
feature/cursor-engineering-preview
→ Pull Request
→ main
```

Do not modify or retag `m2.2-reliability-freeze`.

## 19. Exit Condition and Next Phase

Successful preview does not freeze final pointing behavior.

After this preview:

```text
Cursor Engineering Preview
→ M2.3 Clock Synchronization
→ M2.4 Latency/Jitter Characterization
→ M3 P0 + 2C + P2C + Fitts UI
```

Any mapping parameters observed during preview remain engineering-only until the appropriate pilot/system freeze.
