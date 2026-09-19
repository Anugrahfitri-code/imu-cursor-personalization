# Stage 2.1 — Experimental Data Contract & Session Schema Design v1.0

**Status:** REVIEW CANDIDATE — IMPLEMENTATION NOT STARTED
**Date:** 2026-09-17
**Project:** IMU Cursor Personalization
**Stage:** 2.1 — Experimental Data Contract & Session Schema

## 1. Purpose

Stage 2.1 defines the authoritative data contract for the formal smartphone-IMU cursor experiment before implementation of P0, P2C, L0, L2C, the Fitts task, or participant data collection.

The contract exists to ensure that all experimental conditions produce structurally comparable, traceable, auditable data and that definitions are not changed retrospectively after participant outcomes are observed.

Stage 2.1 defines data structure and provenance. It does not define experimental superiority, model performance, participant outcomes, or final statistical conclusions.

## 2. Relationship to Existing Engineering Infrastructure

Existing subsystems retain their current roles:

* `pc/receiver` remains transport infrastructure.
* `pc/clock_sync` remains timing and clock-alignment infrastructure.
* `pc/cursor_preview` remains engineering-preview infrastructure only.
* `pc/cursor_preview` is not P0 and must not become the participant experiment application.
* M2.3 session-quality rules remain independent of participant-performance outcomes.

Formal experiment functionality will be implemented as a new subsystem:

`pc/experiment/`

Transport behavior must remain fixed across P0, P2C, L0, and L2C unless a later prospectively versioned protocol explicitly changes it.

## 3. Core Data Principles

### 3.1 Raw evidence is immutable

Raw files represent observations generated during acquisition.

After a session is finalized, raw files must not be manually edited, overwritten, filtered in place, or destructively resampled.

Corrections and transformations must create new derived artifacts.

### 3.2 Raw and derived data are separate

Raw observations must not contain inferential participant-performance metrics merely for convenience.

Examples of derived values include:

* movement time;
* effective width;
* effective index of difficulty;
* Fitts throughput;
* overshoot count;
* endpoint error;
* path efficiency;
* statistical exclusions.

These belong in the derived layer.

### 3.3 One structural schema across conditions

P0, P2C, L0, and L2C must use the same session, trial-event, cursor-sample, and provenance structures.

Condition-specific algorithms may differ, but data representation must not silently differ by condition.

### 3.4 Participant identity is pseudonymous

Experimental files must not contain:

* participant name;
* email;
* telephone number;
* student number;
* government identifier;
* other directly identifying information.

The experimental identifier is an opaque pseudonymous `participant_id`.

Any identity-linkage document required by ethics procedures must remain outside the experimental dataset and outside this repository.

### 3.5 Development, pilot, and evaluation data are distinct

Every formal session contains a `dataset_role`.

Allowed values:

* `development`
* `pilot`
* `evaluation`
* `synthetic`

Development data used to design, train, tune, or choose models must not later be silently treated as independent evaluation data.

Pilot data remains distinguishable from the final evaluation dataset.

### 3.6 Timing must remain reconstructable

The contract must preserve sufficient provenance to reconstruct relationships among:

* native Android IMU timestamps;
* Android sequence identifiers;
* PC UDP reception evidence;
* official affine phone-to-PC clock mapping;
* cursor-update timestamps;
* target-event timestamps;
* participant selections.

### 3.7 No final resampling frequency is frozen in Stage 2.1

Raw Android IMU remains at its native observed acquisition rate.

Stage 2.1 does not define a final 100 Hz, 125 Hz, or other resampling grid.

The final preprocessing/resampling protocol must be frozen separately before participant evaluation.

## 4. Dataset Root

Formal experiment data uses a dedicated untracked data root:

`participant_data/`

Canonical structure:

```text
participant_data/
└── <participant_id>/
    └── <session_id>/
        ├── manifest.json
        ├── raw/
        │   ├── trial_events.csv
        │   ├── cursor_samples.csv
        │   ├── calibration_events.csv
        │   ├── imu/
        │   └── clock/
        ├── artifacts/
        │   ├── calibration_parameters.json
        │   └── model_manifest.json
        └── derived/
            ├── trial_metrics.csv
            ├── sequence_metrics.csv
            └── quality_flags.csv
```

`participant_data/` must not be committed to Git.

Schema definitions, validators, synthetic fixtures, and documentation are version controlled.

## 5. Identifiers

### 5.1 participant_id

`participant_id` is opaque and contains no meaningful personal information.

Recommended generated form:

`P` followed by seven uppercase alphanumeric characters.

Example:

`P7K4M2Q8`

Uniqueness must be validated before session creation.

### 5.2 session_id

`session_id` uniquely identifies one experimental session.

It must not contain participant names or other direct identifiers.

### 5.3 Condition code

Allowed experimental condition codes are:

* `P0`
* `P2C`
* `L0`
* `L2C`

Stage 2.1 defines these codes only.

The mathematical and algorithmic definitions of each condition are frozen in later condition-specific protocols.

### 5.4 Hierarchical experimental identifiers

The common hierarchy is:

```text
participant
└── session
    └── condition
        └── block
            └── sequence
                └── trial
```

Required identifiers therefore include:

* `participant_id`
* `session_id`
* `condition_code`
* `block_id`
* `sequence_id`
* `trial_id`

## 6. manifest.json

`manifest.json` is the authoritative provenance record for one session.

Required top-level fields:

```text
schema_version
participant_id
session_id
dataset_role
session_status

experiment_protocol_version
condition_order

functional_commit
experiment_software_version

device
display
android_evidence
clock_evidence
files
```

### 6.1 schema_version

Initial value:

`1.0`

A breaking change to required fields, semantics, identifiers, or units requires a new schema version.

### 6.2 session_status

Allowed values:

* `open`
* `closed`

A `closed` session has finalized raw evidence and must not have raw evidence modified in place.

### 6.3 experiment protocol

The manifest records:

```text
experiment_protocol_version
condition_definition_versions
calibration_protocol_versions
```

This makes condition behavior explicit rather than inferred from filenames.

### 6.4 software provenance

Required:

```text
functional_commit
experiment_software_version
```

Model-based conditions additionally reference an explicit model artifact.

### 6.5 device metadata

Required:

```text
manufacturer
model
android_version
api_level
android_session_id
```

### 6.6 display metadata

Required:

```text
display_width_px
display_height_px
experiment_window_width_px
experiment_window_height_px
display_scale_factor
```

If refresh rate is available it should also be preserved as metadata.

### 6.7 Android evidence

Required references:

```text
imu_file
imu_sha256
android_metadata_file
android_metadata_sha256
```

### 6.8 Clock evidence

Required references:

```text
clock_model_file
clock_model_sha256
sync_probes_file
sync_probes_sha256
```

The session-quality evaluation reference may additionally be preserved.

### 6.9 File provenance

Each authoritative evidence file referenced by the manifest contains:

```text
relative_path
sha256
role
```

The manifest does not include its own SHA-256 value to avoid circular hashing.

A separate session-level manifest hash may be generated during finalization.

## 7. raw/trial_events.csv

`trial_events.csv` records discrete experimental events.

Required columns:

```text
event_id
participant_id
session_id
condition_code
block_id
sequence_id
trial_id
event_type
pc_time_ns
target_id
target_x_px
target_y_px
target_width_px
target_height_px
pointer_x_px
pointer_y_px
event_note
```

`pc_time_ns` uses the PC monotonic timebase.

### 7.1 Allowed event types

Initial vocabulary:

```text
session_start
session_end
condition_start
condition_end
block_start
block_end
sequence_start
sequence_end
trial_start
target_onset
selection
trial_complete
trial_abort
calibration_start
calibration_end
```

The event vocabulary is version controlled.

### 7.2 Movement onset is not a raw event by default

`movement_start` must not be written as authoritative raw data unless the experiment records a literal participant/system event representing movement onset.

