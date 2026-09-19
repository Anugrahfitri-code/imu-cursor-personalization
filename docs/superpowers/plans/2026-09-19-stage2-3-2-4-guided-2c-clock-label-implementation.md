# Stage 2.3–2.4 Guided 2C Calibration and Clock-to-Label Implementation Plan

Version: 1.0

Date: 2026-09-19

Status: IMPLEMENTATION PLAN

Project: IMU Cursor Personalization

Branch:

`research/stage2.3-2.4-guided-2c-clock-label-v1.0`

Design specification:

`docs/superpowers/specs/2026-09-18-stage2-3-2-4-guided-2c-clock-label-design.md`

Design commit:

`b1fe987`

Upstream freeze:

`stage2.1-experimental-data-contract-v1.0`

Upstream freeze commit:

`3831687b1e213e6116c2b0c7c4e7a9a177f09f2d`

Current inherited test baseline:

```text
pc/clock_sync/tests
+
pc/experiment/tests
=
101 passed
```

---

# 1. Purpose

This implementation plan defines the execution sequence for:

- Stage 2.3 Guided Calibration 2C;
- Stage 2.4 Clock Mapping and Label Construction.

The work package establishes an auditable path from:

```text
deterministic PC reference trajectory
        +
raw smartphone IMU timestamps
        +
qualified phone-to-PC clock mapping
        ↓
PC-mapped native sensor timestamps
        ↓
explicit alignment-lag convention
        ↓
reference trajectory lookup
        ↓
reference velocity supervision
```

The output of this work package is a trustworthy native-event supervision layer.

It is not yet the final model-training matrix.

Stage 2.5 will later decide how asynchronous accelerometer and gyroscope data are transformed into a common model input grid.

---

# 2. Scope

Stage 2.3–2.4 implements:

```text
guided 2C trajectory contract

deterministic PC reference trajectory generation

reference trajectory validation

shared calibration manifest

calibration source provenance

phone sensor timestamp → PC timestamp mapping

reference-state lookup

alignment-lag application

native reference-velocity labels

label provenance

label validation

synthetic end-to-end qualification
```

Stage 2.3–2.4 does not implement:

```text
P0 controller

P2C parameter fitting

L0 learned controller

L2C learned personalization

Fitts pointing task

Fitts throughput

final IMU common time grid

final IMU resampling frequency

final accelerometer/gyroscope interpolation

final low-pass filter

final bias-correction method

final smartphone-axis transform

final model temporal window

participant evaluation
```

---

# 3. Frozen Upstream Boundary

Stage 2.3–2.4 inherits Stage 2.1 Experimental Data Contract v1.0.

The following Stage 2.1 schemas must remain unchanged:

```text
raw/trial_events.csv

raw/cursor_samples.csv

raw/calibration_events.csv

derived/quality_flags.csv
```

Stage 2.3–2.4 must not silently modify:

```text
Stage 2.1 CSV column order

Stage 2.1 manifest required fields

dataset role vocabulary

condition code vocabulary

session status vocabulary

Stage 2.1 validator behavior

Stage 2.1 hash-manifest semantics

Stage 2.1 CLI semantics
```

Any additional information required by Stage 2.3–2.4 must be represented through new versioned artifacts.

---

# 4. Qualified Clock-Synchronization Dependency

Stage 2.3–2.4 must reuse the existing qualified clock-sync implementation.

Authoritative mapping implementation:

```python
ClockModel.map_phone_to_pc_ns(...)
```

Conceptual model:

```text
t_pc = alpha * t_phone + beta
```

where the existing implementation represents:

```text
alpha
beta_ns
```

Stage 2.3–2.4 must not:

```text
fit a second affine clock model

estimate a second alpha/beta pair

replace phone sensor timestamps with PC receive timestamps

weaken existing clock-quality gates

change qualified pc/clock_sync mathematics for convenience
```

The supervision timeline is:

```text
phone_sensor_ts_ns
        ↓
ClockModel.map_phone_to_pc_ns(...)
        ↓
pc_mapped_ts_ns
```

`pc_receive_ts_ns` remains transport evidence only.

It may be used for:

```text
latency diagnostics

packet diagnostics

transport debugging

packet ordering investigation
```

It must not be used as the primary label-alignment clock.

---

# 5. Artifact Namespace

Stage 2.3–2.4 uses the following namespace:

```text
raw/calibration/

derived/calibration/

artifacts/calibration/
```

## 5.1 `raw/calibration/`

Source experiment-control evidence.

Examples:

```text
raw/calibration/reference_trajectory.csv

raw/calibration/calibration_manifest.json
```

## 5.2 `derived/calibration/`

Derived scientific evidence.

Examples:

```text
derived/calibration/mapped_sensor_times.csv

derived/calibration/native_reference_labels.csv

derived/calibration/label_manifest.json
```

## 5.3 `artifacts/calibration/`

Configuration and provenance artifacts.

Examples:

```text
artifacts/calibration/label_config.json
```

---

# 6. Repository Hygiene

Never use:

```powershell
git add .
```

Only stage explicit intended files.

Known existing untracked engineering evidence must remain untracked unless a separate documented decision says otherwise:

```text
PktMon.etl

audit_b_extended_20260913_153121_985/

audit_b_receiver_diag_20260913_160603_016/

audit_m2_3_422f20d/

diagnostic_package_20260913_154940_181/

pc/receiver/logs_diagnostic/
```

Participant data remain excluded from Git.

Synthetic qualification evidence under `bench_data/` remains excluded from Git.

