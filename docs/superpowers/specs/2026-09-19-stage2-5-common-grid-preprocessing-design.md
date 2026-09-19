# Stage 2.5 Common Time Grid and Preprocessing Design

Version: 1.0

Date: 2026-09-19

Status: DESIGN SPECIFICATION - IMPLEMENTATION NOT YET STARTED

Project: IMU Cursor Personalization

Branch:

`research/stage2.5-common-grid-preprocessing-v1.0`

Baseline freeze:

`stage2.3-2.4-guided-2c-clock-label-v1.0`

Baseline commit:

`1ecb251557a50f787698c1edb48441cc848fef70`

---

# 1. Purpose

This document defines the design for Stage 2.5 of the IMU Cursor
Personalization research system.

Stage 2.3-2.4 established:

- deterministic Guided 2C reference motion;
- auditable calibration provenance;
- smartphone-to-PC clock mapping;
- native-event reference labels;
- the frozen lag-sign convention;
- boundary-safe reference lookup.

Stage 2.5 now defines how asynchronous accelerometer and gyroscope
streams are converted into one deterministic, auditable, causal common
time representation suitable for later controller and learned-model
families.

The purpose is not merely to make arrays with equal lengths.

The purpose is to freeze one scientifically controlled preprocessing
contract so that P0, P2C, L0, and L2C are not compared using silently
different sensor preparation.

---

# 2. Baseline Guarantees Inherited from Stage 2.3-2.4

Stage 2.5 inherits the following frozen rules and must not redefine them:

- PC monotonic time is the experiment reference timebase.
- Native phone sensor time is mapped through the qualified clock model.
- `pc_receive_ts_ns` is not supervision time.
- Reference velocity is the supervised motion target.
- Positive lag follows:

  `label_pc_time_ns = pc_mapped_ts_ns - alignment_lag_ns`

- Reference lookup must not extrapolate beyond its valid domain.
- Reference lookup must not bridge sequence, direction, segment, phase,
  calibration, session, or participant boundaries.
- Invalid clock quality fails closed.
- Stage 2.1 schema v1.0 and Stage 2.3-2.4 frozen schemas must not be
  silently modified.

Stage 2.5 builds on those contracts.

It does not weaken them.

---

# 3. Engineering Motivation

Prior engineering characterization showed that the requested Android
sampling period is not sufficient to define the actual analysis grid.

Observed behavior included:

- native sensor rate around 125 Hz despite a 100 Hz application request;
- millisecond-scale callback timing variation;
- separate accelerometer and gyroscope timing;
- an observed accelerometer-gyroscope timestamp offset of approximately
  4 ms in one characterized run;
- missing, duplicate, and out-of-order network records in longer
  reliability characterization.

Therefore:

- accelerometer and gyroscope must not be paired solely by sequence ID;
- PC receive time must not be used for sensor alignment;
- array position must not be treated as time;
- the common grid must be constructed from mapped sensor timestamps;
- missing, duplicate, reordered, and delayed records require explicit
  deterministic policies.

---

# 4. Stage 2.5 Scope

Stage 2.5 covers:

1. preprocessing configuration and provenance;
2. source-stream validation;
3. timestamp ordering;
4. duplicate handling;
5. missing-sample and gap handling;
6. common PC-time-grid construction;
7. accelerometer resampling;
8. gyroscope resampling;
9. accelerometer-gyroscope alignment;
10. portrait/sign coordinate transformation;
11. bias correction;
12. causal low-pass filtering;
13. active-motion flag construction;
14. common-grid reference-label construction;
15. causal sequence-start padding semantics;
16. preprocessing quality flags;
17. deterministic preprocessing manifests;
18. synthetic and engineering-evidence qualification.

---

# 5. Explicit Non-Goals

Stage 2.5 does NOT implement or freeze:

- P0 controller coefficients;
- P0 dead-zone;
- P0 response curve;
- P0 cursor gain;
- P2C fitting;
- P2C regularization;
- L0 Conv1D architecture selection;
- L0 training;
- L2C latent adaptation;
- final learned-model temporal window length;
- Fitts pointing geometry;
- Fitts throughput analysis;
- evaluation-participant outcomes;
- statistical hypothesis testing.

Stage 2.5 creates the preprocessing substrate used by later system
families.

---

