# Stage 2.5 Common Time Grid and Preprocessing Implementation Plan

Version: 1.0

Date: 2026-09-19

Status: IMPLEMENTATION PLAN

Project: IMU Cursor Personalization

Branch:

`research/stage2.5-common-grid-preprocessing-v1.0`

Design specification:

`docs/superpowers/specs/2026-09-19-stage2-5-common-grid-preprocessing-design.md`

Design commit:

`e34565e`

Baseline freeze:

`stage2.3-2.4-guided-2c-clock-label-v1.0`

Baseline commit:

`1ecb251557a50f787698c1edb48441cc848fef70`

Baseline regression:

- clock-sync + experiment: 223 passed
- UDP receiver: 6 passed

---

# 1. Implementation Rule

Every production task follows:

`RED -> GREEN -> regression -> audit -> explicit commit`

For every task:

1. create the failing test first;
2. confirm that RED fails for the intended missing behavior;
3. implement only the behavior needed by the task;
4. run targeted tests;
5. run the full clock-sync + experiment regression;
6. run `git diff --check`;
7. inspect `git status --short`;
8. stage only the explicit task files;
9. commit with a task-specific message.

`git add .` is forbidden.

Synthetic and engineering qualification artifacts remain outside source
control under ignored evidence directories such as `bench_data/`.

No evaluation-participant outcome data may be used for Stage 2.5
configuration selection.

---

# 2. Work-Package Boundary

Stage 2.5 starts from the frozen Stage 2.3-2.4 contract.

It must preserve:

- mapped PC sensor timestamps;
- Stage 2.4 clock provenance;
- Stage 2.4 calibration identity;
- Stage 2.4 lag-sign convention;
- Stage 2.4 boundary-safe reference lookup;
- Stage 2.1 and Stage 2.3-2.4 schemas.

Stage 2.5 does not implement P0, P2C, L0, or L2C.

---

# 3. Task 1 - Freeze Stage 2.5 Artifact Schemas

Goal:

Create the Stage 2.5 preprocessing namespace and freeze ordered schemas
before generating preprocessing artifacts.

Production files:

`pc/experiment/preprocessing/__init__.py`

`pc/experiment/preprocessing/schema.py`

Test file:

`pc/experiment/tests/test_stage25_schemas.py`

Freeze constants for:

- common-grid CSV columns;
- preprocessing-config required fields;
- preprocessing-quality required fields;
- preprocessing-manifest required fields;
- sensor-family vocabulary;
- grid-row validity vocabulary;
- preprocessing build-status vocabulary;
- duplicate-event vocabulary;
- gap-event vocabulary.

The common-grid schema must preserve:

- participant identity;
- session identity;
- calibration identity;
- grid index;
- grid PC timestamp;
- accel x/y/z;
- gyro x/y/z;
- accel validity;
- gyro validity;
- combined sensor validity;
- active-motion flag;
- grid label PC timestamp;
- sequence/direction/phase where valid;
- reference position;
- reference velocity;
- label status;
- padding or provenance flag if required by frozen schema;
- derivation version.

Task 1 does not select final numeric preprocessing parameters.

Acceptance:

- exact ordered schemas tested;
- vocabulary tested;
- no existing frozen schema modified.

Suggested commit:

`feat(stage2.5): freeze preprocessing artifact schemas`

---

# 4. Task 2 - Source Stream Normalization and Validation

Goal:

Convert raw/mapped sensor rows into deterministic per-sensor native
streams before grid reconstruction.

Production file:

`pc/experiment/preprocessing/source_validation.py`

Test file:

`pc/experiment/tests/test_stage25_source_validation.py`

Required behavior:

- accelerometer and gyroscope are treated independently;
- `pc_mapped_ts_ns` is the only alignment time;
- `pc_receive_ts_ns` is never substituted;
- participant/session/calibration identity is checked;
- sensor family is validated;
- invalid mapped timestamps fail or flag according to contract;
- temporal reorder events are detected;
- source-order provenance is preserved;
- duplicate source identity is detected;
- duplicate mapped timestamp is detected;
- deterministic normalized ordering is produced.

