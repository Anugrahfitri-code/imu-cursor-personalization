# Stage 2.3-2.4 Guided 2C and Clock-to-Label Freeze v1.0

Status: FROZEN  
Freeze date: 2026-09-19  
Branch: `research/stage2.3-2.4-guided-2c-clock-label-v1.0`  
Freeze tag: `stage2.3-2.4-guided-2c-clock-label-v1.0`  
Functional implementation commit: `d4b388ac3e33ab3d8a5fd0ec8eb54005f48f1623`

## 1. Scope

This decision freezes the Stage 2.3 Guided 2C calibration and Stage 2.4 native clock-to-reference-label construction contract.

The freeze covers:

1. Guided 2C reference trajectory generation.
2. Reference trajectory validation.
3. Calibration source provenance and exact source-slice identity.
4. Native phone sensor timestamp mapping into PC monotonic time.
5. Boundary-safe reference trajectory lookup.
6. Lag-aware native label construction.
7. Label-build validation and label manifest generation.
8. Synthetic end-to-end qualification.

This freeze does not freeze downstream preprocessing, model training, participant-study parameters, or final experimental task design.

## 2. Guided 2C Contract

Guided calibration consists of exactly two cycles.

Each cycle contains exactly eight center-out directions in this order:

1. RIGHT
2. UP_RIGHT
3. UP
4. UP_LEFT
5. LEFT
6. DOWN_LEFT
7. DOWN
8. DOWN_RIGHT

Each direction follows:

`CENTER_HOLD -> OUTBOUND -> TARGET_HOLD -> RETURN`

Each sequence returns to center.

Coordinate convention:

- positive x points right;
- positive y points down.

PC monotonic time is the reference timebase and must be non-decreasing.

Reference trajectory rows contain reference position and velocity.

The calibration remains condition-neutral. No artificial `SHARED_2C` experimental condition is introduced. The shared calibration is identified through `calibration_id`.

## 3. Frozen Artifact Namespace

Calibration raw artifacts:

- `raw/calibration/reference_trajectory.csv`
- `raw/calibration/calibration_manifest.json`

Calibration-derived artifacts:

- `derived/calibration/mapped_sensor_times.csv`
- `derived/calibration/native_reference_labels.csv`
- `derived/calibration/label_manifest.json`

Calibration configuration artifacts:

- `artifacts/calibration/label_config.json`

The Stage 2.1 experimental schemas remain unchanged.

## 4. Calibration Provenance Contract

Calibration provenance records the exact raw IMU source and exact selected slice.

The provenance includes:

- source file identity;
- source file SHA-256;
- first and last selected source row;
- first and last selected sequence;
- calibration PC-time window;
- calibration identity;
- trajectory configuration SHA-256;
- clock-model SHA-256.

The source-selection calibration identity and PC-time window must match the top-level calibration manifest.

Future personalized branches that consume the same Guided 2C calibration must use the same calibration source bundle and exact source slice, not merely files with superficially similar contents.

## 5. Clock Mapping Contract

Native sensor timestamps are mapped using the qualified public clock-model mapping interface:

`ClockModel.map_phone_to_pc_ns(phone_sensor_ts_ns)`

`pc_receive_ts_ns` is not used as the supervision timestamp.

Rows with invalid native source timestamps are marked:

`INVALID_SOURCE_TIMESTAMP`

Successfully mapped rows are marked:

`MAPPED`

A failed clock-quality gate fails closed and does not permit construction of supervision labels.

The synthetic qualification uses a deterministic method-compatible synthetic clock model only for qualification. It does not replace the qualified production clock-model contract.

## 6. Reference Lookup Contract

Exact PC-time matches are preferred.

Interpolation is permitted only when both neighboring reference rows belong to the same:

- `calibration_id`;
- `sequence_id`;
- `segment_index`;
- `direction_code`;
- `phase`.

Interpolation across phase, direction, segment, sequence, or calibration boundaries is forbidden.

Extrapolation outside the reference trajectory is forbidden.

Row-level lookup statuses are:

- `VALID`
- `OUTSIDE_REFERENCE`
- `UNRESOLVED_BOUNDARY`

## 7. Native Label Contract

The supervised target is reference cursor velocity:

`[ref_vx_px_s, ref_vy_px_s]`

The frozen lag-sign convention is:

`label_pc_time_ns = pc_mapped_ts_ns - alignment_lag_ns`

Therefore, a positive alignment lag pairs a sensor observation at mapped time `t` with an earlier reference state at `t - tau`.

The numeric value of `alignment_lag_ns` for the participant study is not frozen by this decision.

The 5 ms lag used by synthetic qualification is a deterministic qualification fixture only.

## 8. Build-Level Validity

Row-level invalidity and build-level technical invalidity are distinct.

Row-level invalid labels may be excluded from valid supervision without invalidating the whole build, provided valid labels remain and all technical gates pass.

Frozen build statuses:

- `VALID`
- `TECHNICAL_INVALID`

Examples of technical-invalid conditions include:

- missing clock model;
- failed clock-quality gate;
- missing source evidence;
- missing provenance;
- invalid label schema/status;
- mixed label identity;
- zero valid labels.

## 9. Synthetic Qualification

Qualification dataset role:

`synthetic`

Real participant data used:

`false`

Qualification result:

`VALID`

Cycle count:

`2`

Mapped record count:

`192`

Valid label count:

`192`

Invalid label count:

`0`

Functional implementation commit embedded in final evidence:

`d4b388ac3e33ab3d8a5fd0ec8eb54005f48f1623`

Synthetic qualification evidence location:

`bench_data/stage2_3_2_4_synthetic_qualification/qualification_v1/`

The evidence directory is intentionally excluded from Git by the existing `bench_data/` ignore rule.

## 10. Final Synthetic Artifact SHA-256

`calibration_manifest`

`0024D9B92AD63F8C915F1CC9933720C171540464C8700C44E872BEEF937C9A84`

`clock_model`

`183485DB6E668E3428E16F8B27FED56592075CBAE083B34F8B03B0E000749FBA`

`label_config`

`8EB1C25A29869C1412F5CE2F344841E7BE5F3601B6D8C2913F081D7A4E2850FF`

`label_manifest`

`36F30BAFEB9D2442BB99D1068CB18F8495F25F14081735734AA168EE1B6C2A7A`

`mapped_sensor_times`

`2492E1D40AA0D4350C3031551BA49AE40833BB4330DC0A4B6BC5E34E976E3CD4`

`native_reference_labels`

`E764C174032EC80C6756708DC73DC14ACE0AA3B045DB884E0E11B754FC4E34CC`

`raw_imu`

`DD8B3099F9FAFB478A1575DD896ED60F0A65ED279D2659F93822A7D1F070F168`

`reference_trajectory`

`0FC6D7CDCB3D4E4673D3B2DA51D3F352B56CBE4A9A7ED4372D2FFC9BE4215ADA`

Calibration provenance SHA-256:

`49FE2CD28C035F72D589DFC12014E9470519BE9A961B1B4E458973F3F353E006`

Synthetic reproducibility digest:

`6296B6E6BBBA967C5A6F3BBD694BE670C054914164A12DE45CA6F80284FC0F05`

## 11. Qualification Test Evidence

Pre-freeze regression:

`223 passed`

UDP receiver regression:

`6 passed`

Task-specific qualification additionally demonstrated:

- deterministic Guided 2C generation;
- exact direction order for both cycles;
- clock mapping based on `phone_sensor_ts_ns`;
- explicit rejection of receive-time supervision;
- frozen lag-sign convention;
- reference velocity target construction;
- exact calibration source-slice provenance;
- reproducible artifact hashes;
- fail-closed behavior under invalid clock quality;
- no use of real participant data.

## 12. Explicitly Not Frozen

This decision does not freeze:

- participant-study phase durations;
- participant-study trajectory speed profile;
- final numerical alignment lag;
- final IMU resampling rate;
- final common time grid;
- preprocessing or filtering configuration;
- model input window construction;
- P0 algorithm implementation;
- P2C algorithm implementation;
- L0 algorithm implementation;
- L2C algorithm implementation;
- final Fitts-law task configuration;
- participant recruitment or data-collection protocol.

Synthetic constants used during software qualification must not be silently promoted to participant-study parameters.

## 13. Freeze Decision

Stage 2.3 Guided 2C and Stage 2.4 native clock-to-label construction are accepted as functionally qualified and frozen at version 1.0.

Changes to any frozen contract in this document require an explicit versioned decision and a new qualification cycle.