---

# 7. TDD Execution Rule

Every implementation task follows:

```text
RED
 ↓
write failing tests
 ↓
confirm expected failure
 ↓
GREEN
 ↓
implement minimum required production code
 ↓
targeted test pass
 ↓
full relevant regression
 ↓
Git boundary audit
 ↓
explicit-file commit
```

No implementation task is complete until:

```text
targeted tests pass

inherited regression passes

tracked diff is understood

staged diff contains only intended files

commit checkpoint is created
```

---

# Task 1 — Freeze New Artifact Schemas

## 8. Objective

Define every Stage 2.3–2.4 artifact schema before implementing trajectory generation, clock mapping, or labels.

---

## 8.1 Files

Create:

```text
pc/experiment/calibration/__init__.py

pc/experiment/calibration/schema.py

pc/experiment/labels/__init__.py

pc/experiment/labels/schema.py

pc/experiment/tests/test_stage23_schemas.py
```

---

## 8.2 Required Calibration Schema Symbols

`pc/experiment/calibration/schema.py` must expose symbols equivalent to:

```python
REFERENCE_TRAJECTORY_COLUMNS

CALIBRATION_MANIFEST_REQUIRED_FIELDS

DIRECTION_CODES

PHASE_CODES

PAUSE_FLAG_BY_PHASE
```

---

## 8.3 Required Label Schema Symbols

`pc/experiment/labels/schema.py` must expose symbols equivalent to:

```python
MAPPED_SENSOR_TIME_COLUMNS

MAPPING_STATUSES

NATIVE_LABEL_COLUMNS

LABEL_STATUSES

LABEL_CONFIG_REQUIRED_FIELDS

LABEL_MANIFEST_REQUIRED_FIELDS

LABEL_BUILD_STATUSES
```

Exact Python container type may be tuple, frozenset, or equivalent appropriate immutable structure.

---

## 8.4 Reference Trajectory Schema

Artifact:

```text
raw/calibration/reference_trajectory.csv
```

Required ordered columns:

```text
reference_sample_id
participant_id
session_id
calibration_id
cycle_index
sequence_id
segment_index
direction_code
phase
pc_time_ns
relative_time_ns
ref_x_px
ref_y_px
ref_vx_px_s
ref_vy_px_s
speed_profile_code
pause_flag
trajectory_version
```

---

## 8.5 Direction Vocabulary

Frozen:

```text
RIGHT

UP_RIGHT

UP

UP_LEFT

LEFT

DOWN_LEFT

DOWN

DOWN_RIGHT
```

Frozen direction order:

```text
1 RIGHT

2 UP_RIGHT

3 UP

4 UP_LEFT

5 LEFT

6 DOWN_LEFT

7 DOWN

8 DOWN_RIGHT
```

---

## 8.6 Phase Vocabulary

Frozen:

```text
CENTER_HOLD

OUTBOUND

TARGET_HOLD

RETURN
```

---

## 8.7 Pause Semantics

Frozen:

```text
CENTER_HOLD = 1

TARGET_HOLD = 1

OUTBOUND = 0

RETURN = 0
```

---

## 8.8 Calibration Manifest Contract

Artifact:

```text
raw/calibration/calibration_manifest.json
```

Required fields:

```text
participant_id

session_id

calibration_id

calibration_start_pc_ns

calibration_end_pc_ns

cycle_count

reference_trajectory_file

trajectory_version

trajectory_config_sha256

raw_imu_sha256

clock_model_sha256
```

If more than one raw IMU source file is required, implementation may represent hashes as a structured collection, provided the same provenance meaning is preserved.

---

## 8.9 Mapped Sensor Time Schema

Artifact:

```text
derived/calibration/mapped_sensor_times.csv
```

Required ordered columns:

```text
mapped_record_id
participant_id
session_id
calibration_id
source_file
source_row_index
phone_sensor_ts_ns
pc_mapped_ts_ns
clock_model_sha256
mapping_status
derivation_version
```

Frozen mapping status vocabulary:

```text
MAPPED

INVALID_SOURCE_TIMESTAMP
```

---

## 8.10 Native Reference Label Schema

Artifact:

```text
derived/calibration/native_reference_labels.csv
```

Required ordered columns:

```text
label_record_id
participant_id
session_id
calibration_id
source_file
source_row_index
phone_sensor_ts_ns
pc_mapped_ts_ns
alignment_lag_ns
label_pc_time_ns
sequence_id
direction_code
phase
ref_x_px
ref_y_px
ref_vx_px_s
ref_vy_px_s
label_status
derivation_version
```

Frozen row-level label status vocabulary:

```text
VALID

OUTSIDE_REFERENCE

UNRESOLVED_BOUNDARY
```

---

## 8.11 Label Configuration Contract

Artifact:

```text
artifacts/calibration/label_config.json
```

Required semantic content:

```text
schema/version identifier

trajectory version

lag sign convention

alignment_lag_ns

clock mapping method

reference lookup method

reference interpolation rule

out-of-range policy

source artifact paths

source artifact hashes

derivation version

functional commit

configuration role
```

Configuration role must distinguish at least:

```text
synthetic

candidate

pilot

frozen
```

Presence of a configuration file does not automatically mean its numerical values are scientifically frozen.

---

## 8.12 Label Manifest Contract

Artifact:

```text
derived/calibration/label_manifest.json
```

Required fields:

