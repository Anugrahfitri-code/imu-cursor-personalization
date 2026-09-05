# Cursor Engineering Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PC-side Pygame engineering preview where the qualified Samsung IMU UDP stream moves a virtual cursor using a temporary gyro-velocity mapping without changing the frozen M2.2 receiver.

**Architecture:** A dedicated `pc/cursor_preview` package owns three isolated responsibilities: pure IMU-to-cursor math in `imu_mapping.py`, non-blocking UDP protocol-v1 ingestion in `udp_input.py`, and the Pygame application/state machine in `cursor_preview.py`. The UDP receiver thread publishes only the latest GYRO sample into thread-safe shared state; the Pygame loop reads that state at 60 Hz, performs neutral-bias correction, dead-zone/gain mapping, staleness checks, and cursor integration.

**Tech Stack:** Python 3.13, standard library (`socket`, `threading`, `dataclasses`, `time`, `statistics`), pytest 9.x, Pygame 2.x.

**Spec:** `docs/superpowers/specs/2026-09-05-cursor-engineering-preview-design.md`

## Global Constraints

- Keep Wi‑Fi UDP protocol v1 as the only transport in this phase.
- Do not modify `pc/receiver/udp_receiver.py` or the `m2.2-reliability-freeze` tag.
- Do not run the preview simultaneously with `udp_receiver.py`; both bind UDP port `5005`.
- Preview window is `1200 × 700` with a target render/update rate of `60 Hz`.
- Initial engineering mapping is `gyro Z → horizontal velocity`, `gyro X → vertical velocity`, `gyro Y → unused`.
- Axis signs are explicit constants and may be inverted after manual direction sanity checking.
- Initial dead-zone is `0.03 rad/s`.
- Sensitivity levels are exactly `0.5×, 1.0×, 1.5×, 2.0×, 3.0×`; default is `1.0×`.
- Neutral hold is approximately `2 seconds` and is not 2C calibration.
- Stream health thresholds are `<250 ms = STREAMING`, `250–1000 ms = STALE`, `>1000 ms = DISCONNECTED`.
- STALE or DISCONNECTED state must force cursor velocity to zero.
- No click action, Fitts target, P0/P2C/L0/L2C logic, participant logging, smoothing, prediction, adaptive gain, or Windows system-cursor control.
- Use TDD for mapping and UDP input behavior.
- Runtime bench/preview data must not be committed.

---

## File Map

Create the following focused package:

```text
pc/
└── cursor_preview/
    ├── __init__.py
    ├── requirements.txt
    ├── imu_mapping.py
    ├── udp_input.py
    ├── cursor_preview.py
    └── tests/
        ├── __init__.py
        ├── test_imu_mapping.py
        └── test_udp_input.py
```

Responsibilities:

- `imu_mapping.py`: pure math and neutral-bias estimator; no socket, no Pygame, no global mutable runtime state.
- `udp_input.py`: protocol-v1 parser, latest-GYRO thread-safe state, UDP receiver thread, stream-age/status helpers.
- `cursor_preview.py`: Pygame UI, neutral-hold application state, keyboard controls, 60 Hz rendering, clean shutdown.
- `requirements.txt`: Pygame dependency only.
- Tests: exercise mapping and UDP input independently from Pygame.

---

### Task 1: Pure IMU Mapping and Neutral Bias

**Files:**
- Create: `pc/cursor_preview/__init__.py`
- Create: `pc/cursor_preview/imu_mapping.py`
- Create: `pc/cursor_preview/tests/__init__.py`
- Create: `pc/cursor_preview/tests/test_imu_mapping.py`

**Interfaces:**
- Produces:
  - `apply_dead_zone(value: float, threshold: float, enabled: bool = True) -> float`
  - `gyro_to_velocity(gx: float, gz: float, *, bias_x: float, bias_z: float, gain: float, x_sign: int, y_sign: int, dead_zone: float, dead_zone_enabled: bool = True) -> tuple[float, float]`
  - `integrate_cursor(x: float, y: float, vx: float, vy: float, dt: float, width: int, height: int) -> tuple[float, float]`
  - `NeutralBiasEstimator(duration_s: float = 2.0)`
  - `NeutralBiasEstimator.add_sample(t_monotonic_s: float, gx: float, gy: float, gz: float) -> None`
  - `NeutralBiasEstimator.ready(current_time_s: float) -> bool`
  - `NeutralBiasEstimator.bias() -> tuple[float, float, float]`
  - `NeutralBiasEstimator.reset() -> None`
- Consumes: standard library only.

- [ ] **Step 1: Create package markers**

Create empty files:

```python
# pc/cursor_preview/__init__.py
```

```python
# pc/cursor_preview/tests/__init__.py
```