The output must include diagnostics sufficient for later quality
reporting.

No duplicate may be silently discarded.

No reordered sample may be silently corrected without reporting it.

Suggested commit:

`feat(stage2.5): normalize timestamped sensor streams`

---

# 5. Task 3 - Deterministic Integer Common Grid

Goal:

Implement deterministic regular PC-time-grid construction independent of
sensor row index.

Production file:

`pc/experiment/preprocessing/grid.py`

Test file:

`pc/experiment/tests/test_stage25_grid.py`

Required behavior:

- grid timestamps use integer nanoseconds;
- grid interval is supplied by configuration;
- no repeated floating-point accumulation;
- timestamps are strictly increasing;
- identical inputs/configuration produce identical grid timestamps;
- grid origin rule is explicit;
- grid domain is explicit;
- no automatic extrapolation beyond configured valid coverage;
- accel and gyro native rows are not paired by sequence/index.

Candidate configuration may be used in tests.

Candidate values are not frozen participant-study values.

Suggested commit:

`feat(stage2.5): add deterministic common time grid`

---

# 6. Task 4 - Causal Resampling and Coverage Policy

Goal:

Resolve independently timestamped sensor families onto the common grid
without future look-ahead.

Production file:

`pc/experiment/preprocessing/resampling.py`

Test file:

`pc/experiment/tests/test_stage25_resampling.py`

Required behavior:

- accel resampled independently;
- gyro resampled independently;
- output pairing occurs only on the common grid;
- resampling uses mapped PC time;
- receive time is ignored;
- future samples cannot influence an earlier grid output;
- source-coverage state is explicit;
- bounded gaps follow configuration;
- gaps beyond the configured maximum are not silently bridged;
- start/end extrapolation is forbidden unless later explicitly frozen;
- a deliberate approximately 4 ms accel/gyro offset fixture is handled
  through timestamp alignment.

Candidate causal methods may initially be configuration-controlled.

Suggested commit:

`feat(stage2.5): add causal sensor resampling`

---

# 7. Task 5 - Duplicate, Reorder, and Gap Policy

Goal:

Freeze executable deterministic policy handling for problematic native
records.

Production may extend:

`pc/experiment/preprocessing/source_validation.py`

`pc/experiment/preprocessing/resampling.py`

Test file:

`pc/experiment/tests/test_stage25_stream_anomalies.py`

Qualification fixtures:

- reordered records;
- duplicate source identity;
- duplicate mapped timestamp;
- repeated timestamp;
- one missing sample;
- bounded missing burst;
- excessive gap.

The implementation must emit explicit diagnostics.

Policy behavior must not be inferred from whether the final matrix
contains NaN.

At this stage the policy mechanism is frozen; final threshold values may
remain candidate-controlled until candidate qualification.

Suggested commit:

`feat(stage2.5): enforce stream anomaly policies`

---

# 8. Task 6 - Portrait and Sign Transform

Goal:

Make device-native to research-coordinate transformation explicit and
fully testable.

Production file:

`pc/experiment/preprocessing/axis_transform.py`

Test file:

`pc/experiment/tests/test_stage25_axis_transform.py`

Required behavior:

- transform is configuration-driven;
- no implicit sign flips;
- each output axis explicitly identifies source axis and sign;
- accel and gyro transforms are explicit;
- basis-vector fixtures verify every mapping;
- deterministic output;
- transform configuration is serializable and hashable.

The participant-study transform values are frozen only after the
evidence-backed candidate decision.

Suggested commit:

`feat(stage2.5): add explicit sensor axis transform`

---

# 9. Task 7 - Bias Estimation and Correction

Goal:

Implement deterministic bias estimation and correction with explicit
eligibility rules.

Production file:

`pc/experiment/preprocessing/bias.py`

Test file:

`pc/experiment/tests/test_stage25_bias.py`

Required behavior:

- supported channels are explicit;
- bias estimator is configuration-driven;
- estimation interval/scope is explicit;
- invalid bias-estimation evidence fails according to policy;
- known additive synthetic bias can be recovered within tolerance;
- no reference-label or evaluation-performance outcome is required;
- identical data/configuration produce identical bias estimate;
- bias provenance is returned for quality/manifest use.

Candidate estimators may be compared during qualification.

Suggested commit:

`feat(stage2.5): add deterministic bias correction`

---

# 10. Task 8 - Causal Low-Pass Filtering

Goal:

Implement a real-time-equivalent low-pass filtering interface.

Production file:

`pc/experiment/preprocessing/filtering.py`

Test file:

`pc/experiment/tests/test_stage25_filtering.py`

Required behavior:

- strictly causal;
- zero-phase / forward-backward filtering forbidden;
- configuration explicitly records family/order/cutoff/grid frequency;
- deterministic initialization;
- deterministic reset;
- state cannot leak between unrelated boundaries;
- impulse fixture;
- step fixture;
- future perturbation fixture proving no future-sample influence;
- filter delay remains distinct from label lag.

Filter family and numeric cutoff remain candidate choices until
qualification evidence selects them.

Suggested commit:

`feat(stage2.5): add causal low-pass filtering`

---

# 11. Task 9 - Active-Motion State

Goal:

Implement deterministic causal active-motion classification.

Production file:

`pc/experiment/preprocessing/active_motion.py`

Test file:

`pc/experiment/tests/test_stage25_active_motion.py`

Required behavior:

- no evaluation outcome input;
- rule is configuration-driven;
- threshold boundary semantics explicit;
- fixtures immediately below, at, and above threshold;
- deterministic output;
- no future-sample dependence;
- active-motion provenance is available to the final configuration.

The final rule/threshold is selected during candidate qualification.

Suggested commit:

`feat(stage2.5): add active-motion state`

---

# 12. Task 10 - Common-Grid Reference Labels

Goal:

Attach Stage 2.4 reference supervision to common-grid timestamps without
changing the frozen lag contract.

Production file:

`pc/experiment/preprocessing/labels.py`

Test file:

`pc/experiment/tests/test_stage25_grid_labels.py`

Frozen formula:

`grid_label_pc_time_ns = grid_pc_time_ns - alignment_lag_ns`

Required behavior:

- reuse Stage 2.4 reference lookup;
- preserve exact lag sign;
- no reference extrapolation;
- no interpolation across sequence/direction/segment/phase boundaries;
- sensor validity and label validity remain distinct;
- invalid boundary labels do not automatically make sensor grid rows
  invalid;
- reference velocity remains the supervision target.

Suggested commit:

`feat(stage2.5): add common-grid reference labels`

---

# 13. Task 11 - Causal Sequence-Start Padding

Goal:

Implement reusable padding semantics without freezing learned-model
window length.

Production file:

`pc/experiment/preprocessing/padding.py`

Test file:

`pc/experiment/tests/test_stage25_padding.py`

Required behavior:

- deterministic sequence-start handling;
- configurable padding policy;
- optional/required padding mask according to frozen schema;
- no future sample copied backward;
- no crossing participant/session/calibration boundaries;
- no dependency on evaluation outcome;
- later model-family window length remains separate.

Suggested commit:

`feat(stage2.5): add causal sequence padding`

---

# 14. Task 12 - Preprocessing Quality Assessment

Goal:

Aggregate source/grid/label diagnostics into an auditable preprocessing
quality artifact.

Production file:

`pc/experiment/preprocessing/quality.py`

Test file:

`pc/experiment/tests/test_stage25_quality.py`

Required summary includes:

- accel source count;
- gyro source count;
- reorder count;
- duplicate count;
- invalid timestamp count;
- mapped coverage;
- maximum observed source gap;
- gap event count;
- grid-row count;
- invalid accel row count;
- invalid gyro row count;
- invalid combined sensor row count;
- valid supervision count;
- invalid supervision count;
- technical errors;
- build status.