# 6. Separation Between Scientific Contract and Candidate Numbers

At design time, this document freezes semantics and qualification
requirements.

It does NOT yet declare the final values for:

- analysis-grid interval;
- analysis sampling frequency;
- interpolation/resampling method;
- maximum interpolation or hold gap;
- filter type beyond the causal requirement;
- filter order;
- filter cutoff;
- portrait transform coefficients;
- bias-estimation rule;
- active-motion threshold;
- sequence-start padding value.

Those values must be selected from Stage 2.5 qualification evidence.

They may not be chosen after evaluation-participant outcomes are seen.

Before Stage 2.5 is frozen, each required numeric or algorithmic choice
listed above must have an explicit final value or method in a versioned
configuration and freeze decision.

---

# 7. Input Timebase

Every sensor observation used by Stage 2.5 must have a mapped PC
timestamp derived from the qualified phone-to-PC clock mapping.

Conceptually:

`phone_sensor_ts_ns -> qualified clock mapping -> pc_mapped_ts_ns`

Common-grid construction must use:

`pc_mapped_ts_ns`

It must not use:

- PC receive timestamp;
- CSV row order as a substitute for time;
- global sequence number as a substitute for time;
- sensor-local sequence equality as evidence that accel and gyro occurred
  simultaneously.

---

# 8. Accelerometer and Gyroscope Are Independent Native Streams

Accelerometer and gyroscope streams must be treated as independent
timestamped streams before common-grid reconstruction.

A valid implementation may later expose a combined six-channel grid, but
the pairing must occur only after each source stream has been resolved
onto the common PC-time grid.

The following is forbidden:

`accel[i] paired with gyro[i] because their row or sensor sequence matches`

The required semantic path is:

`accel native timestamps -> mapped PC time -> common grid`

and independently:

`gyro native timestamps -> mapped PC time -> common grid`

Only then may the six channels occupy the same grid row.

---

# 9. Common Time Grid

Stage 2.5 introduces a regular PC-monotonic analysis grid.

Each grid row must have:

- deterministic grid index;
- exact integer PC timestamp;
- one fixed grid interval within a build;
- monotonic increasing grid time;
- explicit preprocessing configuration identity.

The implementation must use integer nanosecond arithmetic for grid
timestamps.

Floating-point accumulation must not be used to repeatedly advance grid
time.

The final grid interval remains a qualification decision until the Stage
2.5 freeze.

---

# 10. Grid Frequency and Native Sensor Rate

The common-grid frequency must not be assumed from the Android requested
sampling rate.

Observed native behavior must be considered.

The final grid choice must be justified using:

- measured source-rate behavior;
- timing jitter;
- accelerometer/gyroscope timing offset;
- missing-sample behavior;
- computational cost;
- causal preprocessing requirements;
- downstream controller/model compatibility.

A value such as 100 Hz is a candidate only until qualified and frozen.

Observed native behavior near 125 Hz does not automatically mean that
125 Hz is the final analysis frequency.

---

# 11. Grid Domain

The common grid must not require sensor extrapolation beyond available
valid source coverage.

The final grid domain must be the deterministic valid intersection
required by the channels used by the preprocessing bundle.

A grid point is not valid merely because one sensor has data near that
time.

For a six-channel accel-plus-gyro bundle, the build must verify coverage
for both sensor families according to the frozen resampling policy.

Any trimming at the start or end must be explicit and recorded.

---

# 12. Grid Origin

The grid-origin rule must be deterministic and configuration-controlled.

Possible implementations may anchor to:

- a defined session/calibration PC timestamp; or
- another explicitly recorded integer PC-time origin.

The final rule must be frozen before participant evaluation.

Two builds using identical source data and identical configuration must
produce identical grid timestamps.

---

# 13. Reordered Samples

Source records may arrive or be stored out of temporal order.

Reordering policy must distinguish transport/storage order from sensor
time.

A permitted implementation must:

1. preserve source provenance;
2. inspect mapped timestamps;
3. detect reordered records;
4. apply the frozen deterministic reorder policy;
5. report reorder counts in quality metadata.

Silent reordering without reporting is forbidden.

Reordered records are not automatically equivalent to missing records.

---

# 14. Duplicate Samples

Duplicate records require an explicit policy.

The implementation must distinguish at least:

- duplicated source row/record identity;
- duplicated native sensor timestamp;
- duplicated mapped PC timestamp.

No duplicate may be silently averaged, dropped, or selected without a
recorded rule.

The final duplicate-resolution policy remains to be selected during
Stage 2.5 qualification.

The selected policy must be deterministic.

---

# 15. Missing Samples and Gaps

Missing observations must not be hidden by unlimited interpolation.

Stage 2.5 must define and freeze:

- what constitutes a source gap;
- the maximum gap permitted for resampling;
- the behavior when that gap is exceeded;
- whether the affected grid row, region, or entire build becomes invalid.

The implementation must produce explicit gap-related quality metadata.

Long gaps must not be bridged merely to obtain a complete matrix.

---

# 16. Resampling Must Be Causally Realizable

The final preprocessing used for real-time cursor control must be causal.

At grid time `t`, the preprocessing state may not depend on sensor
observations from a future time greater than `t`.

Therefore, the selected Stage 2.5 resampling rule must be realizable
online without future look-ahead.

An offline preprocessing path that uses future samples while the online
controller does not would create a train/inference mismatch and is not
acceptable as the frozen common pipeline.

Candidate methods must be evaluated under this causal requirement.

---

# 17. No Reference-Label Leakage into Sensor Resampling

Reference velocity, target direction, Fitts outcome, or future cursor
performance must not influence how IMU measurements are resampled.

Sensor preprocessing is determined from:

- sensor observations;
- mapped timestamps;
- frozen preprocessing configuration;
- permitted non-evaluation calibration/bias information.

Supervised labels are attached only after sensor preprocessing semantics
have been determined.

---

# 18. Portrait and Sign Transform

Stage 2.5 must define a canonical portrait-coordinate sensor convention.

The final configuration must explicitly record the transform applied to
each relevant sensor axis.

No implicit sign inversion is permitted.

The transform must be:

- deterministic;
- versioned;
- identical across applicable experimental conditions;
- testable using synthetic axis fixtures.

Any difference between device-native axes and research-coordinate axes
must be represented as an explicit transform.

---

# 19. Bias Correction

Bias correction must be explicit and reproducible.

The method must define:

- which channels are corrected;
- the source interval used to estimate bias;
- eligibility rules for that interval;
- behavior when a valid bias interval is unavailable;
- whether bias is session-level or another frozen scope;
- the exact statistic or estimator used.

Bias estimation must not use evaluation outcomes.

Bias estimation must not use future evaluation-trial performance to tune
the correction.

The final bias method remains a qualification decision until Stage 2.5
freeze.

---

# 20. Gyroscope/Accelerometer Alignment

Gyroscope and accelerometer alignment occurs through the common PC-time
grid.

It does not occur by assuming equal callback timing.

The pipeline must tolerate a bounded timestamp offset between native
sensor families provided the frozen source-coverage and resampling rules
can resolve the grid causally.

The engineering fixture set must include a deliberate accel/gyro timing
offset.

---

# 21. Causal Low-Pass Filtering

Any final low-pass filter used in the common preprocessing pipeline must
be causal.

Zero-phase or forward-backward filtering is forbidden for the frozen
real-time preprocessing path.

In particular, an implementation equivalent to non-causal `filtfilt`
must not be used for the model/controller input pipeline.

The final filter configuration must record:

- filter family;
- order or state dimension;
- cutoff;
- assumed grid interval/frequency;
- initialization policy;
- reset policy;
- derivation version.

The filter must be tested for absence of future-sample influence.

---

# 22. Filter State Boundaries

Filter state must not silently leak across logically independent
recording boundaries.

The final reset policy must explicitly identify boundaries such as:

- session start;
- calibration sequence boundary if applicable;
- other frozen discontinuity boundaries.

A build must not carry filter state from an unrelated preceding session.

---

# 23. Active-Motion Flag

Stage 2.5 must produce or define a deterministic active-motion flag.

The rule must be:

- causal;
- versioned;
- based only on permitted sensor/preprocessing quantities;
- independent of evaluation outcome;
- reproducible from the preprocessing configuration.

The final threshold and exact decision rule remain qualification
decisions until freeze.

The active-motion flag may later be used for training masks or
controller logic only as explicitly allowed by later system-family
specifications.

---