- [ ] **Step 2: Write failing mapping tests**

Create `pc/cursor_preview/tests/test_imu_mapping.py`:

```python
import math

import pytest

from pc.cursor_preview.imu_mapping import (
    NeutralBiasEstimator,
    apply_dead_zone,
    gyro_to_velocity,
    integrate_cursor,
)


def test_zero_gyro_produces_zero_velocity():
    vx, vy = gyro_to_velocity(
        0.0,
        0.0,
        bias_x=0.0,
        bias_z=0.0,
        gain=500.0,
        x_sign=1,
        y_sign=1,
        dead_zone=0.03,
    )
    assert vx == 0.0
    assert vy == 0.0


def test_dead_zone_suppresses_small_motion():
    assert apply_dead_zone(0.02, 0.03, True) == 0.0
    assert apply_dead_zone(-0.02, 0.03, True) == 0.0
    assert apply_dead_zone(0.04, 0.03, True) == pytest.approx(0.04)


def test_horizontal_gyro_z_maps_to_vx_with_sign():
    vx, vy = gyro_to_velocity(
        gx=0.0,
        gz=0.2,
        bias_x=0.0,
        bias_z=0.0,
        gain=500.0,
        x_sign=-1,
        y_sign=1,
        dead_zone=0.03,
    )
    assert vx == pytest.approx(-100.0)
    assert vy == 0.0


def test_vertical_gyro_x_maps_to_vy_with_sign():
    vx, vy = gyro_to_velocity(
        gx=0.2,
        gz=0.0,
        bias_x=0.0,
        bias_z=0.0,
        gain=500.0,
        x_sign=1,
        y_sign=-1,
        dead_zone=0.03,
    )
    assert vx == 0.0
    assert vy == pytest.approx(-100.0)


def test_double_gain_doubles_velocity():
    args = dict(
        gx=0.2,
        gz=0.3,
        bias_x=0.0,
        bias_z=0.0,
        x_sign=1,
        y_sign=1,
        dead_zone=0.03,
    )
    vx1, vy1 = gyro_to_velocity(gain=250.0, **args)
    vx2, vy2 = gyro_to_velocity(gain=500.0, **args)

    assert vx2 == pytest.approx(2.0 * vx1)
    assert vy2 == pytest.approx(2.0 * vy1)


def test_bias_is_subtracted_before_dead_zone():
    vx, vy = gyro_to_velocity(
        gx=0.11,
        gz=0.21,
        bias_x=0.10,
        bias_z=0.20,
        gain=500.0,
        x_sign=1,
        y_sign=1,
        dead_zone=0.03,
    )
    assert vx == 0.0
    assert vy == 0.0


def test_integrate_cursor_scales_with_dt():
    p1 = integrate_cursor(100.0, 100.0, 50.0, -25.0, 0.1, 1200, 700)
    p2 = integrate_cursor(100.0, 100.0, 50.0, -25.0, 0.2, 1200, 700)

    assert p1 == pytest.approx((105.0, 97.5))
    assert p2 == pytest.approx((110.0, 95.0))


def test_integrate_cursor_clamps_to_window_edges():
    assert integrate_cursor(1195.0, 695.0, 100.0, 100.0, 1.0, 1200, 700) == (
        1200.0,
        700.0,
    )
    assert integrate_cursor(5.0, 5.0, -100.0, -100.0, 1.0, 1200, 700) == (
        0.0,
        0.0,
    )


def test_neutral_bias_estimator_uses_mean_after_duration():
    est = NeutralBiasEstimator(duration_s=2.0)

    est.add_sample(10.0, 0.10, -0.20, 0.30)
    est.add_sample(11.0, 0.20, -0.10, 0.40)
    est.add_sample(12.0, 0.30, 0.00, 0.50)

    assert est.ready(11.99) is False
    assert est.ready(12.0) is True

    bx, by, bz = est.bias()
    assert bx == pytest.approx(0.20)
    assert by == pytest.approx(-0.10)
    assert bz == pytest.approx(0.40)


def test_neutral_bias_reset_clears_previous_samples():
    est = NeutralBiasEstimator(duration_s=2.0)
    est.add_sample(10.0, 1.0, 2.0, 3.0)
    est.reset()

    assert est.ready(20.0) is False
    with pytest.raises(RuntimeError, match="bias is not ready"):
        est.bias()
```

- [ ] **Step 3: Run mapping tests and verify RED**

From repository root:

```powershell
python -m pytest pc/cursor_preview/tests/test_imu_mapping.py -v
```

Expected: collection/import FAIL because `pc.cursor_preview.imu_mapping` does not exist yet.

- [ ] **Step 4: Implement the minimal pure mapping module**

