from __future__ import annotations

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

# Engineering-only.
# Kita verifikasi arahnya nanti dari gerakan HP nyata.
X_SIGN = -1
Y_SIGN = -1

NEUTRAL_HOLD_S = 2.0


def sample_age_s(
    pc_receive_monotonic_ns: int | None,
) -> float | None:

    if pc_receive_monotonic_ns is None:
        return None

    return max(
        0.0,
        (
            time.monotonic_ns()
            - pc_receive_monotonic_ns
        )
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

    receiver = UdpGyroReceiver(
        port=PORT
    )

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

            dt = (
                clock.tick(FPS_TARGET)
                / 1000.0
            )

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
                            len(
                                SENSITIVITY_LEVELS
                            ) - 1,
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

            snapshot = (
                receiver.state.snapshot()
            )

            sample = snapshot.sample

            age = sample_age_s(
                None
                if sample is None
                else sample.pc_receive_monotonic_ns
            )

            health = stream_status(age)

            # ==============================================
            # NEUTRAL HOLD
            # ==============================================

            if (
                sample is not None
                and not calibrated
                and health == "STREAMING"
                and (
                    sample.seq_global
                    != last_calibration_seq
                )
            ):

                now_s = time.monotonic()

                estimator.add_sample(
                    now_s,
                    sample.gx,
                    sample.gy,
                    sample.gz,
                )

                last_calibration_seq = (
                    sample.seq_global
                )

                if estimator.ready(now_s):

                    (
                        bias_x,
                        bias_y,
                        bias_z,
                    ) = estimator.bias()

                    calibrated = True

            # ==============================================
            # CURSOR VELOCITY
            # ==============================================

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

                (
                    velocity_x,
                    velocity_y,
                ) = gyro_to_velocity(
                    sample.gx,
                    sample.gz,
                    bias_x=bias_x,
                    bias_z=bias_z,
                    gain=(
                        BASE_GAIN
                        * sensitivity
                    ),
                    x_sign=X_SIGN,
                    y_sign=Y_SIGN,
                    dead_zone=DEAD_ZONE,
                    dead_zone_enabled=(
                        dead_zone_enabled
                    ),
                )

                (
                    cursor_x,
                    cursor_y,
                ) = integrate_cursor(
                    cursor_x,
                    cursor_y,
                    velocity_x,
                    velocity_y,
                    dt,
                    WIDTH,
                    HEIGHT,
                )

            # ==============================================
            # APPLICATION STATE
            # ==============================================

            if sample is None:

                app_state = (
                    "WAITING FOR IMU"
                )

            elif not calibrated:

                app_state = "HOLD STILL"

            elif frozen:

                app_state = "FROZEN"

            else:

                app_state = health

            # ==============================================
            # DRAW
            # ==============================================

            screen.fill(
                (20, 20, 24)
            )

            # Central reference crosshair
            pygame.draw.line(
                screen,
                (70, 70, 80),
                (
                    WIDTH // 2 - 15,
                    HEIGHT // 2,
                ),
                (
                    WIDTH // 2 + 15,
                    HEIGHT // 2,
                ),
                1,
            )

            pygame.draw.line(
                screen,
                (70, 70, 80),
                (
                    WIDTH // 2,
                    HEIGHT // 2 - 15,
                ),
                (
                    WIDTH // 2,
                    HEIGHT // 2 + 15,
                ),
                1,
            )

            # Virtual cursor
            pygame.draw.circle(
                screen,
                (240, 240, 245),
                (
                    int(cursor_x),
                    int(cursor_y),
                ),
                8,
            )

            sensitivity = (
                SENSITIVITY_LEVELS[
                    sensitivity_index
                ]
            )

            if sample is None:

                gx = 0.0
                gy = 0.0
                gz = 0.0

                seq_text = "-"

            else:

                gx = sample.gx
                gy = sample.gy
                gz = sample.gz

                seq_text = str(
                    sample.seq_global
                )

            lines = [
                "IMU CURSOR ENGINEERING PREVIEW",

                f"State       : {app_state}",

                f"Packet seq  : {seq_text}",

                f"Gyro X      : {gx:+.5f}",

                f"Gyro Y      : {gy:+.5f}",

                f"Gyro Z      : {gz:+.5f}",

                (
                    "Bias X/Y/Z  : "
                    f"{bias_x:+.5f} "
                    f"{bias_y:+.5f} "
                    f"{bias_z:+.5f}"
                ),

                (
                    "Sensitivity : "
                    f"{sensitivity:.1f}x"
                ),

                (
                    "Dead-zone   : "
                    f"{'ON' if dead_zone_enabled else 'OFF'}"
                ),

                (
                    "UDP GYRO    : "
                    f"{snapshot.packet_count}"
                ),

                (
                    "Invalid     : "
                    f"{snapshot.invalid_count}"
                ),

                (
                    "FPS         : "
                    f"{clock.get_fps():.1f}"
                ),
            ]

            y = 20

            for index, text in enumerate(
                lines
            ):

                use_font = (
                    font
                    if index == 0
                    else small_font
                )

                surface = use_font.render(
                    text,
                    True,
                    (230, 230, 235),
                )

                screen.blit(
                    surface,
                    (20, y),
                )

                y += (
                    30
                    if index == 0
                    else 22
                )

            help_text = (
                "R=recenter  "
                "N=neutral hold  "
                "UP/DOWN=sensitivity  "
                "D=dead-zone  "
                "SPACE=freeze  "
                "ESC=exit"
            )

            help_surface = (
                small_font.render(
                    help_text,
                    True,
                    (190, 190, 200),
                )
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
    raise SystemExit(
        main()
    )