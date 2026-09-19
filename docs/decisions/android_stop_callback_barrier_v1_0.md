# Android STOP callback barrier v1.0

Status: bounded callback-barrier fix; laptop Android build/unit-test tasks passed,
and two device captures reconciled. Complete lifecycle qualification remains open.

Prepared for the user-reported branch `fix/android-stop-drain-v1.0` at
`dd2d7d8fd904668141f76f455a5d2a59c05c759a` (merge of PR #7).
The user applied both implementation and test-correction patches on that branch.
The laptop subsequently reported `git diff --check` exit code 0.

## Problem and behavior

The former `recording` flag only guarded callback entry. A callback could pass
that guard, pause, and offer a sample after STOP had already drained an empty
consumer queue. Unregistering the listener was not a completion acknowledgement
from that callback.

`SensorCallbackGate` now counts admitted callbacks. STOP closes admission,
unregisters the listener, then waits on `IMUStopThread` for all admitted callbacks
to exit before changing either consumer's running flag. The complete sample
handling path, including both queue offers, is covered by a `try/finally` release.
Opening and normal STOP admission transitions use the existing `stopLock`;
callbacks never acquire that lock. Waiting releases the gate's own monitor.

The STOP boundary is closure of callback admission. Previously admitted samples
may finish queueing after closure; later admissions are rejected until a new
session opens. `callback_elapsed_ns` is captured at callback entry before the
admission check. `session_stop_elapsed_ns` remains a stop boundary timestamp,
captured after admission closes, rather than a drain-completion timestamp.
CSV columns and UDP protocol version remain unchanged.

Failure-to-start cleanup and best-effort `onDestroy` cleanup also close admission
and await admitted callbacks before touching consumers or files. Those existing
emergency paths can block their caller; normal STOP waits on its worker thread.
An interrupted barrier continues waiting and restores interruption afterward.
There is no timeout that silently permits finalization over an active callback.

## Verification

Five real-thread/queue scenarios are shared between `SensorCallbackGateTest`
(JUnit) and the dependency-free `SensorCallbackGateScenarios.main` runner:

1. STOP while an admitted callback is paused before both queue offers.
2. STOP while paused between the local and network offers.
3. Interrupted STOP must wait again and preserve its interrupt status.
4. STOP must wait for all outstanding callbacks, not just the first exit.
5. A new session cannot open over an outstanding callback; reopening after
   completion works, and callbacks before start or after close are rejected.

Local Java 17 compilation with `--release 11` and execution of the shared
runner passed all five cases. The initial no-wait scaffold failed the paused
callback assertion. Separate mutations that return early on interruption,
omit admission closure, or allow reopening over an active callback also failed.
These are gate-level behavioral checks, not exhaustive Android lifecycle tests.

The first laptop build of `android-stop-drain-v1.0.patch` failed in
`:app:compileDebugUnitTestJavaWithJavac`: the test's `java.lang.management`
imports were unavailable to that compilation. The follow-up
`android-stop-drain-tests-v1.0.1.patch` removed those imports. The interruption
scenario now keeps the callback paused by a latch while checking that STOP
cannot complete within a one-second observation window. It then releases the
callback and checks completion and restored interrupt status. Production code
was unchanged by this correction.

The corrected shared runner also passed with compilation restricted to
`--release 11 --limit-modules java.base`. Mutants that skip waiting, return
early on interruption, or omit interrupt restoration failed the relevant cases.

### Laptop build and installation

User-supplied PowerShell output on 2026-09-19 records:

```powershell
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug --console=plain
```

- `BUILD SUCCESSFUL`; `ANDROID_BUILD_TEST_EXIT_CODE=0`.
- Unit-test compilation and `:app:testDebugUnitTest` executed.
- `adb install -r` returned `Success`; `APK_INSTALL_EXIT_CODE=0`.
- Patched APK SHA-256:
  `47E3274F816607C7DB7067ADEBB1DA3072836E8AD90D6C99E4A19B6FD0DE29A7`.

These are laptop-reported results. The Gradle console does not establish an
exact executed test count; no JUnit XML count is claimed here.

### Device capture evidence

Device: Samsung SM-A175F, Android 16 / API 36, STM LSM6DSVTR accelerometer and
gyroscope. The following results are from the previously inspected phone CSV,
metadata, and matching receiver CSV for each session.

| Measurement | Foreground STOP | Background/screen test case |
| --- | ---: | ---: |
| Session | `20260919_202318_560` | `20260919_203656_632` |
| Duration from phone metadata boundaries (s) | 30.693242155 | 120.304988391 |
| Local rows / PC rows / metadata UDP sent | 7670 / 7670 / 7670 | 30074 / 30074 / 30074 |
| ACC / GYRO rows | 3835 / 3835 | 15037 / 15037 |
| Missing / extra PC samples | 0 / 0 | 0 / 0 |
| PC duplicates / out-of-order samples | 0 / 0 | 0 / 0 |
| Shared payload mismatches | 0 | 0 |
| Final local / network queue remaining | 0 / 0 | 0 / 0 |
| Network queue drops / UDP send errors | 0 / 0 | 0 / 0 |
| Callback timestamps at or after STOP | 0 | 0 |
| Send timestamps at or after STOP | 0 | 1 |
| Last callback before STOP (ms) | 5.522846 | 0.210846 |
| Maximum PC inter-arrival gap (ms) | 90.8601 | 584.0546 |

All 37,744 samples across the two captures matched across the 11 shared payload
columns. XYZ values were compared numerically; other shared values were compared
exactly. Global and per-sensor sequences were contiguous. Both metadata files
reported `user_stop`. These captures support successful callback/queue
completion for the observed runs; they do not establish a race-failure rate or
prove all possible thread schedules safe.

For the background case, the final GYRO sample (global sequence 30074) has a
callback timestamp 0.210846 ms before STOP and a send timestamp 0.890385 ms after
STOP. This is consistent with sending an already admitted sample while draining.
The STOP timestamp is not a promise that all sends have completed. The send
timestamp records the phone's send attempt, not physical transmission on the wire.

The supplied background receiver console reported 30074 valid packets and zero
invalid packets. Its single post-STOP screenshot shows STOPPED, timer 00:02:00,
Total/UDP sent 30074, ACC/GYRO 15037 each, and zero drops/errors. START appears
enabled and STOP appears disabled. Stability of those values for ten seconds
after STOPPED has not been confirmed. Actual Home/screen-off/return transitions
were not independently recorded, so the case name and continuous sensor coverage
do not by themselves prove the screen-state schedule.

The largest PC gap, 584.0546 ms, is between global sequences 15546 and 15547.
The corresponding phone callback and send gaps are only 7.232923 ms and
6.931692 ms. The cause remains unresolved and needs separate investigation for
real-time cursor use. Independent phone and PC monotonic clocks were not mapped;
this inter-arrival gap is not a one-way latency measurement.

### Evidence locations on the laptop

Both case folders are under
`D:\IMU_Cursor_Research\bench_data\android_stop_validation\`.

Foreground folder: `a17_stop_fg_30s_fix_01`

- `imu_a17_stop_fg_30s_fix_01_20260919_202318_560.csv`
- `meta_a17_stop_fg_30s_fix_01_20260919_202318_560.txt`
- `udp_stream_20260919_202240.csv`

Background folder: `a17_bg_screen_2min_fix_01`

- `imu_a17_bg_screen_2min_fix_01_20260919_203656_632.csv`
- `meta_a17_bg_screen_2min_fix_01_20260919_203656_632.txt`
- `udp_stream_20260919_203614.csv`

The earlier foreground report,
`android_stop_fg_fix_01_validation_v1_0.json`, records 47 passing file-data checks.
Its statement that background evidence was pending reflects its earlier creation
time; the background results above supplement that historical report.

## Remaining audit work

This patch establishes producer completion before consumer shutdown. It does not
establish successful file persistence or successful termination of every worker.
Existing writer/metadata error reporting, worker join timeouts or interrupted
joins, duplicate emergency finalization, rapid restart versus pending `stopSelf`,
and STOP before a queued START still need separate fixes and qualification.
Unexpected service destruction remains best effort. No production-readiness or
complete lifecycle-safety claim follows from the gate scenarios or these two
successful device captures.