Create `pc/cursor_preview/imu_mapping.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import fmean


def apply_dead_zone(
    value: float,
    threshold: float,
    enabled: bool = True,
) -> float:
    if threshold < 0:
        raise ValueError("dead-zone threshold must be >= 0")

    if enabled and abs(value) < threshold:
        return 0.0

    return value


def gyro_to_velocity(
    gx: float,
    gz: float,
    *,
    bias_x: float,
    bias_z: float,
    gain: float,
    x_sign: int,
    y_sign: int,
    dead_zone: float,
    dead_zone_enabled: bool = True,
) -> tuple[float, float]:
    if x_sign not in (-1, 1):
        raise ValueError("x_sign must be -1 or +1")
    if y_sign not in (-1, 1):
        raise ValueError("y_sign must be -1 or +1")
    if gain < 0:
        raise ValueError("gain must be >= 0")

    corrected_x = apply_dead_zone(
        gx - bias_x,
        dead_zone,
        dead_zone_enabled,
    )
    corrected_z = apply_dead_zone(
        gz - bias_z,
        dead_zone,
        dead_zone_enabled,
    )

    vx = float(x_sign) * gain * corrected_z
    vy = float(y_sign) * gain * corrected_x
    return vx, vy


def integrate_cursor(
    x: float,
    y: float,
    vx: float,
    vy: float,
    dt: float,
    width: int,
    height: int,
) -> tuple[float, float]:
    if dt < 0:
        raise ValueError("dt must be >= 0")
    if width <= 0 or height <= 0:
        raise ValueError("window dimensions must be > 0")

    new_x = min(float(width), max(0.0, x + vx * dt))
    new_y = min(float(height), max(0.0, y + vy * dt))
    return new_x, new_y


@dataclass
class NeutralBiasEstimator:
    duration_s: float = 2.0
    _start_time_s: float | None = None
    _gx: list[float] = field(default_factory=list)
    _gy: list[float] = field(default_factory=list)
    _gz: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.duration_s <= 0:
            raise ValueError("duration_s must be > 0")

    def add_sample(
        self,
        t_monotonic_s: float,
        gx: float,
        gy: float,
        gz: float,
    ) -> None:
        if self._start_time_s is None:
            self._start_time_s = t_monotonic_s

        self._gx.append(gx)
        self._gy.append(gy)
        self._gz.append(gz)

    def ready(self, current_time_s: float) -> bool:
        if self._start_time_s is None or not self._gx:
            return False

        return (
            current_time_s - self._start_time_s
            >= self.duration_s
        )

    def bias(self) -> tuple[float, float, float]:
        if not self._gx:
            raise RuntimeError("bias is not ready")

        return (
            fmean(self._gx),
            fmean(self._gy),
            fmean(self._gz),
        )

    def reset(self) -> None:
        self._start_time_s = None
        self._gx.clear()
        self._gy.clear()
        self._gz.clear()
```

- [ ] **Step 5: Run mapping tests and verify GREEN**

```powershell
python -m pytest pc/cursor_preview/tests/test_imu_mapping.py -v
```

Expected: `10 passed`.

- [ ] **Step 6: Commit Task 1**

```powershell
git add pc/cursor_preview/__init__.py `
        pc/cursor_preview/imu_mapping.py `
        pc/cursor_preview/tests/__init__.py `
        pc/cursor_preview/tests/test_imu_mapping.py

git commit -m "Add tested IMU-to-cursor mapping"
```

---

### Task 2: UDP Protocol-v1 Input Adapter and Stream Health

**Files:**
- Create: `pc/cursor_preview/udp_input.py`
- Create: `pc/cursor_preview/tests/test_udp_input.py`

**Interfaces:**
- Consumes: UDP protocol-v1 DATA packets emitted by the Android application.
- Produces:
  - `GyroSample`
  - `parse_data_packet(message: str, pc_receive_monotonic_ns: int) -> GyroSample | None`
  - `stream_status(age_s: float | None) -> str`
  - `LatestGyroState`
  - `LatestGyroState.update(sample: GyroSample) -> None`
  - `LatestGyroState.snapshot() -> GyroSnapshot`
  - `UdpGyroReceiver(host: str = "0.0.0.0", port: int = 5005)`
  - `UdpGyroReceiver.start() -> None`
  - `UdpGyroReceiver.stop() -> None`
  - `UdpGyroReceiver.state: LatestGyroState`

- [ ] **Step 1: Write failing UDP parser/state tests**

Create `pc/cursor_preview/tests/test_udp_input.py`:

```python
import time

import pytest

from pc.cursor_preview.udp_input import (
    GyroSample,
    LatestGyroState,
    parse_data_packet,
    stream_status,
)