# 24. Common-Grid Reference Labels

Stage 2.4 native labels are an intermediate auditable artifact.

Stage 2.5 common-grid supervision must preserve the frozen Stage 2.4 lag
semantics.

For common-grid timestamp:

`grid_pc_time_ns`

the corresponding label query time is:

`grid_label_pc_time_ns = grid_pc_time_ns - alignment_lag_ns`

Reference state must be resolved using the already qualified
boundary-safe reference lookup semantics.

The pipeline must not redefine the lag sign.

The final numerical lag remains configuration-controlled unless a later
explicit freeze decision selects it.

---

# 25. Do Not Interpolate Invalid Reference Boundaries

Common-grid label construction must preserve Stage 2.4 reference
boundary rules.

A common-grid point must not obtain a label by bridging:

- different calibration IDs;
- different sequence IDs;
- different segment indices;
- different directions;
- different phases.

No reference extrapolation is allowed.

A sensor grid row and its label validity are separate concepts.

A valid sensor row may have an invalid supervision label near a
reference boundary.

---

# 26. Sequence-Start Window Padding

Stage 2.5 must freeze the semantics of causal padding at the start of a
temporal sequence.

The design distinguishes:

- padding policy;
- model-family window length.

Stage 2.5 freezes the padding policy.

Later learned-model stages may freeze their actual window length.

Padding must never copy or inspect future observations in a way that
leaks future information into an earlier model position.

The final padding value/method remains to be selected during Stage 2.5
qualification.

Padding provenance must remain visible through a mask or equivalent
metadata if required by the final design.

---

# 27. System-Family Preprocessing Invariance

All experimental conditions must use the same Stage 2.5 preprocessing
contract wherever scientifically compatible.

Differences required by system-family definitions must be explicit.

For example:

- a parametric family may consume a defined rotational feature subset;
- a learned temporal family may consume the common six-channel
  accelerometer-plus-gyroscope sequence.

Such feature selection is a system-family bundle decision.

It must not result in different hidden timestamp mapping, filtering,
axis transform, gap handling, or quality rules between experimental
conditions.

---

# 28. Evaluation Data Must Not Tune Preprocessing

Stage 2.5 preprocessing choices must be selected using permitted
development, engineering, synthetic, and pilot evidence.

Evaluation-participant outcome data must not be used to choose:

- grid rate;
- interpolation method;
- filter cutoff;
- bias correction;
- active-motion threshold;
- padding strategy;
- duplicate policy;
- gap threshold.

If later evidence requires a change, a new versioned decision and
requalification are required.

---

# 29. Proposed Artifact Namespace

Stage 2.5 introduces a dedicated preprocessing namespace.

Proposed configuration artifact:

`artifacts/preprocessing/preprocessing_config.json`

Proposed derived common-grid artifact:

`derived/preprocessing/common_grid.csv`

Proposed quality artifact:

`derived/preprocessing/preprocessing_quality.json`

Proposed build manifest:

`derived/preprocessing/preprocessing_manifest.json`

These paths are design-level contracts for this work package unless an
implementation-plan review identifies a concrete repository conflict
before production code begins.

---

# 30. Preprocessing Configuration

`preprocessing_config.json` must record enough information to reproduce
the build.

It must include, at minimum, semantic fields for:

- schema version;
- configuration role;
- common-grid interval/frequency;
- grid-origin rule;
- grid-domain rule;
- sensor timestamp field;
- reorder policy;
- duplicate policy;
- missing/gap policy;
- maximum permitted source gap;
- accelerometer resampling method;
- gyroscope resampling method;
- portrait/sign transform;
- bias-correction method and parameters;
- low-pass filter configuration;
- filter reset policy;
- active-motion rule and threshold;
- sequence-start padding policy;
- label lag convention;
- source artifact paths;
- source artifact hashes;
- derivation version;
- functional commit.

Synthetic values must be clearly identified as synthetic.

Presence in a config file does not automatically make a candidate value
scientifically frozen.

---

# 31. Common-Grid Artifact

`common_grid.csv` is the auditable regular-time representation used as
the preprocessing substrate for later system families.

At design level it must contain sufficient information to trace every
grid row to:

- participant/session/calibration identity;
- grid index;
- PC grid timestamp;
- preprocessed accelerometer state;
- preprocessed gyroscope state;
- active-motion state;
- sensor validity/coverage state;
- supervision validity where applicable;
- derivation version.