Build statuses:

- `VALID`
- `TECHNICAL_INVALID`

Row invalidity remains separate from build invalidity.

Suggested commit:

`feat(stage2.5): add preprocessing quality assessment`

---

# 15. Task 13 - Preprocessing Configuration and Manifest

Goal:

Make the complete Stage 2.5 build reproducible and provenance-bound.

Production files:

`pc/experiment/preprocessing/config.py`

`pc/experiment/preprocessing/manifest.py`

Test files:

`pc/experiment/tests/test_stage25_config.py`

`pc/experiment/tests/test_stage25_manifest.py`

Required behavior:

- canonical deterministic serialization;
- SHA-256 validation;
- config hash;
- source artifact hashes;
- upstream Stage 2.4 provenance;
- common-grid hash;
- quality-artifact hash;
- identity consistency;
- derivation version;
- functional commit;
- candidate/final configuration role;
- deterministic manifest.

A manifest must reject inconsistent source/config hashes.

Suggested commit:

`feat(stage2.5): add preprocessing config and manifest`

---

# 16. Task 14 - Integrated Preprocessing Builder

Goal:

Compose Tasks 2-13 into one deterministic build interface.

Production file:

`pc/experiment/preprocessing/builder.py`

Test file:

`pc/experiment/tests/test_stage25_builder.py`

Conceptual pipeline:

`validated accel + gyro`

`-> mapped-time normalization`

`-> anomaly policy`

`-> common grid`

`-> causal resampling`

`-> axis transform`

`-> bias correction`

`-> causal filtering`

`-> active-motion state`

`-> Stage 2.4 reference labeling`

`-> quality assessment`

`-> common-grid artifact + config + quality + manifest`

Required behavior:

- same source/config produces same result;
- invalid upstream clock/provenance fails closed;
- mixed identity fails closed;
- no hidden condition-specific preprocessing path;
- no evaluation outcome required.

Suggested commit:

`feat(stage2.5): add integrated preprocessing builder`

---

# 17. Task 15 - Candidate Qualification Harness

Goal:

Evaluate still-unfrozen Stage 2.5 choices using synthetic and permitted
engineering evidence.

Production file:

`pc/experiment/preprocessing/candidate_qualification.py`

Test file:

`pc/experiment/tests/test_stage25_candidate_qualification.py`

Evidence must compare candidate alternatives for:

- grid interval/frequency;
- causal resampling;
- maximum source gap;
- duplicate policy;
- causal filter configuration;
- axis transform;
- bias correction;
- active-motion rule;
- padding policy.

Candidate qualification must record:

- candidate identifier;
- configuration;
- fixture/evidence set;
- pass/fail gates;
- timing/coverage diagnostics;
- causality result;
- reproducibility result;
- reason for acceptance/rejection.

No evaluation-participant outcome is permitted.

Output evidence belongs under ignored `bench_data/`.

Suggested commit:

`test(stage2.5): add preprocessing candidate qualification`

---

# 18. Task 16 - Candidate Selection Decision

Goal:

Select the final Stage 2.5 configuration before final synthetic
qualification.

Decision file:

`docs/decisions/stage2_5_preprocessing_candidate_selection_v1_0.md`

The decision must explicitly freeze the Stage 2.5-owned choices:

- grid interval/frequency;
- grid origin/domain rule;
- resampling method;
- gap threshold/policy;
- reorder policy;
- duplicate policy;
- filter family/order/cutoff/reset;
- axis/sign transform;
- bias estimator and interval;
- active-motion rule/threshold;
- sequence-start padding policy.

For each selected item, record:

- alternatives considered;
- evidence used;
- selected value/method;
- reason;
- configuration identifier.

If final numerical alignment lag remains owned by a later work package,
the decision must state this explicitly rather than silently assigning a
synthetic fixture value.

Suggested commit:

`docs(stage2.5): select preprocessing configuration`

---

# 19. Task 17 - Final Synthetic End-to-End Qualification

Goal:

Qualify the final selected Stage 2.5 preprocessing configuration.