VALID_GYRO = (
    "DATA,1,20260905_120734_878,m2_preview,42,21,GYRO,"
    "55023193819033,55023194819033,55023195000000,"
    "0.1,-0.2,0.3,3"
)

VALID_ACC = (
    "DATA,1,20260905_120734_878,m2_preview,43,22,ACC,"
    "55023193829033,55023194919033,55023195100000,"
    "1.0,2.0,3.0,3"
)


def test_valid_gyro_packet_parses_to_sample():
    sample = parse_data_packet(
        VALID_GYRO,
        pc_receive_monotonic_ns=123456789,
    )

    assert sample == GyroSample(
        seq_global=42,
        sensor_ts_phone_ns=55023193819033,
        pc_receive_monotonic_ns=123456789,
        gx=0.1,
        gy=-0.2,
        gz=0.3,
    )


def test_non_gyro_packet_returns_none():
    assert parse_data_packet(
        VALID_ACC,
        pc_receive_monotonic_ns=123,
    ) is None


def test_malformed_packet_is_rejected():
    with pytest.raises(ValueError, match="14 fields"):
        parse_data_packet(
            "DATA,1,too,few,fields",
            pc_receive_monotonic_ns=123,
        )


def test_unsupported_protocol_version_is_rejected():
    message = VALID_GYRO.replace("DATA,1,", "DATA,2,", 1)

    with pytest.raises(ValueError, match="protocol version"):
        parse_data_packet(
            message,
            pc_receive_monotonic_ns=123,
        )


def test_latest_state_uses_newest_gyro_sample():
    state = LatestGyroState()

    first = GyroSample(10, 1000, 2000, 0.1, 0.2, 0.3)
    second = GyroSample(11, 1100, 2100, 0.4, 0.5, 0.6)

    state.update(first)
    state.update(second)

    snapshot = state.snapshot()

    assert snapshot.sample == second
    assert snapshot.packet_count == 2


def test_stream_status_thresholds():
    assert stream_status(None) == "WAITING"
    assert stream_status(0.249) == "STREAMING"
    assert stream_status(0.250) == "STALE"
    assert stream_status(1.000) == "STALE"
    assert stream_status(1.001) == "DISCONNECTED"
```

- [ ] **Step 2: Run UDP tests and verify RED**

```powershell
python -m pytest pc/cursor_preview/tests/test_udp_input.py -v
```

Expected: import FAIL because `pc.cursor_preview.udp_input` does not exist.

- [ ] **Step 3: Implement the parser, thread-safe state, and receiver thread**

Create `pc/cursor_preview/udp_input.py`:

```python
from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass


EXPECTED_PROTOCOL_VERSION = 1
BUFFER_SIZE = 4096
SOCKET_TIMEOUT_S = 0.25


@dataclass(frozen=True)
class GyroSample:
    seq_global: int
    sensor_ts_phone_ns: int
    pc_receive_monotonic_ns: int
    gx: float
    gy: float
    gz: float


@dataclass(frozen=True)
class GyroSnapshot:
    sample: GyroSample | None
    packet_count: int
    invalid_count: int


def parse_data_packet(
    message: str,
    pc_receive_monotonic_ns: int,
) -> GyroSample | None:
    parts = message.strip().split(",")

    if len(parts) != 14:
        raise ValueError(
            f"expected 14 fields, got {len(parts)}"
        )

    if parts[0] != "DATA":
        raise ValueError(
            f"invalid packet type: {parts[0]}"
        )

    version = int(parts[1])
    if version != EXPECTED_PROTOCOL_VERSION:
        raise ValueError(
            f"unsupported protocol version: {version}"
        )

    sensor_type = parts[6]
    if sensor_type != "GYRO":
        return None

    return GyroSample(
        seq_global=int(parts[4]),
        sensor_ts_phone_ns=int(parts[7]),
        pc_receive_monotonic_ns=pc_receive_monotonic_ns,
        gx=float(parts[10]),
        gy=float(parts[11]),
        gz=float(parts[12]),
    )


def stream_status(age_s: float | None) -> str:
    if age_s is None:
        return "WAITING"
    if age_s < 0.250:
        return "STREAMING"
    if age_s <= 1.000:
        return "STALE"
    return "DISCONNECTED"


class LatestGyroState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sample: GyroSample | None = None
        self._packet_count = 0
        self._invalid_count = 0

    def update(self, sample: GyroSample) -> None:
        with self._lock:
            self._sample = sample
            self._packet_count += 1

    def note_invalid(self) -> None:
        with self._lock:
            self._invalid_count += 1

    def snapshot(self) -> GyroSnapshot:
        with self._lock:
            return GyroSnapshot(
                sample=self._sample,
                packet_count=self._packet_count,
                invalid_count=self._invalid_count,
            )