```text
participant_id

session_id

calibration_id

status

raw_imu_sha256

reference_trajectory_sha256

clock_model_sha256

label_config_sha256

mapped_record_count

valid_label_count

invalid_label_count

first_mapped_pc_time_ns

last_mapped_pc_time_ns

derivation_version

functional_commit
```

Frozen build-level status vocabulary:

```text
VALID

TECHNICAL_INVALID
```

---

## 8.13 RED Phase

Create tests first.

Minimum tests:

```text
test_reference_trajectory_columns_are_exact

test_direction_codes_are_exact

test_phase_codes_are_exact

test_pause_flag_semantics_are_exact

test_calibration_manifest_fields_are_exact

test_mapped_sensor_time_columns_are_exact

test_mapping_status_vocabulary_is_exact

test_native_label_columns_are_exact

test_label_status_vocabulary_is_exact

test_label_config_required_fields_are_exact

test_label_manifest_required_fields_are_exact

test_label_build_status_vocabulary_is_exact
```

Expected initial state:

```text
FAIL
```

due to missing modules or symbols.

---

## 8.14 GREEN Phase

Implement schema constants and only minimal schema validation helpers.

Do not implement:

```text
trajectory generation

clock mapping

reference lookup

label construction
```

---

## 8.15 Verification

Targeted:

```powershell
python -m pytest `
  ".\pc\experiment\tests\test_stage23_schemas.py" `
  -v
```

Then regression:

```powershell
python -m pytest `
  ".\pc\clock_sync\tests" `
  ".\pc\experiment\tests" `
  -q
```

Expected:

```text
Task 1 tests PASS

inherited tests PASS
```

---

## 8.16 Commit Checkpoint

Stage only Task 1 files.

Commit:

```text
feat(stage2.3-2.4): add calibration artifact schemas
```

---

# Task 2 — Deterministic Guided 2C Trajectory Generator

## 9. Objective

Implement the deterministic PC reference trajectory used by the shared 2C calibration episode.

---

## 9.1 Files

Create:

```text
pc/experiment/calibration/trajectory.py

pc/experiment/tests/test_guided_trajectory.py
```

---

## 9.2 Frozen 2C Structure

2C means exactly:

```text
2 complete calibration cycles
```

Each cycle contains exactly:

```text
8 directions
```

Total:

```text
16 directional center-out-return units
```

Direction order is the frozen order from Task 1.

---

## 9.3 Reference Coordinate Convention

PC experiment-window coordinates:

```text
+x = right

+y = down
```

Conceptual direction vectors:

```text
RIGHT       = (+1,  0)

UP_RIGHT    = (+1, -1), normalized

UP          = ( 0, -1)

UP_LEFT     = (-1, -1), normalized

LEFT        = (-1,  0)

DOWN_LEFT   = (-1, +1), normalized

DOWN        = ( 0, +1)

DOWN_RIGHT  = (+1, +1), normalized
```

This does not define smartphone sensor-axis mapping.

---

## 9.4 Phase Structure

Each direction follows:

```text
CENTER_HOLD
    ↓
OUTBOUND
    ↓
TARGET_HOLD
    ↓
RETURN
```

After `RETURN`, reference position must be at the calibration center before the next directional unit starts.

---

## 9.5 Interface

Implement an interface equivalent to:

```python
generate_guided_2c(
    participant_id,
    session_id,
    calibration_id,
    start_pc_time_ns,
    config,
)
```

Return representation may be selected during implementation, but emitted rows must conform exactly to `REFERENCE_TRAJECTORY_COLUMNS`.

---

## 9.6 Determinism

For identical:

```text
trajectory configuration

calibration identifier

cycle index

direction index

relative calibration time

trajectory implementation version
```

the same relative reference state must be produced.

Determinism is defined relative to:

```text
calibration_start_pc_ns
```

Absolute PC timestamps across separate runs do not need to match.

---

## 9.7 Reference Timing

Trajectory progression uses a monotonic PC clock or injectable monotonic test clock.

`pc_time_ns` must be:

```text
monotonically non-decreasing
```

Equal adjacent timestamps are permitted.

Timestamp decrease is invalid.

---

## 9.8 Velocity Semantics

Reference velocity must come directly from the deterministic trajectory definition.

Do not derive reference velocity through noisy finite differences when the trajectory generator already knows its analytic/deterministic velocity.

During true holds:

```text
ref_vx_px_s = 0

ref_vy_px_s = 0
```

---

## 9.9 Unfrozen Numerical Parameters

Task 2 must not scientifically freeze:

```text
final movement radius

final outbound duration

final return duration

final center-hold duration

final target-hold duration

final speed-profile choice

final speed-profile numeric parameters

final reference emission cadence
```

Synthetic engineering values are allowed if explicitly identified as test-only or candidate.

---

## 9.10 RED Phase

Minimum tests:

```text
test_two_cycles_are_generated_exactly

test_each_cycle_contains_eight_directions

test_direction_order_is_exact

test_each_direction_starts_at_center

test_each_direction_returns_to_center

test_cycle_two_repeats_direction_order

test_relative_trajectory_is_deterministic

test_reference_timestamps_do_not_decrease

test_reference_sample_ids_are_unique

test_sequence_ids_are_unique

test_sequence_ids_are_deterministic

test_hold_velocity_is_zero

test_pause_flag_matches_phase

test_direction_codes_are_valid

test_phase_codes_are_valid
```

---

## 9.11 GREEN Phase

Implement the minimum deterministic generator needed to satisfy the tests.

Do not introduce:

```text
P2C fitting

model features

Fitts logic
```

---

## 9.12 Verification

Targeted:

```powershell
python -m pytest `
  ".\pc\experiment\tests\test_guided_trajectory.py" `
  -v
