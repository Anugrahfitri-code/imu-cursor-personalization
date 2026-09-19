# Stage 2.5 Preprocessing Candidate Selection Decision v1.0

## 1. Decision Identity

Stage: 2.5

Decision version: 1.0

Status: FINAL PREPROCESSING CONFIGURATION SELECTED, PENDING TASK 17 FINAL SYNTHETIC QUALIFICATION

Branch:

`research/stage2.5-common-grid-preprocessing-v1.0`

Final configuration identifier:

`stage2.5-preprocessing-final-v1.0`

Selection basis repository state before this decision:

`d9942cc`

Functional expanded qualification implementation:

`071eded`

Qualification evidence:

`bench_data/stage2_5_preprocessing_candidate_qualification/qualification_v2/qualification_report.json`

Qualification evidence SHA-256:

`D8E8FA9DC0A2B73765520E9B35CB8BE0B086D8636D54A2CF6500AA89E85DD5A4`

Dataset role:

`synthetic`

Real participant data used:

`false`

No evaluation-participant outcome was used to select this configuration.

---

## 2. Decision Scope

This decision freezes the Stage 2.5-owned preprocessing choices required before Task 17 final synthetic end-to-end qualification.

The selection criteria are:

1. preserve strict causality;
2. preserve usable temporal coverage;
3. preserve information unless a qualified transformation is necessary;
4. minimize unnecessary synthetic or artificial signal modification;
5. preserve deterministic and provenance-bound behavior;
6. avoid dependence on condition identity or evaluation outcome;
7. prefer simpler qualified behavior when alternatives are technically equivalent.

Qualification acceptance means an alternative was technically admissible.

It does not mean every accepted alternative is equally suitable as the final shared preprocessing contract.

Task 16 therefore applies the documented selection criteria to the accepted alternatives.

---

## 3. Final Configuration Summary

The selected Stage 2.5 configuration is:

```text
configuration_id = stage2.5-preprocessing-final-v1.0
configuration_role = FINAL

grid_interval_ns = 10000000
grid_frequency_hz = 100.0
grid_origin_rule = ALIGN_TO_ORIGIN
grid_domain_rule = INTERSECTION

sensor_timestamp_field = pc_mapped_ts_ns

reorder_policy = SORT_AND_REPORT
duplicate_policy = KEEP_FIRST

gap_policy = EXPLICIT_STATUS
max_source_gap_ns = 20000000

accel_resampling_method = PREVIOUS_SAMPLE_HOLD
gyro_resampling_method = PREVIOUS_SAMPLE_HOLD

axis_transform.ACCEL = identity x/y/z, sign +1
axis_transform.GYRO = identity x/y/z, sign +1

bias_correction.method = MEAN_PC_WINDOW
bias_correction.channels = x,y,z
bias_correction.minimum_samples = 2
bias interval = explicit per-session stationary pre-motion PC-time window

low_pass_filter.family = ONE_POLE_IIR
low_pass_filter.order = 1
low_pass_filter.cutoff_hz = 10.0
low_pass_filter.grid_frequency_hz = 100.0
low_pass_filter.initialization = FIRST_SAMPLE
low_pass_filter.reset_policy = EXPLICIT_BOUNDARIES
filter_reset_policy = EXPLICIT_BOUNDARIES

active_motion.source_family = GYRO
active_motion.method = L2_NORM_THRESHOLD
active_motion.channels = x,y
active_motion.threshold = 0.1
active_motion.comparison = GREATER_EQUAL

padding_policy.method = REPEAT_FIRST
padding_policy.padding_value = 0.0
```

For `REPEAT_FIRST`, `padding_value = 0.0` remains present only because the frozen configuration schema records the field. The value is not used by the selected padding method.

---

## 4. Common Grid Selection

Alternatives considered:

- 100 Hz / 10 ms;
- 50 Hz / 20 ms.

Qualification evidence showed both alternatives could produce deterministic integer-nanosecond grids without extrapolation.

The 100 Hz fixture retained three common-grid timestamps over the tested intersection, whereas the 50 Hz fixture retained one.

Selected:

```text
grid_interval_ns = 10000000
grid_frequency_hz = 100.0
```

Reason:

The 100 Hz alternative preserves greater temporal resolution while remaining deterministic and within the valid intersection domain.

This is now an explicit Task 16 selection and is no longer merely a synthetic unit-test constant.

---

## 5. Grid Origin and Domain

Selected:

```text
grid_origin_rule = ALIGN_TO_ORIGIN
grid_domain_rule = INTERSECTION
```

Reason:

The qualified common-grid implementation uses an integer origin-aligned lattice and restricts output to the overlap of valid accelerometer and gyroscope coverage.

`INTERSECTION` prevents grid extrapolation outside shared sensor support.

These policies are structural engineering constraints rather than evaluation-tuned hyperparameters.

---

## 6. Timing Source

Selected:

```text
sensor_timestamp_field = pc_mapped_ts_ns
```

This inherits the qualified Stage 2.3-2.4 timing contract.

`pc_receive_ts_ns`, source row number, and sensor sequence number must not replace mapped PC sensor time as the preprocessing time coordinate.