class UdpGyroReceiver:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5005,
    ) -> None:
        self.host = host
        self.port = port
        self.state = LatestGyroState()

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self.bind_error: OSError | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("receiver already started")

        self._thread = threading.Thread(
            target=self._run,
            name="CursorPreviewUdpReceiver",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        sock = self._socket
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)

    def _run(self) -> None:
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )
        self._socket = sock
        sock.settimeout(SOCKET_TIMEOUT_S)

        try:
            sock.bind((self.host, self.port))
        except OSError as exc:
            self.bind_error = exc
            try:
                sock.close()
            finally:
                return

        try:
            while not self._stop_event.is_set():
                try:
                    payload, _addr = sock.recvfrom(BUFFER_SIZE)
                except socket.timeout:
                    continue
                except OSError:
                    if self._stop_event.is_set():
                        break
                    raise

                receive_ns = time.monotonic_ns()

                try:
                    sample = parse_data_packet(
                        payload.decode("utf-8"),
                        pc_receive_monotonic_ns=receive_ns,
                    )
                except (UnicodeDecodeError, ValueError):
                    self.state.note_invalid()
                    continue

                if sample is not None:
                    self.state.update(sample)
        finally:
            try:
                sock.close()
            except OSError:
                pass
```

- [ ] **Step 4: Run UDP tests and verify GREEN**

```powershell
python -m pytest pc/cursor_preview/tests/test_udp_input.py -v
```

Expected: `6 passed`.

- [ ] **Step 5: Run all cursor-preview tests**

```powershell
python -m pytest pc/cursor_preview/tests -v
```

Expected: `16 passed`.

- [ ] **Step 6: Commit Task 2**

```powershell
git add pc/cursor_preview/udp_input.py `
        pc/cursor_preview/tests/test_udp_input.py

git commit -m "Add UDP input adapter for cursor preview"
```

---

### Task 3: Add Pygame Runtime and Virtual Cursor UI

**Files:**
- Create: `pc/cursor_preview/requirements.txt`
- Create: `pc/cursor_preview/cursor_preview.py`
- Modify: none outside `pc/cursor_preview`.

**Interfaces:**
- Consumes:
  - `UdpGyroReceiver`
  - `stream_status(age_s)`
  - `NeutralBiasEstimator`
  - `gyro_to_velocity(...)`
  - `integrate_cursor(...)`
- Produces: manual engineering preview application invoked with:
  - `python -m pc.cursor_preview.cursor_preview`

- [ ] **Step 1: Add Pygame dependency**

Create `pc/cursor_preview/requirements.txt`:

```text
pygame>=2.5,<3
```

Install into the active Python environment:

```powershell
python -m pip install -r pc/cursor_preview/requirements.txt
```

Verify:

```powershell
python -c "import pygame; print(pygame.version.ver)"
```

Expected: a Pygame `2.x` version is printed.

- [ ] **Step 2: Create the preview application**

Create `pc/cursor_preview/cursor_preview.py`:

```python
from __future__ import annotations

import sys
import time

import pygame

from pc.cursor_preview.imu_mapping import (
    NeutralBiasEstimator,
    gyro_to_velocity,
    integrate_cursor,
)
from pc.cursor_preview.udp_input import (
    UdpGyroReceiver,
    stream_status,
)


WIDTH = 1200
HEIGHT = 700
FPS_TARGET = 60

PORT = 5005

DEAD_ZONE = 0.03
BASE_GAIN = 500.0

SENSITIVITY_LEVELS = (
    0.5,
    1.0,
    1.5,
    2.0,
    3.0,
)
DEFAULT_SENSITIVITY_INDEX = 1

# Engineering-only signs. Change only after manual sanity check.
X_SIGN = 1
Y_SIGN = 1

NEUTRAL_HOLD_S = 2.0


def sample_age_s(
    pc_receive_monotonic_ns: int | None,
) -> float | None:
    if pc_receive_monotonic_ns is None:
        return None

    return max(
        0.0,
        (time.monotonic_ns() - pc_receive_monotonic_ns)
        / 1_000_000_000.0,
    )


def main() -> int:
    pygame.init()

    screen = pygame.display.set_mode(
        (WIDTH, HEIGHT)
    )
    pygame.display.set_caption(
        "IMU Cursor Engineering Preview"
    )

    clock = pygame.time.Clock()
    font = pygame.font.SysFont(
        "consolas",
        20,
    )
    small_font = pygame.font.SysFont(
        "consolas",
        16,
    )

    receiver = UdpGyroReceiver(port=PORT)
    receiver.start()

    estimator = NeutralBiasEstimator(
        duration_s=NEUTRAL_HOLD_S
    )

    sensitivity_index = (
        DEFAULT_SENSITIVITY_INDEX
    )
    dead_zone_enabled = True
    frozen = False

    cursor_x = WIDTH / 2.0
    cursor_y = HEIGHT / 2.0

    bias_x = 0.0
    bias_y = 0.0
    bias_z = 0.0
    calibrated = False

    last_calibration_seq: int | None = None

    try:
        running = True

        while running:
            dt = clock.tick(FPS_TARGET) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False

                    elif event.key == pygame.K_r:
                        cursor_x = WIDTH / 2.0
                        cursor_y = HEIGHT / 2.0

                    elif event.key == pygame.K_n:
                        estimator.reset()
                        calibrated = False
                        last_calibration_seq = None

                    elif event.key == pygame.K_d:
                        dead_zone_enabled = (
                            not dead_zone_enabled
                        )

                    elif event.key == pygame.K_SPACE:
                        frozen = not frozen

                    elif event.key == pygame.K_UP:
                        sensitivity_index = min(
                            sensitivity_index + 1,
                            len(SENSITIVITY_LEVELS) - 1,
                        )

                    elif event.key == pygame.K_DOWN:
                        sensitivity_index = max(
                            sensitivity_index - 1,
                            0,
                        )

            if receiver.bind_error is not None:
                print(
                    "ERROR: could not bind UDP "
                    f"0.0.0.0:{PORT}: "
                    f"{receiver.bind_error}"
                )
                return 2

            snapshot = receiver.state.snapshot()
            sample = snapshot.sample

            age = sample_age_s(
                None
                if sample is None
                else sample.pc_receive_monotonic_ns
            )
            health = stream_status(age)

            if (
                sample is not None
                and not calibrated
                and health == "STREAMING"
                and sample.seq_global != last_calibration_seq
            ):
                estimator.add_sample(
                    time.monotonic(),
                    sample.gx,
                    sample.gy,
                    sample.gz,
                )
                last_calibration_seq = (
                    sample.seq_global
                )

                if estimator.ready(
                    time.monotonic()
                ):
                    bias_x, bias_y, bias_z = (
                        estimator.bias()
                    )
                    calibrated = True

            velocity_x = 0.0
            velocity_y = 0.0

            if (
                sample is not None
                and calibrated
                and health == "STREAMING"
                and not frozen
            ):
                sensitivity = (
                    SENSITIVITY_LEVELS[
                        sensitivity_index
                    ]
                )

                velocity_x, velocity_y = (
                    gyro_to_velocity(
                        sample.gx,
                        sample.gz,
                        bias_x=bias_x,
                        bias_z=bias_z,
                        gain=BASE_GAIN * sensitivity,
                        x_sign=X_SIGN,
                        y_sign=Y_SIGN,
                        dead_zone=DEAD_ZONE,
                        dead_zone_enabled=(
                            dead_zone_enabled
                        ),
                    )
                )

                cursor_x, cursor_y = (
                    integrate_cursor(
                        cursor_x,
                        cursor_y,
                        velocity_x,
                        velocity_y,
                        dt,
                        WIDTH,
                        HEIGHT,
                    )
                )

            if sample is None:
                app_state = "WAITING FOR IMU"
            elif not calibrated:
                app_state = "HOLD STILL"
            elif frozen:
                app_state = "FROZEN"
            else:
                app_state = health

            screen.fill((20, 20, 24))

            pygame.draw.line(
                screen,
                (70, 70, 80),
                (WIDTH // 2 - 15, HEIGHT // 2),
                (WIDTH // 2 + 15, HEIGHT // 2),
                1,
            )
            pygame.draw.line(
                screen,
                (70, 70, 80),
                (WIDTH // 2, HEIGHT // 2 - 15),
                (WIDTH // 2, HEIGHT // 2 + 15),
                1,
            )

            pygame.draw.circle(
                screen,
                (240, 240, 245),
                (
                    int(cursor_x),
                    int(cursor_y),
                ),
                8,
            )

            sensitivity = SENSITIVITY_LEVELS[
                sensitivity_index
            ]

            if sample is None:
                gx = gy = gz = 0.0
                seq_text = "-"
            else:
                gx = sample.gx
                gy = sample.gy
                gz = sample.gz
                seq_text = str(sample.seq_global)

            lines = [
                "IMU CURSOR ENGINEERING PREVIEW",
                f"State       : {app_state}",
                f"Packet seq  : {seq_text}",
                f"Gyro X      : {gx:+.5f}",
                f"Gyro Y      : {gy:+.5f}",
                f"Gyro Z      : {gz:+.5f}",
                f"Bias X/Y/Z  : "
                f"{bias_x:+.5f} "
                f"{bias_y:+.5f} "
                f"{bias_z:+.5f}",
                f"Sensitivity : {sensitivity:.1f}x",
                f"Dead-zone   : "
                f"{'ON' if dead_zone_enabled else 'OFF'}",
                f"UDP GYRO    : {snapshot.packet_count}",
                f"Invalid     : {snapshot.invalid_count}",
                f"FPS         : {clock.get_fps():.1f}",
            ]

            y = 20
            for index, text in enumerate(lines):
                use_font = (
                    font if index == 0 else small_font
                )
                surface = use_font.render(
                    text,
                    True,
                    (230, 230, 235),
                )
                screen.blit(surface, (20, y))
                y += 30 if index == 0 else 22

            help_text = (
                "R=recenter  N=neutral hold  "
                "UP/DOWN=sensitivity  D=dead-zone  "
                "SPACE=freeze  ESC=exit"
            )
            help_surface = small_font.render(
                help_text,
                True,
                (190, 190, 200),
            )
            screen.blit(
                help_surface,
                (
                    20,
                    HEIGHT - 35,
                ),
            )

            pygame.display.flip()

    finally:
        receiver.stop()
        pygame.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run the full automated test suite before manual testing**

From repository root:

```powershell
python -m pytest pc/cursor_preview/tests -v
python -m pytest pc/receiver/test_udp_receiver.py -v
```

Expected:
- cursor preview tests: `16 passed`;
- frozen receiver tests: `6 passed`.

The second command proves this new subsystem did not alter the M2.2 receiver behavior.

- [ ] **Step 4: Verify port 5005 is free**

```powershell
Get-NetUDPEndpoint -LocalPort 5005 -ErrorAction SilentlyContinue
```

Expected: no output.

If an old receiver process still owns the port, identify it before stopping anything:

```powershell
$endpoint = Get-NetUDPEndpoint -LocalPort 5005 -ErrorAction SilentlyContinue
if ($endpoint) {
    Get-CimInstance Win32_Process |
    Where-Object {
        $_.ProcessId -eq $endpoint.OwningProcess
    } |
    Select-Object ProcessId,Name,CommandLine
}
```

- [ ] **Step 5: Run the cursor preview**

```powershell
python -m pc.cursor_preview.cursor_preview
```

Expected:
- a `1200 × 700` Pygame window opens;
- state starts as `WAITING FOR IMU`;
- no exception or port-bind error appears.

- [ ] **Step 6: Start Android IMU streaming to the current PC IPv4**

Check the current Wi‑Fi IPv4:

```powershell
ipconfig
```

In the Samsung application:
- PC IP = current Wi‑Fi IPv4;
- Port = `5005`;
- Record name may be `cursor_preview_smoke_01`;
- start streaming/recording.

Expected:
- preview changes from `WAITING FOR IMU` to `HOLD STILL`;
- after approximately 2 seconds of stillness it changes to `STREAMING`;
- GYRO packet count and values update.

- [ ] **Step 7: Perform the direction sanity check**

Use remote-like posture: screen generally upward, top edge pointed toward the monitor.

Check in this order:

```text
top edge right → cursor right
top edge left  → cursor left
top edge up    → cursor up
top edge down  → cursor down
```

If only horizontal direction is inverted, change `X_SIGN` from `1` to `-1`.
If only vertical direction is inverted, change `Y_SIGN` from `1` to `-1`.
Do not change sensor-axis selection in the same step.

After any sign change:

```powershell
python -m pytest pc/cursor_preview/tests -v
```

Expected: `16 passed`.

- [ ] **Step 8: Perform manual control acceptance**

Verify each behavior explicitly:

```text
[ ] R recenters the virtual cursor.
[ ] N returns to HOLD STILL and recalibrates neutral bias.
[ ] UP increases sensitivity through 0.5,1.0,1.5,2.0,3.0.
[ ] DOWN decreases sensitivity.
[ ] D toggles dead-zone without crashing.
[ ] SPACE freezes and resumes cursor motion.
[ ] Stationary phone gives approximately stationary cursor behavior.
[ ] Cursor remains inside the 1200×700 window.
```

- [ ] **Step 9: Perform stale/disconnect fail-safe check**

While the cursor is moving:
1. stop Samsung streaming;
2. do not touch the PC preview.

Expected:
- within 250–1000 ms the state becomes `STALE`;
- after >1000 ms it becomes `DISCONNECTED`;
- cursor stops rather than continuing with an old velocity.

Restart Samsung streaming.

Expected:
- state returns to `STREAMING`;
- cursor control resumes without restarting Pygame.

- [ ] **Step 10: Verify clean shutdown**

Press `ESC`.

Expected:
- Pygame window closes;
- PowerShell prompt returns;
- port 5005 is free:

```powershell
Get-NetUDPEndpoint -LocalPort 5005 -ErrorAction SilentlyContinue
```

Expected: no output.

- [ ] **Step 11: Commit Task 3**

```powershell
git add pc/cursor_preview/requirements.txt `
        pc/cursor_preview/cursor_preview.py

git commit -m "Add Pygame virtual cursor engineering preview"
```