Production file:

`pc/experiment/preprocessing/synthetic_qualification.py`

Test file:

`pc/experiment/tests/test_stage25_synthetic_e2e.py`

Qualification must include:

- regular streams;
- approximately 4 ms accel/gyro offset;
- timestamp jitter;
- reorder;
- duplicate;
- missing sample;
- bounded burst;
- excessive gap;
- basis-vector transform;
- known bias;
- filter impulse and step;
- future perturbation;
- active-motion boundaries;
- sequence-start padding;
- reference-label boundaries;
- deterministic rebuild.

Final qualification evidence must include:

- dataset role = synthetic;
- real participant data used = false;
- final configuration hash;
- common-grid hash;
- quality hash;
- manifest hash;
- reproducibility digest;
- all selected policy identifiers;
- functional commit.

Evidence directory:

`bench_data/stage2_5_preprocessing_qualification/`

Suggested commit:

`test(stage2.5): add preprocessing end-to-end qualification`

---

# 20. Task 18 - Final Regression and Freeze

Goal:

Freeze Stage 2.5 only after the final selected configuration is fully
qualified.

Required final gates:

- all Stage 2.5 targeted tests pass;
- all Stage 2.3-2.4 tests remain passing;
- clock-sync tests pass;
- experiment regression passes;
- receiver regression passes;
- synthetic E2E qualification status is VALID;
- real participant data used is false;
- config/manifest hashes are reproducible;
- candidate-selection decision is committed;
- worktree is clean except previously accepted untracked engineering
  evidence.

Final decision file:

`docs/decisions/stage2_5_common_grid_preprocessing_v1_0.md`

Proposed tag:

`stage2.5-common-grid-preprocessing-v1.0`

The freeze decision must separate:

- functional implementation commit;
- final configuration-selection commit;
- freeze/documentation commit;
- qualification evidence digest.

Branch and annotated tag must be pushed and remotely verified.

---

# 21. Planned Task Order

The execution order is mandatory unless a documented blocking issue
requires a versioned plan amendment.

Task 1:

Artifact schemas.

Task 2:

Source normalization and validation.

Task 3:

Integer common grid.

Task 4:

Causal resampling.

Task 5:

Stream anomaly policies.

Task 6:

Portrait/sign transform.

Task 7:

Bias correction.

Task 8:

Causal filtering.

Task 9:

Active motion.

Task 10:

Common-grid labels.

Task 11:

Causal padding.

Task 12:

Quality assessment.

Task 13:

Configuration and manifest.

Task 14:

Integrated builder.

Task 15:

Candidate qualification.

Task 16:

Candidate selection decision.

Task 17:

Final synthetic E2E qualification.

Task 18:

Final regression and freeze.

---

# 22. Numeric-Parameter Safety Rule

Synthetic unit-test values are fixtures only.

They must not silently become participant-study constants.

In particular, values appearing in tests for:

- grid frequency;
- filter cutoff;
- gap threshold;
- bias duration;
- active-motion threshold;
- padding value;
- alignment lag;

are not scientifically frozen unless Task 16 explicitly selects them.

This rule applies even if a candidate happens to pass every unit test.

---

# 23. Evaluation Contamination Rule

Stage 2.5 candidate selection may use:

- synthetic fixtures;
- engineering qualification evidence;
- development evidence;
- permitted pilot evidence.

It may not use evaluation-participant pointing outcomes to optimize the
preprocessing configuration.

Once Stage 2.5 is frozen, evaluation data may use that preprocessing
contract but may not retroactively change it.

---

# 24. Completion Definition

Stage 2.5 is complete only when one final preprocessing configuration is
fully provenance-bound and qualified, and the resulting common-grid
representation can be reproduced deterministically.

The output of Stage 2.5 becomes a frozen dependency for later:

- P0;
- P2C;
- L0;
- L2C.

No controller/model work package should duplicate or privately redefine
the Stage 2.5 timing, alignment, filtering, transform, gap, bias, or
padding semantics.