The exact ordered schema is an implementation-plan Task 1 concern and
must be frozen before production rows are generated.

---

# 32. Preprocessing Quality Artifact

The quality artifact must summarize, at minimum:

- source row counts by sensor family;
- reordered count;
- duplicate count;
- invalid timestamp count;
- mapped-time coverage;
- missing/gap events;
- maximum observed source gap;
- grid-row count;
- invalid sensor-grid-row count;
- valid supervision row count;
- invalid supervision row count;
- preprocessing status;
- technical-invalid reasons.

Quality reporting must not silently convert technical failures into
usable data.

---

# 33. Preprocessing Manifest

The preprocessing manifest must bind together:

- source artifact hashes;
- Stage 2.4 label/reference provenance;
- preprocessing configuration hash;
- common-grid artifact hash;
- quality artifact hash;
- participant/session/calibration identity;
- build status;
- derivation version;
- functional commit.

The manifest must make two identical builds auditable and comparable.

---

# 34. Build Status

Minimum build-level status vocabulary:

`VALID`

`TECHNICAL_INVALID`

Stage 2.5 must fail closed for conditions such as:

- missing required source artifact;
- invalid clock mapping provenance;
- incompatible participant/session/calibration identity;
- non-reconstructable common grid;
- missing required sensor family;
- source coverage insufficient under frozen rules;
- gap policy violation requiring build rejection;
- invalid preprocessing configuration;
- non-deterministic configuration/provenance mismatch.

Row-level invalidity and build-level invalidity must remain distinct.

---

# 35. Determinism Requirement

Given identical:

- source artifacts;
- source hashes;
- preprocessing configuration;
- upstream frozen artifacts;
- functional code commit;

the preprocessing build must produce identical:

- common-grid timestamps;
- grid values within the frozen numeric serialization contract;
- quality summary;
- artifact hashes;
- manifest;
- reproducibility digest.

Random preprocessing behavior is forbidden unless an explicitly seeded
and scientifically justified operation is later introduced.

No such random operation is currently planned.

---

# 36. Qualification Strategy

Stage 2.5 must not be frozen from unit tests alone.

Qualification must include synthetic fixtures that separately exercise:

1. perfectly regular accel and gyro streams;
2. unequal accel/gyro native timestamps;
3. approximately 4 ms sensor-family offset;
4. timestamp jitter;
5. one missing source sample;
6. a bounded missing burst;
7. a gap beyond the permitted threshold;
8. reordered records;
9. duplicate records;
10. repeated timestamp;
11. invalid source timestamp;
12. start-of-stream boundary;
13. end-of-stream boundary;
14. portrait-axis sign fixture;
15. known sensor bias fixture;
16. filter impulse/step fixture;
17. active-motion threshold fixture;
18. causal padding fixture;
19. reference-label boundary fixture;
20. deterministic rebuild fixture.

Qualification must also include permitted replay of existing engineering
evidence where useful.

No real evaluation-participant outcome may be required to qualify the
software contract.

---

# 37. Causality Qualification

A dedicated test must demonstrate that changing an observation at future
time:

`t_future > t`

cannot change the frozen preprocessed output at grid time `t`.

This requirement applies to:

- resampling;
- filter output;
- active-motion state;
- padding behavior.

A failure indicates future leakage and is disqualifying.

---

# 38. Timestamp-Alignment Qualification

A synthetic fixture must create accelerometer and gyroscope samples with
different native timestamps.

The test must demonstrate that the resulting common-grid pairing follows
mapped timestamps rather than:

- row index;
- sensor sequence equality;
- receive timestamp.

The fixture must be capable of detecting an implementation that
incorrectly pairs samples by array position.

---

# 39. Missing and Reordered Qualification

Synthetic fixtures must verify the frozen policies for:

- in-order complete data;
- out-of-order source records;
- missing source observations;
- duplicate observations;
- excessive gaps.

Expected behavior must be explicit.

No test may pass merely because the final matrix has no NaN values.

---

# 40. Filtering Qualification

Filtering tests must demonstrate:

- causality;
- deterministic initialization;
- deterministic reset;
- stable output;
- correct configuration binding;
- no use of future observations.

