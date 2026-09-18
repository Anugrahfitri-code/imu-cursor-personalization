Bisa. Supaya tidak repot dengan PowerShell here-string yang panjang,
**buat file ini secara manual**:

`docs/decisions/stage2_1_experimental_data_contract_v1_0.md`

Lalu copy-paste **seluruh isi berikut** ke file tersebut dan save
sebagai UTF-8.

``` markdown
# Stage 2.1 Experimental Data Contract v1.0 Freeze Decision

## 1. Decision Identity

Stage: 2.1

Schema version: 1.0

Status: QUALIFIED FOR FREEZE. The formal freeze becomes effective when this decision is committed and the annotated tag stage2.1-experimental-data-contract-v1.0 points to that commit.

Design specification:

`docs/superpowers/specs/2026-09-17-stage2-1-experimental-data-contract-design.md`

Implementation plan:

`docs/superpowers/plans/2026-09-17-stage2-1-experimental-data-contract.md`

Functional qualification commit:

`ca55d30`

Branch used for qualification:

`research/stage2.1-experimental-data-contract-v1.0`

---

## 2. Scope of This Freeze

Stage 2.1 freezes the experimental data contract and its supporting validation infrastructure.

The frozen scope includes:

- contract constants;
- CSV schemas;
- session manifest contract;
- machine-readable manifest schema;
- cross-file session validation;
- session evidence SHA-256 generation;
- session hash verification;
- validation and finalization CLI;
- synthetic end-to-end qualification.

Stage 2.1 does not freeze experimental controller algorithms, Fitts-law outcome computation, or IMU preprocessing and resampling parameters.

---

## 3. Allowed Dataset Roles

The following dataset roles are frozen:

```text
development
pilot
evaluation
synthetic
```

------------------------------------------------------------------------

## 4. Allowed Condition Codes

The following experimental condition identifiers are frozen:

``` text
P0
P2C
L0
L2C
```

P0/P2C/L0/L2C codes are frozen as identifiers only.

Their algorithms are not defined by Stage 2.1.

No P0 implementation was added in Stage 2.1.

No P2C implementation was added in Stage 2.1.

No L0 implementation was added in Stage 2.1.

No L2C implementation was added in Stage 2.1.

------------------------------------------------------------------------

## 5. CSV Schemas

### 5.1 `raw/trial_events.csv`

Frozen ordered columns:

``` text
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

### 5.2 `raw/cursor_samples.csv`

Frozen ordered columns:

``` text
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

### 5.3 `raw/calibration_events.csv`

Frozen ordered columns:

``` text
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

### 5.4 `derived/quality_flags.csv`

Frozen ordered columns:

``` text
scope_type
scope_id
flag_code
flag_value
reason
rule_version
created_utc
```

------------------------------------------------------------------------

## 6. Session Manifest Contract

Machine-readable manifest schema:

`pc/experiment/schemas/manifest.schema.json`

The manifest schema uses schema version:

``` text
1.0
```

Required top-level fields:

``` text
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

Allowed session status values:

``` text
open
closed
```

Allowed dataset-role values:

``` text
development
pilot
evaluation
synthetic
```

Allowed `condition_order` identifiers:

``` text
P0
P2C
L0
L2C
```

The Python manifest contract and machine-readable JSON schema use the
same required top-level field set.

------------------------------------------------------------------------

## 7. Contract Constants

The Stage 2.1 contract freezes:

``` text
SCHEMA_VERSION = 1.0
```

Allowed dataset roles:

``` text
development
pilot
evaluation
synthetic
```

Allowed session statuses:

``` text
open
closed
```

Allowed conditions:

``` text
P0
P2C
L0
L2C
```

The experimental event vocabulary includes:

``` text
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

------------------------------------------------------------------------

## 8. Cross-File Session Validation

The Stage 2.1 session validator is implemented in:

`pc/experiment/validator.py`

Validation interface:

``` text
python -m pc.experiment.cli validate <session-dir>
```

Successful machine-readable output:

``` text
VALIDATION_STATUS=PASS
```

Failed validation produces:

``` text
VALIDATION_STATUS=FAIL
```

The cross-file validator performs the following checks in the frozen
validation flow:

1.  session directory exists;
2.  manifest exists and parses;
3.  manifest structural validation;
4.  required raw CSV files exist;
5.  CSV headers exactly match the frozen contracts;
6.  `participant_id` is consistent with the session manifest;
7.  `session_id` is consistent with the session manifest;
8.  condition codes are valid;
9.  `event_id` values are unique;
10. `sample_id` values are unique;
11. `pc_time_ns` parses as an integer;
12. ordered cursor samples do not decrease in `pc_time_ns`;
13. cursor trial references resolve to known trial IDs;
14. finalized-session validation requires `session_status=closed`.

The validator reports detected failures and does not modify source
evidence.

------------------------------------------------------------------------

## 9. Session Finalization Interface

Session finalization command:

``` text
python -m pc.experiment.cli finalize <session-dir>
```

The finalization flow is:

``` text
validate_session
    â†“
validation PASS?
    â†“ yes
write SESSION_SHA256SUMS.txt
    â†“
verify SESSION_SHA256SUMS.txt
    â†“
return success
```

If validation fails, finalization returns failure and no new hash
manifest is generated.

Successful finalization reports:

``` text
FINALIZATION_STATUS=PASS
```

Failed finalization reports:

``` text
FINALIZATION_STATUS=FAIL
```

CLI exit-code contract:

``` text
0 = success
1 = validation or hash failure
2 = command or input usage failure
```

------------------------------------------------------------------------

## 10. Session Evidence SHA-256 Contract

Session evidence hashing is implemented in:

`pc/experiment/session_hash.py`

The generated hash-manifest filename is:

``` text
SESSION_SHA256SUMS.txt
```

SHA-256 entries use the format:

``` text
<SHA256><two spaces><session-relative-path>
```

The frozen hashing rules are:

-   SHA-256 values are uppercase;
-   paths are relative to the session directory;
-   paths use forward slashes;
-   entries are sorted by relative path;
-   `SESSION_SHA256SUMS.txt` excludes itself;
-   source evidence is read but not modified during hash generation.

The hash writer does not:

-   modify raw CSV files;
-   modify IMU evidence;
-   modify clock evidence;
-   delete source evidence;
-   rewrite manifest contents.

SHA-256 verification command:

``` text
python -m pc.experiment.cli verify-hashes <session-dir>
```

Successful hash verification reports:

``` text
HASH_VERIFY_STATUS=PASS
```

Failed hash verification reports:

``` text
HASH_VERIFY_STATUS=FAIL
```

------------------------------------------------------------------------

## 11. Automated Test Qualification

At functional qualification commit:

``` text
ca55d30
```

the complete Stage 2.1 experiment test package produced:

``` text
46 passed
```

The tested components include:

-   contract constants;
-   CSV schemas;
-   CSV-header validation;
-   manifest contract;
-   manifest schema consistency;
-   cross-file validator;
-   synthetic fixture infrastructure;
-   evidence hashing;
-   hash-manifest sorting;
-   relative-path handling;
-   self-exclusion;
-   modified-file detection;
-   missing-file detection;
-   CLI validation;
-   CLI finalization;
-   hash-verification CLI;
-   CLI exit codes;
-   machine-readable CLI status output.

------------------------------------------------------------------------

## 12. Synthetic End-to-End Qualification

Synthetic end-to-end qualification evidence is stored under:

`bench_data/stage2_1_synthetic_validation/`

The directory is intentionally excluded from Git by the repository
`bench_data/` ignore policy.

The valid synthetic qualification session used:

``` text
dataset_role=synthetic
participant_id=P7K4M2Q8
condition_order=P0,P2C,L0,L2C
REAL_PARTICIPANT_DATA_USED=false
```

No human participant information was used.

The valid session contained the following evidence structure:

``` text
manifest.json
raw/trial_events.csv
raw/cursor_samples.csv
raw/calibration_events.csv
raw/imu/imu.csv
raw/imu/meta.txt
raw/clock/clock_model.json
raw/clock/sync_probes.csv
artifacts/calibration_parameters.json
artifacts/model_manifest.json
derived/quality_flags.csv
```

Before finalization:

``` text
SESSION_SHA256SUMS.txt = absent
```

The valid session validation produced:

``` text
VALIDATION_STATUS=PASS
```

with exit code:

``` text
0
```

The valid session finalization produced:

``` text
VALIDATION_STATUS=PASS
HASH_VERIFY_STATUS=PASS
FINALIZATION_STATUS=PASS
```

with exit code:

``` text
0
```

Finalization successfully created:

``` text
SESSION_SHA256SUMS.txt
```

Independent hash verification produced:

``` text
HASH_VERIFY_STATUS=PASS
```

with exit code:

``` text
0
```

The valid-session hash manifest contained:

``` text
HASH_ENTRIES=11
SELF_REFERENCE_COUNT=0
```

------------------------------------------------------------------------

## 13. Synthetic Expected-Failure Qualification

A copy of the valid synthetic session was created as:

`bench_data/stage2_1_synthetic_validation/invalid_session/`

Only one copied cursor-sample `condition_code` was intentionally
changed.

Original condition:

``` text
P0
```

Modified condition:

``` text
INVALID
```

Number of deliberately modified rows:

``` text
1
```

Validation of the copied invalid session correctly produced:

``` text
VALIDATION_STATUS=FAIL
```

and reported:

``` text
INVALID_CONDITION_CODE
```

The invalid-session validation command returned exit code:

``` text
1
```

This is an expected qualification failure and demonstrates that the
validator rejects an invalid condition code.

------------------------------------------------------------------------

## 14. Preserved Synthetic Qualification Status

The qualification status is stored locally at:

`bench_data/stage2_1_synthetic_validation/VALIDATION_STATUS.txt`

The recorded qualification result is:

``` text
VALID_SESSION=PASS
VALID_SESSION_HASH_VERIFY=PASS
INVALID_SESSION=EXPECTED_FAIL
REAL_PARTICIPANT_DATA_USED=false
SCHEMA_VERSION=1.0
FUNCTIONAL_COMMIT=ca55d30
STAGE2_1_TESTS=46_PASS
```

The synthetic evidence remains untracked.

------------------------------------------------------------------------

## 15. Repository Evidence Policy

`participant_data/` is excluded from Git.

Stage 2.1 synthetic qualification evidence under:

`bench_data/stage2_1_synthetic_validation/`

is also excluded from Git through the repository `bench_data/` ignore
rule.

Source code, tests, contracts, schemas, plans, specifications, and the
present decision document remain version-controlled.

No real participant data were collected during Stage 2.1.

------------------------------------------------------------------------

## 16. Explicit Non-Freezes

Stage 2.1 does not freeze any Fitts outcome metric.

Stage 2.1 does not freeze any final effective-width implementation.

Stage 2.1 does not freeze Fitts aggregation or exclusion rules.

Stage 2.1 does not freeze a final IMU resampling frequency.

Stage 2.1 does not freeze a final common IMU time grid.

Stage 2.1 does not freeze a final interpolation method.

Stage 2.1 does not freeze a final causal-filter configuration.

Stage 2.1 does not implement or freeze the P0 controller algorithm.

Stage 2.1 does not implement or freeze the P2C personalization
algorithm.

Stage 2.1 does not implement or freeze the L0 learned controller.

Stage 2.1 does not implement or freeze the L2C personalized learned
adapter.

Therefore:

``` text
P0/P2C/L0/L2C codes are frozen as identifiers only.
Their algorithms are not defined by Stage 2.1.
```

No Fitts metric is frozen.

No resampling grid is frozen.

No condition algorithm is implemented by Stage 2.1.

------------------------------------------------------------------------

## 17. Stage 2.1 Source Boundary

Stage 2.1 implementation is intended to remain isolated from previously
qualified engineering subsystems.

Permitted Stage 2.1 changes are limited to:

``` text
.gitignore
pc/experiment/**
docs/decisions/stage2_1_experimental_data_contract_v1_0.md
docs/superpowers/plans/2026-09-17-stage2-1-experimental-data-contract.md
```

Stage 2.1 must not modify:

``` text
pc/receiver/**
pc/clock_sync/**
pc/cursor_preview/**
android/**
```

The existing engineering subsystems must continue to pass their relevant
regression tests before the Stage 2.1 freeze tag is created.

------------------------------------------------------------------------

## 18. Stage 2.1 Final Exit Gate

Stage 2.1 may be declared complete only when all of the following are
true:

``` text
Design spec committed
Implementation plan committed
participant_data/ ignored by Git
Contract constants tested
CSV schemas tested
Manifest schema tested
Cross-file validator tested
Session SHA-256 generation tested
Session hash verification tested
CLI tested
Valid synthetic session PASS
Invalid synthetic session EXPECTED FAIL
Existing clock-sync tests PASS
Existing cursor-preview tests PASS
No real participant data collected
No P0 implementation added
No P2C implementation added
No L0 implementation added
No L2C implementation added
No Fitts outcome formula frozen
No final IMU resampling frequency frozen
Tracked worktree clean
Stage 2.1 decision document committed
Stage 2.1 tag points to final qualified commit
```

The Stage 2.1 freeze tag must only be created after every exit criterion
above has been verified.

------------------------------------------------------------------------

## 19. Intended Freeze Tag

The intended annotated Git tag is:

``` text
stage2.1-experimental-data-contract-v1.0
```

The tag message is:

``` text
Freeze Stage 2.1 experimental data contract v1.0
```

After creation, the following two commits must be identical:

``` text
git rev-parse HEAD
git rev-list -n 1 stage2.1-experimental-data-contract-v1.0
```

Only after the hashes match and all exit criteria are satisfied may
Stage 2.1 be declared formally complete and development proceed to the
next formal experiment-system work package.


    Setelah Anda paste dan save file tersebut, **jangan commit/tag dulu**. Lanjut dengan test dan source-boundary gate yang tadi sudah saya berikan. Kalau mau lebih praktis, setelah file sudah tersimpan cukup kirim output dari command berikut:

    ```powershell
    cd "D:\IMU_Cursor_Research"

    python -m pytest `
      ".\pc\experiment\tests" `
      -q

    python -m pytest `
      ".\pc\clock_sync\tests" `
      ".\pc\cursor_preview\tests" `
      ".\pc\experiment\tests" `
      -q

    python -m pytest `
      ".\pc\receiver\test_udp_receiver.py" `
      -q

    git check-ignore -v "participant_data/"

    git diff `
      "82d907bd8820c66708dfa6dfd17e43c663f52a7a..HEAD" `
      --name-status

    git status --short

    git diff --name-status

    git diff --cached --name-status

Setelah hasil itu Anda kirim, saya cek satu per satu sebelum kita
melakukan **freeze commit + tag final Stage 2.1**.