```

Regression:

```powershell
python -m pytest `
  ".\pc\clock_sync\tests" `
  ".\pc\experiment\tests" `
  -q
```

---

## 9.13 Commit Checkpoint

Commit:

```text
feat(stage2.3-2.4): add deterministic guided 2C trajectory
```

---

# Task 3 — Reference Trajectory Validator

## 10. Objective

Validate that generated reference trajectory evidence satisfies the frozen Stage 2.3 structure.

---

## 10.1 Files

Create:

```text
pc/experiment/calibration/validator.py

pc/experiment/tests/test_reference_validator.py
```

---

## 10.2 Validation Requirements

The validator must verify:

```text
required columns

participant identity consistency

session identity consistency

calibration identity consistency

reference_sample_id uniqueness

cycle index validity

exact cycle count

sequence identity uniqueness

segment identity presence

direction code validity

phase validity

pause_flag semantics

hold velocity semantics

non-decreasing pc_time_ns

non-decreasing relative_time_ns

exact direction order

return-to-center requirement
```

---

## 10.3 Required Failure Cases

At minimum reject:

```text
missing required column

duplicate reference_sample_id

invalid cycle index

wrong cycle count

invalid direction code

wrong direction order

invalid phase

invalid pause_flag

non-zero hold velocity

decreasing pc_time_ns

decreasing relative_time_ns

missing return-to-center
```

---

## 10.4 RED Phase

Minimum tests:

```text
test_valid_reference_trajectory_passes

test_missing_required_column_fails

test_duplicate_reference_sample_id_fails

test_invalid_cycle_index_fails

test_wrong_cycle_count_fails

test_invalid_direction_code_fails

test_wrong_direction_order_fails

test_invalid_phase_fails

test_invalid_pause_flag_fails

test_invalid_hold_velocity_fails

test_decreasing_pc_time_fails

test_decreasing_relative_time_fails

test_missing_return_to_center_fails
```

---

## 10.5 GREEN Phase

Implement validator only.

Do not add label logic.

---

## 10.6 Verification

```powershell
python -m pytest `
  ".\pc\experiment\tests\test_reference_validator.py" `
  -v
```

Then full inherited regression.

---

## 10.7 Commit Checkpoint

```text
feat(stage2.3-2.4): validate reference trajectory
```

---

# Task 4 — Calibration Bundle Provenance

## 11. Objective

Create provenance proving that future P2C and L2C use exactly the same calibration evidence and source selection.

---

## 11.1 Files

Create:

```text
pc/experiment/calibration/provenance.py

pc/experiment/tests/test_calibration_provenance.py
```

---

## 11.2 Calibration Manifest

Generate:

```text
raw/calibration/calibration_manifest.json
```

with the Task 1 contract.

---

## 11.3 Shared Calibration Principle

The shared 2C calibration is condition-neutral.

Do not create a new Stage 2.1 condition code such as:

```text
SHARED_2C
```

Shared identity is represented by:

```text
calibration_id
```

and Stage 2.3 artifacts.

---

## 11.4 Exact Source Selection

Matching a raw IMU file hash is not sufficient.

The provenance must record an exact source-selection descriptor equivalent to:

```text
source file SHA-256

source first row and/or source sequence

source last row and/or source sequence

calibration_start_pc_ns

calibration_end_pc_ns

calibration_id
```

If multiple raw IMU evidence files participate, preserve source identity and window descriptor for each.

---

## 11.5 Equality Requirement

Future P2C and L2C must use the same:

```text
calibration_id

raw IMU source hash

source selection descriptor

reference trajectory hash

clock model hash

label configuration hash

alignment lag

derivation version
```

---

## 11.6 Hashing Requirement

Use SHA-256.

Hashing must not mutate source evidence.

---

## 11.7 RED Phase

Minimum tests:

```text
test_calibration_manifest_contains_required_fields

test_raw_imu_hash_is_preserved

test_clock_model_hash_is_preserved

test_trajectory_config_hash_is_preserved

test_source_selection_descriptor_is_recorded

test_same_inputs_produce_same_provenance

test_changed_raw_hash_changes_provenance

test_changed_clock_hash_changes_provenance

test_changed_source_window_changes_provenance

test_missing_required_source_hash_fails
```

---

## 11.8 GREEN Phase

Implement provenance helpers and calibration manifest generation.

Do not implement P2C or L2C.

---

## 11.9 Commit Checkpoint

```text
feat(stage2.3-2.4): add calibration provenance manifest
```

---

# Task 5 — Native Timestamp Mapping

## 12. Objective

Map native smartphone sensor timestamps into PC time using the already qualified clock model.

---

## 12.1 Files

Create:

```text
pc/experiment/labels/clock_mapping.py

pc/experiment/tests/test_clock_mapping_labels.py
```

---

## 12.2 Authoritative Clock API

Must call:

```python
ClockModel.map_phone_to_pc_ns(...)
```

Do not reproduce its affine mapping implementation independently.

---

## 12.3 Input

Primary timestamp input:

```text
phone_sensor_ts_ns
```

Raw sensor values remain authoritative in the original raw evidence.

---

## 12.4 Output

Create rows conforming to:

```text
derived/calibration/mapped_sensor_times.csv
```

---

## 12.5 Mapping Status

Use:

```text
MAPPED

INVALID_SOURCE_TIMESTAMP
```

---

## 12.6 Clock Quality Preconditions