---

### Task 4: Final Verification, Documentation Record, and PR Preparation

**Files:**
- Modify only if needed after manual sign sanity check:
  - `pc/cursor_preview/cursor_preview.py`
- No research data files are committed.

**Interfaces:**
- Consumes: all Task 1–3 deliverables.
- Produces: verified branch ready for review/PR.

- [ ] **Step 1: Run fresh automated verification**

From repository root:

```powershell
python -m pytest pc/cursor_preview/tests -v
python -m pytest pc/receiver/test_udp_receiver.py -v
```

Expected:
- cursor preview: `16 passed`;
- receiver: `6 passed`;
- zero failures.

- [ ] **Step 2: Verify branch contains only intended source/spec changes**

```powershell
git status
git diff main...HEAD --stat
git log --oneline --decorate -8
```

Expected source changes are limited to:
- approved design spec;
- implementation plan;
- `pc/cursor_preview/**`.

There must be no `bench_data`, runtime CSV, receiver logs, Android session data, `.venv`, or generated cache files in the commit set.

- [ ] **Step 3: Record the manual acceptance result in the commit message, not research data**

If all manual checks passed and axis signs were finalized, create a final small commit only if code changed during acceptance:

```powershell
git add pc/cursor_preview/cursor_preview.py
git commit -m "Finalize cursor preview axis signs after bench sanity check"
```

