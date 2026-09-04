# Smartphone IMU Cursor Personalization

Research prototype for investigating personalized free-space
cursor control using smartphone inertial sensors.

## Research Scope

This project compares four cursor-control conditions:

- P0: Global parametric controller
- P2C: Parametric controller personalized using 2C calibration
- L0: Global temporal learned controller
- L2C: Temporal learned controller with user-specific latent adaptation

The primary HCI evaluation will use a controlled pointing task
with Fitts-law throughput as the primary outcome.

## Current Status

### M0 — Device and Sensor Validation
PASS

### M1 — Sensor Acquisition
PASS / FROZEN

Current validated device:

- Device: Samsung SM-A066B
- Android: 16
- Accelerometer: Bosch bmi3xy acc
- Gyroscope: Bosch bmi3xy gyro
- Requested sampling rate: 100 Hz

Validated acquisition characteristics:

- SensorEvent.timestamp used as primary sensor timestamp
- raw ACC and GYRO logging
- per-sensor and global sequence numbers
- asynchronous disk writer
- metadata logging
- recording naming
- bench-validation archive

## Repository Structure

```text
android/
    IMUResearchClient/

validation_archive/
    M1_SENSOR_FREEZE/

Additional PC, analysis, experiment, and modeling components
will be added in subsequent development stages.

Research Status

This repository is under active development.

Human-participant evaluation data are not included in this
repository.

Publication

Manuscript preparation is in progress.