The implementation must distinguish filtering delay from clock mapping
or label lag.

Filter delay must not be silently compensated by altering the frozen
Stage 2.4 lag-sign convention.

---

# 41. Bias Qualification

Synthetic bias fixtures must include a known additive bias.

The selected correction method must recover the expected correction
within a documented numerical tolerance.

A bias method that depends on evaluation labels is forbidden.

Failure to obtain a valid bias estimate must follow a frozen explicit
policy.

---

# 42. Portrait Transform Qualification

Synthetic basis-vector fixtures must verify every axis/sign mapping.

For each canonical input basis vector, the expected transformed output
must be known exactly.

This prevents accidental sign flips or swapped axes from remaining
undetected.

---

# 43. Active-Motion Qualification

The qualification suite must include sensor magnitudes or equivalent
features immediately below, at, and above the final active-motion
threshold.

Boundary semantics must be explicit.

The same input and configuration must always yield the same flag.

---

# 44. Window-Padding Qualification

Padding tests must prove:

- sequence-start behavior is deterministic;
- padded positions are distinguishable if the design requires a mask;
- no future sample is copied backward;
- padding does not cross participant/session/calibration boundaries.

Stage 2.5 does not need to freeze the final L0/L2C window length to freeze
these padding semantics.

---

# 45. Candidate Selection Before Freeze

Before the Stage 2.5 freeze decision, the project must produce an
evidence table for every still-open required choice.

At minimum:

- final grid interval/frequency;
- resampling method;
- maximum source gap;
- duplicate policy;
- causal low-pass filter and cutoff;
- portrait/sign transform;
- bias-correction method;
- accel/gyro common-grid alignment rule;
- active-motion rule and threshold;
- sequence-start padding policy.

Each selected value or method must include:

- candidate alternatives considered;
- evidence used;
- reason for selection;
- qualification result;
- configuration identifier.

The evaluation dataset must not participate in this selection.

---

# 46. Proposed Module Structure

The implementation plan may use a structure equivalent to:

`pc/experiment/preprocessing/__init__.py`

`pc/experiment/preprocessing/schema.py`

`pc/experiment/preprocessing/source_validation.py`

`pc/experiment/preprocessing/grid.py`

`pc/experiment/preprocessing/resampling.py`

`pc/experiment/preprocessing/axis_transform.py`

`pc/experiment/preprocessing/bias.py`

`pc/experiment/preprocessing/filtering.py`

`pc/experiment/preprocessing/active_motion.py`

`pc/experiment/preprocessing/labels.py`

`pc/experiment/preprocessing/padding.py`

`pc/experiment/preprocessing/quality.py`

`pc/experiment/preprocessing/manifest.py`

`pc/experiment/preprocessing/synthetic_qualification.py`

Exact file decomposition may change during implementation planning if the
scientific responsibilities remain equivalent.

Module layout must not silently change the contracts in this design.

---

# 47. Test-Driven Implementation Rule

Every implementation task must follow:

`RED -> GREEN -> regression -> audit -> explicit commit`

New production behavior must first have a failing test demonstrating the
missing contract.

A test is not considered RED merely because of an unrelated syntax or
environment failure.

After GREEN:

- targeted tests must pass;
- all existing experiment tests must pass;
- clock-sync regression must pass;
- receiver regression must remain qualified at freeze;
- Git diff must be audited;
- only explicit task files may be staged.

`git add .` must not be used.

---

# 48. Existing Evidence Boundary

Existing engineering evidence remains evidence.

It must not be silently committed into source control.

Existing ignored participant or bench-data policies remain in force.

Synthetic qualification output should continue to use an ignored
engineering-evidence area such as:

`bench_data/`

No participant-study file is required for Stage 2.5 software
qualification.

---

# 49. What This Design Freezes Now

This design freezes the following Stage 2.5 principles:

- common-grid alignment is timestamp-based;
- mapped PC sensor time is the timing source;
- receive time is not alignment time;
- accel and gyro are independently timestamped streams;
- common-grid processing must be causally realizable;
- no future-sample leakage is permitted;
- no unlimited interpolation across gaps is permitted;
- missing/reordered/duplicate handling must be explicit;
- portrait/sign transform must be explicit and versioned;
- bias correction must be explicit and versioned;
- low-pass filtering must be causal;
- accel/gyro alignment occurs on the common time grid;
- active-motion behavior must be deterministic;
- sequence-start padding must be causal;
- Stage 2.4 lag-sign semantics are preserved;
- preprocessing must be shared across experimental conditions wherever
  scientifically compatible;