If no code changed, do not create an empty commit.

- [ ] **Step 4: Save and commit this implementation plan**

Ensure this file exists at:

```text
docs/superpowers/plans/2026-09-05-cursor-engineering-preview.md
```

Then:

```powershell
git add docs/superpowers/plans/2026-09-05-cursor-engineering-preview.md
git commit -m "Add cursor engineering preview implementation plan"
```

If the implementation plan was committed before execution, skip this step.

- [ ] **Step 5: Push the feature branch**

```powershell
git push -u origin feature/cursor-engineering-preview
```

- [ ] **Step 6: Create a Pull Request against `main`**

Recommended title:

```text
Add cursor engineering preview
```

Recommended PR summary:

```text
- add isolated Pygame virtual cursor preview
- reuse frozen Wi-Fi UDP protocol v1 without modifying M2.2 receiver
- add tested gyro-to-velocity mapping and neutral-bias estimator
- add non-blocking latest-sample UDP adapter and stream fail-safe states
- keep preview explicitly separate from P0/P2C and participant data collection
- verify cursor-preview tests and frozen receiver regression tests
```

Do not merge until fresh tests and manual acceptance have been reviewed.

---

## Self-Review Against the Approved Spec

**Spec coverage**
- Purpose and engineering-only boundary: Tasks 3–4.
- Wi‑Fi UDP only; Bluetooth excluded: Global Constraints and Task 2.
- Frozen receiver untouched: Global Constraints and Task 3 regression command.
- Remote-like posture: Task 3 manual sanity check.
- Gyro Z → horizontal / Gyro X → vertical: Task 1 and Task 3.
- Explicit axis signs: Task 1 interface and Task 3 constants.
- Velocity mapping with actual `dt`: Task 1.
- Neutral hold ~2 s: Task 1 estimator and Task 3 state flow.
- Dead-zone 0.03 and five sensitivity levels: Task 3 constants/UI.
- Stale/disconnected fail-safe: Task 2 + Task 3 manual check.
- 1200×700 at 60 Hz: Task 3.
- Controls R/N/UP/DOWN/D/SPACE/ESC: Task 3.
- No click/Fitts/P0/P2C/smoothing/system cursor: Global Constraints.
- Non-blocking UDP vs render loop: Task 2 receiver thread + Task 3 main loop.
- Malformed/version handling and bind failure: Task 2 + Task 3.
- Automated mapping/UDP tests: Tasks 1–2.
- Manual acceptance: Task 3.
- Git workflow: Task 4.

**Placeholder scan**
- No `TBD`, `TODO`, “implement later”, or unspecified code steps remain.

**Type/signature consistency**
- Task 3 imports and calls the exact functions/classes produced by Tasks 1–2.
- `GyroSample` field names match parser construction and UI consumption.
- `NeutralBiasEstimator.bias()` returns X/Y/Z; Task 3 uses X and Z for mapping while retaining Y for diagnostics.