If movement onset is inferred from cursor motion, velocity, threshold crossing, or another algorithm, it is derived data and must include an explicit derivation version.

## 8. raw/cursor_samples.csv

`cursor_samples.csv` records the actual cursor trajectory produced by the experimental cursor loop.

Required columns:

```text
sample_id
participant_id
session_id
condition_code
block_id
sequence_id
trial_id
pc_time_ns
cursor_x_px
cursor_y_px
active_target_id
source_seq_start
source_seq_end
```

### 8.1 Timestamp semantics

`pc_time_ns` is the PC monotonic timestamp associated with emission or logging of the cursor state.

It must not be replaced by wall-clock time.

### 8.2 Source sequence references

`source_seq_start` and `source_seq_end` provide traceability to the Android IMU evidence used to produce the cursor update.

For a single-sample mapping:

```text
source_seq_start == source_seq_end
```

For temporal/windowed models, the range may span multiple source sequences.

This supports both instantaneous and temporal models without changing the trajectory schema.

### 8.3 Sampling frequency

No fixed cursor-sample rate is assumed by the schema.

Temporal ordering and timing derive from `pc_time_ns`.

## 9. raw/calibration_events.csv

Calibration observations are stored independently from calibration parameters.

Required columns:

```text
calibration_event_id
participant_id
session_id
condition_code
calibration_id
step_id
event_type
pc_time_ns
reference_target_id
source_seq_start
source_seq_end
instruction_code
event_note
```

Calibration events represent what happened.

Fitted gains, coefficients, parameters, and learned states are artifacts, not raw observations.

## 10. artifacts/calibration_parameters.json

When a condition produces participant-specific calibration parameters, they are stored as a versioned artifact.

Required fields:

```text
artifact_version
artifact_id
participant_id
session_id
condition_code
calibration_id
calibration_protocol_version
mapping_algorithm_version
source_event_file_sha256
source_imu_sha256
parameters
created_utc
```

The exact contents of `parameters` depend on the later condition-specific protocol.

Stage 2.1 does not define P2C or L2C parameter mathematics.

## 11. artifacts/model_manifest.json

Model-based conditions must not depend on an unidentified model file.

Required fields:

```text
model_manifest_version
model_id
condition_code
model_type
model_file
model_sha256
training_code_commit
training_protocol_version
training_dataset_role
training_dataset_id
frozen_before_evaluation
```

For evaluation sessions:

`frozen_before_evaluation` must be `true`.

Development participants or sessions used for model selection/tuning must be traceable through the training dataset provenance.

## 12. Derived Trial Metrics

`derived/trial_metrics.csv` is not raw evidence.

The initial schema reserves fields such as:

```text
participant_id
session_id
condition_code
block_id
sequence_id
trial_id
movement_time_ms
selection_error
endpoint_error_px
path_length_px
overshoot_count
derivation_version
```

Stage 2.1 does not define the final algorithms for these metrics.

Fields may remain absent or unpopulated until the corresponding analysis protocol is frozen.

## 13. Derived Sequence Metrics

`derived/sequence_metrics.csv` is intended for sequence-level outcomes.

Reserved fields include:

```text
participant_id
session_id
condition_code
block_id
sequence_id
trial_count
error_rate
effective_width_px
effective_index_of_difficulty_bits
throughput_bps
derivation_version
```

Sequence-level Fitts throughput is expected to become a primary experimental outcome, but the final formula, aggregation, exclusions, effective-width implementation, and validity criteria are not frozen in Stage 2.1.

## 14. quality_flags.csv

Quality-control decisions are preserved independently from raw evidence.

Required structure:

```text
scope_type
scope_id
flag_code
flag_value
reason
rule_version
created_utc
```

Possible scope types include:

```text
session
condition
block
sequence
trial
```

Quality flags must never delete or rewrite the underlying raw row.

## 15. Relationship to Android IMU and Clock Data

The experiment contract does not duplicate or redefine the Android IMU protocol.