Label-dependent mapping may be declared valid only if upstream qualified clock evidence is valid.

If clock evidence is:

```text
missing

malformed

non-reconstructable

quality-gate failing
```

then valid supervised output must not be declared.

Build-level outcome becomes:

```text
TECHNICAL_INVALID
```

---

## 12.7 Prohibited Behavior

Must not:

```text
fit a new clock model

estimate alpha/beta again

use pc_receive_ts_ns as label time

continue silently after an invalid clock gate
```

---

## 12.8 RED Phase

Minimum tests:

```text
test_known_affine_mapping_recovers_expected_pc_time

test_large_nanosecond_timestamp_maps_correctly

test_mapping_uses_phone_sensor_timestamp

test_receive_timestamp_is_not_used_as_supervision_time

test_positive_alpha_preserves_timestamp_order

test_invalid_source_timestamp_is_flagged

test_clock_model_sha256_is_preserved

test_invalid_clock_gate_prevents_valid_mapping
```

---

## 12.9 GREEN Phase

Implement a thin mapping layer around the existing `ClockModel`.

---

## 12.10 Verification

Targeted:

```powershell
python -m pytest `
  ".\pc\experiment\tests\test_clock_mapping_labels.py" `
  -v
```

Then:

```powershell
python -m pytest `
  ".\pc\clock_sync\tests" `
  ".\pc\experiment\tests" `
  -q
```

---

## 12.11 Commit Checkpoint

```text
feat(stage2.3-2.4): add native timestamp mapping
```

---

# Task 6 — Reference Lookup Engine

## 13. Objective

Resolve a reference trajectory state at a requested PC label time.

---

## 13.1 Files

Create:

```text
pc/experiment/labels/reference_lookup.py

pc/experiment/tests/test_reference_lookup.py
```

---

## 13.2 Interface

Equivalent interface:

```python
lookup_reference_state(
    reference_trajectory,
    label_pc_time_ns,
)
```

---

## 13.3 Valid Output

A valid lookup must return:

```text
ref_x_px

ref_y_px

ref_vx_px_s

ref_vy_px_s

direction_code

phase

sequence_id
```

---

## 13.4 Exact Match Priority

If an exact trajectory sample exists at:

```text
label_pc_time_ns
```

use that exact sample rather than interpolation.

---

## 13.5 Interpolation Rule

Interpolation is allowed only when both bracketing samples share the same:

```text
calibration_id

sequence_id

segment_index

direction_code

phase
```

---

## 13.6 Forbidden Lookup Behavior

Never:

```text
cross participant boundaries

cross session boundaries

cross calibration boundaries

cross sequence boundaries

cross direction boundaries

cross segment boundaries

cross phase boundaries

extrapolate outside the reference domain
```

---

## 13.7 Status Rules

If query time is outside the trajectory:

```text
OUTSIDE_REFERENCE
```

If lookup would require crossing a forbidden boundary:

```text
UNRESOLVED_BOUNDARY
```

Otherwise:

```text
VALID
```

---

## 13.8 RED Phase

Minimum tests:

```text
test_exact_timestamp_match_is_preferred

test_valid_same_segment_interpolation_succeeds

test_lookup_does_not_cross_sequence_boundary

test_lookup_does_not_cross_direction_boundary

test_lookup_does_not_cross_phase_boundary

test_lookup_does_not_cross_segment_boundary

test_pre_start_query_is_outside_reference

test_post_end_query_is_outside_reference

test_lookup_never_extrapolates

test_lookup_is_deterministic
```

---

## 13.9 GREEN Phase

Implement deterministic lookup.

Reference interpolation here is not the same as final IMU resampling.

Do not create a common IMU grid.

---

## 13.10 Commit Checkpoint

```text
feat(stage2.3-2.4): add reference lookup engine
```

---

# Task 7 — Lag-Aware Native Label Builder

## 14. Objective

Generate native-event reference-velocity labels using mapped sensor timestamps and the frozen lag sign convention.

---

## 14.1 Files

Create:

```text
pc/experiment/labels/label_builder.py

pc/experiment/tests/test_label_builder.py
```

---

## 14.2 Frozen Lag Sign Convention

Let:

```text
t_mapped = phone sensor timestamp mapped to PC time

tau = configured alignment lag
```

Then:

```text
t_label = t_mapped - tau
```

Integer representation:

```text
label_pc_time_ns =
pc_mapped_ts_ns -
alignment_lag_ns
```

Positive `tau` means the sensor observation at mapped PC time `t` is paired with reference motion occurring `tau` earlier.

---

## 14.3 Numeric Lag Remains Unfrozen

Stage 2.3–2.4 freezes only the sign convention.

It does not freeze:

```text
final alignment_lag_ns
```

Synthetic tests may use explicit known lag values.

Evaluation-user Fitts results must never determine the lag.

---

## 14.4 Supervised Target

Target:

```text
Y = [ref_vx, ref_vy]
```

The target is not:

```text
PC receive latency

observed cursor output

selected endpoint

Fitts performance

throughput
```

---

## 14.5 Output Artifact

Generate:

```text
derived/calibration/native_reference_labels.csv
```

Each row must remain traceable to:

```text
raw source file

raw source row

phone timestamp

mapped PC timestamp

alignment lag

label query time

reference state

derivation version
```

---

## 14.6 RED Phase

Minimum tests:

```text
test_positive_lag_uses_subtraction

test_wrong_sign_fixture_fails

test_zero_lag_uses_mapped_time

test_pre_start_label_is_outside_reference

test_post_end_label_is_outside_reference