---

## 7. Causal Resampling Selection

Alternatives considered:

- `PREVIOUS_SAMPLE_HOLD`;
- `EXACT_ONLY_COMPARISON`.

The synthetic offset fixture used a source sample at 100 ms and a common-grid timestamp at 104 ms.

`PREVIOUS_SAMPLE_HOLD` retained a causal source sample with a 4 ms source age.

`EXACT_ONLY_COMPARISON` remained causal but produced no sample at the offset grid timestamp.

Selected for both sensor families:

```text
accel_resampling_method = PREVIOUS_SAMPLE_HOLD
gyro_resampling_method = PREVIOUS_SAMPLE_HOLD
```

Reason:

It preserves asynchronous sensor coverage while using only information available at or before the common-grid timestamp.

No future sample may influence a current grid row.

---

## 8. Source-Gap Selection

Alternatives considered:

- maximum source gap = 5 ms;
- maximum source gap = 20 ms.

Both alternatives passed the technical build gates.

In the qualification fixture:

```text
20 ms candidate:
invalid_sensor_row_count = 0
valid_supervision_count = 3

5 ms candidate:
invalid_sensor_row_count = 3
valid_supervision_count = 3
```

Selected:

```text
gap_policy = EXPLICIT_STATUS
max_source_gap_ns = 20000000
```

Reason:

The 5 ms threshold rejects ordinary asynchronous coverage in the approximately 4 ms offset fixture once source age is evaluated on the common grid.

The 20 ms threshold preserves the qualified grid rows while remaining bounded and explicit.

It also corresponds to at most a short bounded hold relative to the selected 10 ms grid interval rather than unlimited interpolation.

---

## 9. Reorder Policy

Selected:

```text
reorder_policy = SORT_AND_REPORT
```

Reason:

Mapped-PC timestamp order is the processing order.

Out-of-order input is deterministically sorted and retained as explicit diagnostic evidence rather than silently accepted or interpreted using source-file order.

---

## 10. Duplicate Policy

Alternatives considered:

- `KEEP_FIRST`;
- `KEEP_ALL_REPORT`.

Both were technically deterministic.

Selected:

```text
duplicate_policy = KEEP_FIRST
```

Reason:

`KEEP_FIRST` preserves one deterministic observation for a duplicate timestamp and avoids giving repeated timestamp observations additional influence in later causal processing.

Duplicate events remain explicitly reported in diagnostics.

---

## 11. Causal Filter Selection

Alternatives considered:

- first-order one-pole IIR, 5 Hz cutoff;
- first-order one-pole IIR, 10 Hz cutoff.

Both alternatives passed causality qualification and had no future-sample dependency.

Selected:

```text
family = ONE_POLE_IIR
order = 1
cutoff_hz = 10.0
grid_frequency_hz = 100.0
initialization = FIRST_SAMPLE
reset_policy = EXPLICIT_BOUNDARIES
```

Reason:

Both candidates are causal, but 10 Hz is the less aggressive smoothing option.

It preserves more motion bandwidth and has a faster causal response than the qualified 5 Hz alternative while still providing low-pass filtering.

This selection intentionally prioritizes information preservation and lower filtering delay before later controller/model work packages.

Zero-phase or forward-backward filtering remains forbidden.

Filter delay remains distinct from supervision alignment lag.

---

## 12. Axis and Sign Transform Selection

Alternatives considered by the synthetic basis-vector evidence included:

- identity x/y/z;
- explicit x-axis inversion.

Both alternatives were mechanically valid and deterministic.

Selected for both ACCEL and GYRO:

```text
x <- +x
y <- +y
z <- +z
```

Reason:

No qualification evidence requires an axis inversion.

The identity transform therefore introduces the fewest unsupported assumptions and preserves the native portrait-oriented sensor representation.

The selection does not claim that smartphone axes are identical to PC cursor axes.

Later controller/model work packages must consume this frozen feature representation rather than privately applying an undocumented alternative Stage 2.5 transform.

---

## 13. Bias Estimation and Interval Selection

The qualified estimator is:

```text
method = MEAN_PC_WINDOW
channels = x,y,z
minimum_samples = 2
```

Synthetic known-bias evidence demonstrated exact recovery of a constant bias for multiple eligible sample counts.

Selected interval rule:

```text
Use the explicit stationary pre-motion bias interval for the
current calibration/session in mapped PC time.

window_start_pc_ns =
resolved first boundary of that designated stationary interval

window_end_pc_ns =
resolved final boundary of that designated stationary interval
```

The absolute PC timestamps are intentionally not global constants.

They are session-specific provenance values and must be resolved from the actual calibration source interval.

The synthetic values such as 100 ms and 114 ms are not participant-study timestamps and are not frozen by this decision.

Reason:

Using the full designated stationary interval gives the mean estimator the available stationary evidence while preserving an explicit and reproducible PC-time boundary.

A build must fail rather than silently estimate bias when the configured minimum eligible sample requirement is not met.

---

## 14. Active-Motion Selection

Alternatives considered:

- L2 threshold = 0.1;
- L2 threshold = 0.5.

Both rules were deterministic and current-sample-only.