The authoritative Android raw evidence remains the acquisition output generated by the qualified Android subsystem.

The experiment session references or copies that evidence and records its SHA-256.

The official affine clock model remains the authoritative phone-to-PC mapping.

Mapped timestamps may be produced in derived processing, but native phone timestamps must remain preserved.

## 16. Condition Independence

The raw schema must not depend on condition-specific columns that exist only for one condition.

Condition-specific model/calibration data belongs in artifacts.

This prevents P0, P2C, L0, and L2C from acquiring structurally different evidence.

## 17. Trial Count Independence

The Stage 2.1 schema does not freeze:

* number of blocks;
* number of sequences;
* number of targets;
* number of transitions;
* the current candidate `4 × 2 × 9 = 72` transitions.

Those values belong to the later experimental protocol.

The schema supports any prospectively frozen trial count without structural modification.

## 18. Raw Data Invariants

A finalized session must satisfy at least:

```text
participant_id consistent across all session files
session_id consistent across all session files
condition codes valid
event_id unique
cursor sample_id unique
timestamps parse as integer nanoseconds
PC timestamps are nondecreasing within each ordered stream
all referenced trial IDs exist
all referenced block/sequence relationships are valid
all required evidence paths exist
all required SHA-256 hashes match
dataset_role is valid
session_status == closed
```

Additional invariants will be added only through explicit schema-version changes.

## 19. Synthetic Validation

Stage 2.1 implementation must include a fully synthetic session fixture.

The synthetic fixture:

* contains no human participant data;
* uses `dataset_role = synthetic`;
* exercises all four condition codes;
* contains trial events;
* contains cursor trajectories;
* contains calibration events where applicable;
* contains placeholder but structurally valid provenance;
* must pass the same schema validator used for future real sessions.

A deliberately corrupted synthetic fixture must also be used to demonstrate validator failure.

## 20. Repository Boundaries

Version-controlled Stage 2.1 implementation is expected under:

```text
pc/experiment/
```

Version-controlled tests are expected under:

```text
pc/experiment/tests/
```

The participant dataset itself must remain outside version control.

`pc/cursor_preview` remains unchanged unless a later separately approved engineering task requires shared extraction/refactoring.

No participant experiment logic should be added to `cursor_preview` merely for convenience.

## 21. Stage 2.1 Deliverables

Stage 2.1 implementation will provide:

1. this design specification;
2. authoritative Experimental Data Contract v1.0 decision document;
3. machine-readable manifest schema;
4. machine-readable or programmatically defined CSV schemas;
5. Python data models;
6. schema validator;
7. unit tests;
8. valid synthetic session fixture;
9. invalid synthetic session fixture or mutation-based validation test;
10. validation CLI;
11. schema version freeze.

## 22. Explicit Non-Goals

Stage 2.1 does not implement:

* P0 cursor mapping;
* P2C mapping;
* L0 temporal model;
* L2C temporal personalization;
* 2C calibration mathematics;
* Fitts target UI;
* click/selection interaction design;
* final movement-onset algorithm;
* final movement-time definition;
* final effective-width algorithm;
* final Fitts throughput formula;
* final overshoot algorithm;
* final endpoint-error algorithm;
* final resampling grid;
* participant recruitment;
* pilot data collection;
* inferential statistics.

## 23. Change Control

Once Experimental Data Contract v1.0 is frozen:

* additive nonsemantic metadata changes require review;
* changes to required fields, units, identifiers, timestamp semantics, provenance semantics, or raw/derived boundaries require a new schema version;
* participant outcome data must never be used retrospectively to redefine raw evidence semantics.

## 24. Exit Criteria

Stage 2.1 is complete only when:

* the data-contract decision document is frozen;
* schemas and validators are version controlled;
* all Stage 2.1 tests pass;
* a valid synthetic session passes validation;
* a deliberately invalid synthetic session fails validation for the expected reason;
* no real participant data have been collected;
* no final Fitts outcome formula or resampling choice has been introduced implicitly.

Only then may the project proceed to the next experimental-system work package.