test_boundary_crossing_is_unresolved

test_reference_velocity_is_supervised_target

test_label_preserves_raw_source_identity

test_label_output_is_deterministic
```

---

## 14.7 Mandatory Wrong-Sign Control

Create a synthetic reference velocity change at a known PC time.

Synthetic sensor observations must contain a known positive delay.

Correct implementation:

```text
t_label = t_mapped - tau
```

must recover the expected earlier target.

An intentionally wrong implementation:

```text
t_label = t_mapped + tau
```

must not recover the expected target.

---

## 14.8 GREEN Phase

Implement native label construction using:

```text
Task 5 timestamp mapping

Task 6 reference lookup
```

Do not implement final model windows.

---

## 14.9 Commit Checkpoint

```text
feat(stage2.3-2.4): add lag-aware label builder
```

---

# Task 8 — Label Validation and Build Manifest

## 15. Objective

Validate native supervision output and produce build-level provenance.

---

## 15.1 Files

Create:

```text
pc/experiment/labels/validator.py

pc/experiment/labels/manifest.py

pc/experiment/tests/test_label_validator.py

pc/experiment/tests/test_label_manifest.py
```

---

## 15.2 Row-Level Status Vocabulary

Frozen:

```text
VALID

OUTSIDE_REFERENCE

UNRESOLVED_BOUNDARY
```

---

## 15.3 Build-Level Status Vocabulary

Frozen:

```text
VALID

TECHNICAL_INVALID
```

---

## 15.4 Valid Build Semantics

Build status `VALID` does not require every source row to produce a valid label.

Rows with:

```text
OUTSIDE_REFERENCE

UNRESOLVED_BOUNDARY
```

must:

```text
remain auditable

increment invalid_label_count

not enter the valid supervised label set
```

No maximum invalid-row fraction is frozen in Stage 2.3–2.4.

---

## 15.5 TECHNICAL_INVALID Conditions

At minimum:

```text
missing clock model

malformed clock model

upstream clock-quality failure

missing source evidence

corrupted required evidence

impossible timestamp mapping

missing required provenance

zero valid labels
```

Low-quality participant movement is not automatically a technical failure.

---

## 15.6 Label Manifest

Generate:

```text
derived/calibration/label_manifest.json
```

with the Task 1 contract.

Counts must agree with actual label rows.

---

## 15.7 RED Phase

Minimum tests:

```text
test_valid_build_passes

test_row_level_invalid_labels_are_counted

test_invalid_rows_are_excluded_from_valid_supervision

test_zero_valid_labels_is_technical_invalid

test_missing_clock_model_is_technical_invalid

test_invalid_clock_gate_is_technical_invalid

test_missing_source_evidence_is_technical_invalid

test_missing_provenance_is_technical_invalid

test_manifest_counts_match_label_rows

test_manifest_hashes_match_source_inputs
```

---

## 15.8 GREEN Phase

Implement validator and build manifest generation.

---

## 15.9 Verification

Run targeted tests, then:

```powershell
python -m pytest `
  ".\pc\clock_sync\tests" `
  ".\pc\experiment\tests" `
  -q
```

---

## 15.10 Commit Checkpoint

```text
feat(stage2.3-2.4): validate label construction
```

---

# Task 9 — Synthetic End-to-End Qualification

## 16. Objective

Demonstrate the complete Stage 2.3–2.4 pipeline without real participant data.

---

## 16.1 Qualification Directory

Use:

```text
bench_data/stage2_3_2_4_synthetic_validation/
```

This evidence remains ignored by Git through the existing `bench_data/` policy.

---

## 16.2 Synthetic Qualification Pipeline

```text
synthetic raw IMU evidence
        ↓
qualified synthetic clock model
        ↓
native timestamp mapping
        ↓
deterministic guided 2C trajectory
        ↓
explicit synthetic lag
        ↓
reference lookup
        ↓
native reference labels
        ↓
provenance and label manifest
```

---

## 16.3 Required Positive Qualification

Demonstrate:

```text
2 cycles = PASS

8 directions per cycle = PASS

16 directional units = PASS

direction order = PASS

return-to-center = PASS

reference timestamp monotonicity = PASS

trajectory determinism = PASS

clock mapping = PASS

positive lag sign = PASS

reference lookup = PASS

native label build = PASS

provenance hashes = PASS
```

---

## 16.4 Required Negative Qualification

Demonstrate expected handling for:

```text
invalid clock gate

invalid source timestamp

out-of-range pre-start label

out-of-range post-end label

unresolved interpolation boundary

wrong lag-sign synthetic control
```

Expected semantics:

```text
invalid clock = TECHNICAL_INVALID

out-of-range = expected row exclusion

unresolved boundary = expected row exclusion

wrong lag sign = expected synthetic mismatch
```

---

## 16.5 Qualification Status File

Create:

```text
bench_data/stage2_3_2_4_synthetic_validation/VALIDATION_STATUS.txt
```

Recommended content:

```text
VALID_CALIBRATION=PASS
VALID_CLOCK_MAPPING=PASS
VALID_LABEL_BUILD=PASS
LAG_SIGN_TEST=PASS
INVALID_CLOCK=EXPECTED_FAIL
OUTSIDE_REFERENCE=EXPECTED_EXCLUSION
UNRESOLVED_BOUNDARY=EXPECTED_EXCLUSION
WRONG_LAG_SIGN=EXPECTED_MISMATCH
REAL_PARTICIPANT_DATA_USED=false
DESIGN_COMMIT=b1fe987
FUNCTIONAL_COMMIT=<fill-at-qualification>
```