- evaluation outcomes must not tune preprocessing;
- all final numeric/method choices require qualification evidence.

---

# 50. Explicitly Unfrozen at Design-Start

The following remain deliberately UNFROZEN at the moment this design
specification is committed:

- final common-grid interval;
- final common-grid frequency;
- final grid origin;
- final resampling method;
- final maximum source gap;
- final reorder policy details;
- final duplicate-resolution policy;
- final causal filter family;
- final filter order;
- final filter cutoff;
- final filter initialization/reset constants;
- final portrait/sign transform values;
- final bias-correction estimator;
- final bias-estimation interval;
- final active-motion rule;
- final active-motion threshold;
- final sequence-start padding value/method;
- final numerical alignment lag;
- final learned-model window length.

This is intentional.

The Stage 2.5 work package is responsible for qualifying and freezing the
Stage 2.5 items before its exit gate.

The final numerical alignment lag and learned-model window length may
remain owned by their later explicit research decisions if the Stage 2.5
freeze documents that boundary clearly.

---

# 51. Required Freeze Evidence

Before Stage 2.5 can be declared complete, evidence must demonstrate:

- design specification committed;
- implementation plan committed;
- common-grid schema frozen;
- preprocessing configuration schema frozen;
- preprocessing manifest schema frozen;
- PC-mapped timestamp used;
- receive timestamp rejected for alignment;
- accel/gyro independent timing handled;
- timestamp-offset synthetic fixture passed;
- missing-sample fixture passed;
- reordered-sample fixture passed;
- duplicate fixture passed;
- excessive-gap fixture passed;
- portrait/sign fixture passed;
- known-bias fixture passed;
- causal-filter fixture passed;
- no-future-leakage fixture passed;
- active-motion fixture passed;
- sequence-padding fixture passed;
- common-grid label semantics passed;
- deterministic rebuild passed;
- selected grid configuration justified;
- selected resampling method justified;
- selected gap policy justified;
- selected filter configuration justified;
- selected axis transform justified;
- selected bias method justified;
- selected active-motion rule justified;
- selected padding policy justified;
- synthetic end-to-end qualification passed;
- existing Stage 2.3-2.4 tests passed;
- existing clock-sync tests passed;
- receiver regression passed;
- no evaluation outcome used for tuning;
- no real evaluation-participant data required for qualification;
- ignored engineering evidence remains untracked;
- worktree audited;
- decision record committed;
- freeze tag points to the final qualified commit.

---

# 52. Exit Gate

Stage 2.5 is complete only when the preprocessing contract can be
reconstructed from versioned source artifacts and produces deterministic
common-grid data under the final frozen configuration.

At exit:

- the analysis time grid is no longer ambiguous;
- accel and gyro alignment is no longer ambiguous;
- resampling behavior is no longer ambiguous;
- missing/reordered/duplicate behavior is no longer ambiguous;
- causal filtering is no longer ambiguous;
- portrait/sign handling is no longer ambiguous;
- bias correction is no longer ambiguous;
- active-motion semantics are no longer ambiguous;
- sequence-start padding semantics are no longer ambiguous.

Only after this gate passes may implementation of P0/P2C and L0/L2C rely
on Stage 2.5 preprocessing as a frozen shared substrate.

---

# 53. Design Summary

The Stage 2.5 processing concept is:

`native accel stream`

`+`

`native gyro stream`

`+`

`qualified phone-to-PC timing`

`+`

`frozen preprocessing configuration`

`->`

`source validation and explicit reorder/duplicate/gap policy`

`->`

`independent timestamp-based causal resampling`

`->`

`regular PC common time grid`

`->`

`explicit portrait/sign transform`

`->`

`bias correction`

`->`

`causal low-pass filtering`

`->`

`active-motion state`

`+`

`Stage 2.4 lag/reference-label semantics`

`->`

`auditable common-grid preprocessing artifact`

`->`

`later P0/P2C/L0/L2C system-family bundles`

The common preprocessing substrate is intentionally frozen before the
controllers and learned models are implemented.