The synthetic magnitudes 0.0, 0.2, and 1.0 produced:

```text
threshold 0.1:
active = 2
inactive = 1

threshold 0.5:
active = 1
inactive = 2
```

Selected:

```text
source family = GYRO
method = L2_NORM_THRESHOLD
channels = x,y
threshold = 0.1
comparison = GREATER_EQUAL
```

Reason:

The selected lower threshold preserves sensitivity to the qualified intermediate-motion case rather than classifying it as inactive.

The Stage 2.5 active-motion state is an explicit preprocessing annotation and does not itself convert an otherwise valid common-grid sensor row into an invalid row.

Evaluation outcomes must not be used later to retune this threshold.

---

## 15. Sequence-Start Padding Selection

Alternatives considered:

- `REPEAT_FIRST`;
- `CONSTANT` with zero padding.

Both alternatives were causal and deterministic.

Selected:

```text
padding_policy.method = REPEAT_FIRST
```

Reason:

`REPEAT_FIRST` avoids introducing an artificial zero vector at the beginning of a sequence while requiring no future samples.

It therefore preserves causal initialization with less synthetic discontinuity than constant-zero padding.

The final downstream model window length remains a later model-family decision unless separately frozen.

---

## 16. Label-Lag Boundary

The Stage 2.4 sign convention remains frozen:

```text
grid_label_pc_time_ns =
grid_pc_time_ns - alignment_lag_ns
```

Task 16 does not silently freeze a synthetic numerical lag.

The final numerical `alignment_lag_ns` remains owned by the appropriate later alignment/model qualification work package.

For synthetic Stage 2.5 software qualification, an explicitly marked synthetic fixture value may be supplied, including zero where required by the fixture.

Such a value must not be represented as the final participant-study lag.

---

## 17. Condition Neutrality

This final Stage 2.5 preprocessing contract is shared across:

```text
P0
P2C
L0
L2C
```

where scientifically compatible.

No preprocessing parameter may be changed solely because the downstream condition identifier differs.

In particular:

```text
condition_id
evaluation_score
Fitts outcome
participant evaluation performance
```

must not select a different preprocessing path.

P2C and L2C must continue to use the same Stage 2.3-2.4 calibration source bundle and source slice when required by the frozen upstream contract.

---

## 18. Qualification Evidence Used

Task 15 expanded qualification produced evidence for all nine required candidate dimensions:

```text
grid_interval_frequency
causal_resampling
maximum_source_gap
duplicate_policy
causal_filter_configuration
axis_transform
bias_correction
active_motion_rule
padding_policy
```

Each dimension contained at least two explicit alternatives.

Qualification evidence passed the readiness audit:

```text
DIGEST_MATCH = TRUE
DIMENSIONS_COMPLETE = TRUE
ALTERNATIVES_COMPLETE = TRUE
QUALIFICATION_STATUSES_EXPLICIT = TRUE
REAL_PARTICIPANT_DATA_USED = FALSE
TASK16_SELECTION_READY = TRUE
```

Task 15 expanded regression:

```text
512 passed
```

---

## 19. What This Decision Freezes

Task 16 freezes:

```text
100 Hz / 10 ms common grid
ALIGN_TO_ORIGIN
INTERSECTION common domain
pc_mapped_ts_ns timing basis
SORT_AND_REPORT reorder policy
KEEP_FIRST duplicate policy
EXPLICIT_STATUS gap policy
20 ms maximum source age
PREVIOUS_SAMPLE_HOLD for ACCEL
PREVIOUS_SAMPLE_HOLD for GYRO
identity ACCEL axis/sign transform
identity GYRO axis/sign transform
MEAN_PC_WINDOW bias estimator
x/y/z bias channels
minimum two eligible bias samples
explicit stationary pre-motion bias-window rule
ONE_POLE_IIR
filter order 1
10 Hz cutoff
FIRST_SAMPLE initialization
EXPLICIT_BOUNDARIES filter reset
GYRO x/y L2 active-motion rule
active-motion threshold 0.1
GREATER_EQUAL threshold semantics
REPEAT_FIRST sequence-start padding
configuration identifier stage2.5-preprocessing-final-v1.0
```

---

## 20. Explicitly Not Frozen Here

This decision does not freeze:

```text
final numerical alignment_lag_ns
P0 controller gain or mapping
P2C solver or regularization
L0 architecture or model hyperparameters
L2C adaptation settings
final downstream model window length
Fitts task geometry
Fitts-law outcome implementation
participant evaluation outcomes
```

No later work package may silently redefine a Stage 2.5-owned preprocessing choice frozen above.

A required change must use an explicit versioned decision and requalification.

---

## 21. Task 16 Decision

The Stage 2.5 preprocessing configuration:

`stage2.5-preprocessing-final-v1.0`

is selected for Task 17 final synthetic end-to-end qualification.

Task 17 must verify the selected configuration under the complete synthetic anomaly and causality suite before Stage 2.5 may be frozen.

Stage 2.5 itself is not yet frozen by this decision.

Remaining work:

```text
Task 17 - Final Synthetic End-to-End Qualification
Task 18 - Final Regression and Freeze
```