---

## 16.6 No Real Participant Data

Qualification must state:

```text
REAL_PARTICIPANT_DATA_USED=false
```

No human research recording is needed for software qualification.

---

## 16.7 Full Regression

Run:

```powershell
python -m pytest `
  ".\pc\clock_sync\tests" `
  ".\pc\experiment\tests" `
  -v
```

Also run receiver safety regression:

```powershell
python -m pytest `
  ".\pc\receiver\test_udp_receiver.py" `
  -q
```

All must pass.

---

## 16.8 Source Boundary Audit

Implementation baseline:

```text
b1fe987
```

Audit:

```powershell
git diff `
  "b1fe987..HEAD" `
  --name-status
```

Permitted implementation areas:

```text
pc/experiment/calibration/**

pc/experiment/labels/**

pc/experiment/tests/**

configs/experiment/**

docs/superpowers/plans/**

docs/decisions/**
```

Changes to these require explicit justification and requalification:

```text
pc/clock_sync/**

pc/receiver/**

android/**
```

`pc/cursor_preview/**` must not be silently promoted into the final experimental controller.

---

## 16.9 Git Evidence Policy

Verify:

```powershell
git check-ignore -v `
  "bench_data/stage2_3_2_4_synthetic_validation/VALIDATION_STATUS.txt"
```

Synthetic qualification evidence must remain untracked.

---

## 16.10 Commit Checkpoint

If Task 9 adds tracked tests or tracked synthetic-fixture generators, commit them explicitly:

```text
test(stage2.3-2.4): qualify synthetic clock-to-label pipeline
```

If Task 9 creates only ignored qualification evidence and no tracked source changes, do not create an empty commit.

---

# Task 10 — Freeze Stage 2.3–2.4

## 17. Objective

Freeze the qualified Guided 2C and Clock-to-Label work package.

---

## 17.1 Decision Document

Create:

```text
docs/decisions/stage2_3_2_4_guided_2c_clock_label_v1_0.md
```

---

## 17.2 Required Decision Content

The decision document must record:

```text
Stage identity

design specification path

implementation plan path

design commit

final functional commit

artifact schemas

2C structural semantics

fixed direction order

phase vocabulary

clock mapping dependency

clock quality dependency

lag sign convention

row-level label status vocabulary

build-level status vocabulary

shared calibration provenance requirement

exact source-selection requirement

synthetic qualification result

regression result

source boundary result

no participant data statement

explicit non-freezes

final tag
```

---

## 17.3 Explicit Non-Freezes

The freeze decision must state that Stage 2.3–2.4 does not freeze:

```text
final 2C cycle duration

final movement radius

final speed profile

final pause durations

final reference emission cadence

final numeric alignment lag

final IMU analysis frequency

final common time grid

IMU interpolation method

causal filter cutoff

bias-correction method

gyro/accelerometer common-grid alignment

active-motion threshold

P2C regularization

P2C solver settings

L0 model hyperparameters

L2C optimization settings

Fitts geometry

Fitts throughput formula implementation
```

---

## 17.4 Final Regression

Run:

```powershell
python -m pytest `
  ".\pc\clock_sync\tests" `
  ".\pc\experiment\tests" `
  -q
```

Receiver regression:

```powershell
python -m pytest `
  ".\pc\receiver\test_udp_receiver.py" `
  -q
```

Both must exit `0`.

---

## 17.5 Participant Data Policy

Verify:

```powershell
git check-ignore -v "participant_data/"
```

Verify synthetic qualification evidence is ignored.

---

## 17.6 Final Source Boundary

Run:

```powershell
git diff `
  "b1fe987..HEAD" `
  --name-status
```

Then inspect for any unexpected changes.

No unexplained changes may exist in:

```text
pc/clock_sync/**

pc/receiver/**

android/**
```

---

## 17.7 Final Clean-State Gate

Before final tag:

```powershell
git diff --name-status

git diff --cached --name-status
```

Both must be empty.

Known unrelated untracked engineering evidence may remain untracked.

---

## 17.8 Freeze Decision Commit

Commit:

```text
docs(stage2.3-2.4): freeze guided 2C and clock-to-label v1.0
```

---

## 17.9 Annotated Freeze Tag

Tag:

```text
stage2.3-2.4-guided-2c-clock-label-v1.0
```

Message:

```text
Freeze Stage 2.3-2.4 guided 2C and clock-to-label v1.0
```

Command:

```powershell
git tag `
  -a `
  stage2.3-2.4-guided-2c-clock-label-v1.0 `
  -m "Freeze Stage 2.3-2.4 guided 2C and clock-to-label v1.0"
```

---

## 17.10 Tag Verification

Verify:

```powershell
git rev-parse HEAD

git rev-list `
  -n 1 `
  stage2.3-2.4-guided-2c-clock-label-v1.0
```

The commit hashes must be identical.

---

# 18. Planned Commit Sequence

The intended commit history is:

```text
b1fe987
docs(stage2.3-2.4): define guided 2C and clock-to-label design

<next>
docs(stage2.3-2.4): add guided 2C implementation plan

<next>
feat(stage2.3-2.4): add calibration artifact schemas

<next>
feat(stage2.3-2.4): add deterministic guided 2C trajectory

<next>
feat(stage2.3-2.4): validate reference trajectory

<next>
feat(stage2.3-2.4): add calibration provenance manifest

<next>
feat(stage2.3-2.4): add native timestamp mapping

<next>
feat(stage2.3-2.4): add reference lookup engine

<next>
feat(stage2.3-2.4): add lag-aware label builder

<next>
feat(stage2.3-2.4): validate label construction

<optional if tracked qualification support exists>
test(stage2.3-2.4): qualify synthetic clock-to-label pipeline

<final>
docs(stage2.3-2.4): freeze guided 2C and clock-to-label v1.0
```

---

# 19. Final Exit Gate

Stage 2.3–2.4 is formally complete only when every condition below is satisfied.

```text
DESIGN

[ ] design specification committed
[ ] implementation plan committed


SCHEMAS

[ ] reference trajectory schema tested
[ ] calibration manifest schema tested
[ ] mapped sensor time schema tested
[ ] native label schema tested
[ ] label configuration schema tested
[ ] label manifest schema tested


GUIDED 2C

[ ] exactly two cycles tested
[ ] exactly eight directions per cycle tested
[ ] direction order tested
[ ] return-to-center tested
[ ] phase order tested
[ ] deterministic trajectory tested
[ ] unique reference IDs tested
[ ] deterministic sequence IDs tested
[ ] hold velocity tested
[ ] pause semantics tested
[ ] non-decreasing PC timestamps tested


TRAJECTORY VALIDATION

[ ] invalid cycle rejected
[ ] invalid direction rejected
[ ] wrong direction order rejected
[ ] invalid phase rejected
[ ] duplicate reference ID rejected
[ ] decreasing timestamps rejected
[ ] invalid hold velocity rejected
[ ] missing return-to-center rejected


PROVENANCE

[ ] raw IMU SHA-256 preserved
[ ] clock model SHA-256 preserved
[ ] trajectory config SHA-256 preserved
[ ] calibration_id preserved
[ ] exact source selection descriptor preserved
[ ] source-window change changes provenance
[ ] same input gives deterministic provenance


CLOCK MAPPING

[ ] existing ClockModel reused
[ ] known affine mapping tested
[ ] large nanosecond timestamp tested
[ ] phone_sensor_ts_ns used
[ ] pc_receive_ts_ns not used as supervision time
[ ] invalid timestamp handled
[ ] invalid clock gate fails closed
[ ] clock model provenance preserved


REFERENCE LOOKUP

[ ] exact match tested
[ ] same-segment interpolation tested
[ ] cross-sequence lookup rejected
[ ] cross-direction lookup rejected
[ ] cross-phase lookup rejected
[ ] cross-segment lookup rejected
[ ] pre-start extrapolation rejected
[ ] post-end extrapolation rejected
[ ] deterministic lookup tested


LAG AND LABELS

[ ] positive lag uses t_mapped - tau
[ ] zero lag tested
[ ] wrong-sign synthetic control fails
[ ] label_pc_time_ns tested
[ ] reference velocity is target
[ ] raw source identity preserved
[ ] OUTSIDE_REFERENCE tested
[ ] UNRESOLVED_BOUNDARY tested
[ ] label output deterministic


LABEL BUILD

[ ] VALID build tested
[ ] TECHNICAL_INVALID build tested
[ ] invalid rows counted
[ ] invalid rows excluded from valid supervision
[ ] zero valid labels rejected
[ ] missing clock rejected
[ ] missing evidence rejected
[ ] missing provenance rejected
[ ] manifest counts match output
[ ] manifest hashes match inputs


SYNTHETIC QUALIFICATION

[ ] valid synthetic 2C PASS
[ ] valid clock mapping PASS
[ ] valid native label build PASS
[ ] lag-sign test PASS
[ ] invalid clock EXPECTED FAIL
[ ] outside-reference case demonstrated
[ ] unresolved-boundary case demonstrated
[ ] wrong lag sign EXPECTED MISMATCH
[ ] source hashes recorded
[ ] REAL_PARTICIPANT_DATA_USED=false


REGRESSION

[ ] Stage 2.1 experiment tests PASS
[ ] clock-sync tests PASS
[ ] receiver safety tests PASS


BOUNDARIES

[ ] no Stage 2.1 schema modified
[ ] no new affine clock fitter created
[ ] no final common IMU grid frozen
[ ] no final resampling frequency frozen
[ ] no final numeric lag frozen
[ ] no P0 implemented
[ ] no P2C fitting implemented
[ ] no L0 implemented
[ ] no L2C implemented
[ ] no Fitts task implemented
[ ] no throughput implementation added


DATA POLICY

[ ] participant_data/ ignored
[ ] synthetic qualification evidence ignored
[ ] no real participant data collected during qualification


GIT

[ ] tracked worktree clean
[ ] staged worktree clean
[ ] source boundary audit PASS
[ ] decision document committed
[ ] annotated freeze tag created
[ ] freeze tag points to final qualified commit
```

---

# 20. Stage 2.3–2.4 Completion State

After successful completion:

```text
Stage 1
Engineering Qualification
        ✅ COMPLETE
        ↓

Stage 2.1
Experimental Data Contract v1.0
        ✅ FROZEN
        ↓

Stage 2.3
Guided 2C Calibration
        ✅ FROZEN
        ↓

Stage 2.4
Clock Mapping + Label Construction
        ✅ FROZEN
        ↓

Stage 2.5
Common Time Grid + Preprocessing
        NEXT
```

Stage 2.3–2.4 must end with trustworthy and reproducible timing, calibration, provenance, and supervision artifacts.

It must not silently convert candidate engineering parameters into final participant-study parameters.

Only after the complete exit gate passes may the project proceed to Stage 2.5.