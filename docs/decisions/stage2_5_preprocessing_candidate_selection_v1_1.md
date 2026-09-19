# Stage 2.5 Preprocessing Configuration Selection v1.1

Date: 2026-09-19

Status: SELECTED AND SYNTHETICALLY QUALIFIED; TASK 18 FREEZE PENDING.

Branch: `research/stage2.5-common-grid-preprocessing-v1.0`

Configuration identifier: `stage2.5-preprocessing-final-v1.1`

Audit hardening commit: `12618fa`

Task 17 functional implementation commit:
`4f98f70b8b99faa2a390b67cf7317e53fbf007b7`

The configuration-selection commit is the Git commit introducing this document.
Its exact hash must be recorded separately in the subsequent Task 18 freeze
decision. That documentation commit must not be substituted for the functional
implementation commit above when describing the existing qualification runs.

## 1. Relationship to the historical decision

This version supersedes the current-policy and qualification claims of
`stage2_5_preprocessing_candidate_selection_v1_0.md`. Keep the complete local
v1.0 document as a historical record; do not rewrite its evidence hashes or
delete its earlier reports.

The selected numerical policies remain the same. The v1.1 identifier separates
the audited behavior and verified source-artifact boundary from historical v1.0
evidence, as required by `stage2_5_audit_hardening_2026_09_19.md` and specified in
`stage2_5_task17_synthetic_qualification_v1_0.md`.

Historical candidate evidence is not sufficient to qualify the audited pipeline.
In particular, `EXACT_ONLY_COMPARISON` has no production implementation and the
corrected candidate qualifier reports `NOT_IMPLEMENTED`. It must not be described
as a production-qualified alternative. Historical fixture row counts and the
512-test result are historical observations, not the post-audit acceptance gate.

This decision records an engineering selection and its tested behavior. It does
not establish that the chosen values are empirically optimal for participants.
No participant outcome or condition-specific performance was used for selection.

## 2. Selected shared policy

| Component | Selected policy | Selection rationale |
| --- | --- | --- |
| Grid | 100 Hz; 10,000,000 ns; ALIGN_TO_ORIGIN with origin 0 | Preserve temporal resolution on an explicit integer lattice |
| Domain | INTERSECTION | Keep timestamps inside shared sensor support |
| Timing field | pc_mapped_ts_ns | Use the reconstructed sensor event-time coordinate |
| Reorder | SORT_AND_REPORT | Preserve observations while reporting disorder |
| Duplicate | KEEP_FIRST | Retain one observation according to the production stable ordering; report duplicate events |
| ACCEL and GYRO resampling | PREVIOUS_SAMPLE_HOLD | Use current or earlier observations on the asynchronous streams |
| Gap | EXPLICIT_STATUS; maximum source age 20,000,000 ns | Bound how long an observation can be held |
| Axis/sign | ACCEL and GYRO: x <- +x, y <- +y, z <- +z | Preserve native sensor channels without an unsupported inversion |
| Bias | MEAN_PC_WINDOW; x/y/z; minimum 2 samples per family | Use an explicitly designated stationary pre-motion interval |
| Filter | ONE_POLE_IIR; order 1; cutoff 10 Hz; grid 100 Hz | Select the less aggressive of the considered 5/10 Hz smoothing settings |
| Filter initialization/reset | FIRST_SAMPLE; EXPLICIT_BOUNDARIES | Initialize each valid run from its first sample; restart after an invalid gap |
| Active motion | GYRO x/y L2 norm; threshold 0.1; GREATER_EQUAL | Preserve sensitivity to the selected intermediate-motion fixture |
| Sequence-start padding | REPEAT_FIRST; padding_value field 0.0 | Initialize without future samples or an artificial zero vector |
| Label-lag sign | grid_label_pc_time_ns = grid_pc_time_ns - alignment_lag_ns | Preserve the Stage 2.4 supervision convention |

The same Stage 2.5-owned policies apply to P0, P2C, L0 and L2C where the upstream
contracts are scientifically compatible. Condition ID and evaluation outcome
must not select a different preprocessing configuration. Shared personalized
calibration must retain the required common source bundle and source slice.

## 3. Boundary semantics after audit

Published grid rows must satisfy
`grid_pc_time_ns > bias_correction.window_end_pc_ns`. Raw samples in the bias
interval remain available for estimation. The interval must be resolved for the
actual session and must contain sufficient eligible samples in both families.
Stationarity in a real recording requires separate evidence; the artifact
adapter does not infer it merely from timestamps or a caller flag.

The 20 ms limit applies to the age of the previous observation at each grid
timestamp. A reported native gap does not automatically invalidate every nearby
row. The Task 17 bounded-burst fixture has one gap event and zero invalid sensor
rows. Its excessive-gap fixture has one gap event and seven invalid sensor rows.
Those seven rows remain explicit while the build itself remains VALID.

The filter restarts after invalid sensor gaps. Reference supervision, reference
phase boundaries and condition identity must not change sensor filtering. Label
validity is separate from sensor validity. The Task 17 reference-boundary fixture
retains 63 UNRESOLVED_BOUNDARY rows and two OUTSIDE_REFERENCE rows as expected;
these are deliberate boundary tests, not evidence of usable supervision there.

Use `build_stage25_from_artifacts` for file-backed evidence. The lower-level
in-memory builder is a trusted numerical kernel and does not itself verify the
caller-provided artifact hashes or clock-pass assertion.

## 4. Observed Task 17 evidence

User Windows run directories:

```text
bench_data/stage2_5_preprocessing_qualification/task17_v1_4f98f70_run01/
bench_data/stage2_5_preprocessing_qualification/task17_v1_4f98f70_run02/
```

Run01's uploaded report is archived unchanged at:

```text
docs/evidence/stage2_5/task17_v1_4f98f70/qualification_report.json
```

The adjacent `.sha256` file contains its canonical JSON digest. The full generated
input/output bundles remain in their run directories. This repository archive
contains the report and digest, not copies of all 302 generated artifact files.

| Evidence | Recorded result |
| --- | --- |
| Dataset role | synthetic |
| Real participant data used | false |
| Reference coverage | 2 cycles; 16 sequences |
| Baseline common grid | 193 rows |
| Scenarios | 23/23 PASS |
| Individual checks | 54/54 passed, also recalculated from uploaded actual/expected fields |
| CLI result, both runs | VALID; exit code 0 |
| Functional revision, both runs | 4f98f70b8b99faa2a390b67cf7317e53fbf007b7 |
| Revision provenance | VERIFIED_CLEAN_GIT_HEAD_AT_CLI_START |
| Complete report digest equality | REPRODUCIBLE=True in user PowerShell output |
| Regression | 672 passed in 11.98 s on the user's Windows environment |

The test suite includes deliberate replacement of the production filter with
lookahead and a 1 ns grid shift. Both must invalidate qualification. Passing this
suite and the selected synthetic fixtures supplies finite behavioral evidence;
it is not a proof over every possible input.

Run01 was directly inspected. Run02's status, revision and digest equality are
supported by the supplied terminal output; its full report was not separately
uploaded. The 302 inventory entries in the report have valid hash syntax and
safe relative paths. Their current bytes on the user's machine still require
the local artifact-inventory check before the final freeze is declared.

## 5. Exact evidence identifiers

| Object | SHA-256 |
| --- | --- |
| Baseline preprocessing config, canonical | 2BBFC2E850461391AA91C6BA137A9A612BAA6EAF9FC51E03C6378D6820112832 |
| Baseline common-grid structure, canonical | 80CDF5D6EA40265E9E565F2D03D3C6D2DE914538A7C506B8A8D4E50B4925BA92 |
| Baseline quality, canonical | 063B72B9EBEB09419C3E6CF0720B70D7CCB1FD6B4FE6BB924BA21E5939394A0D |
| Baseline manifest, canonical | 101F02E55E4C5956B47ADD1429AB6018C83F647CEF733B506D9C3E91D861A184 |
| Qualification report, canonical | 020A4C121EDE1F177D33DBE6C1E079B27FA53C08B98EF8CF51D626105CFC71E4 |
| Uploaded/archived report file bytes | BB5AE18A54509A88010AC4DD2E1E618034DCF8A2D133AF380DE719CDF56F3E71 |
| Reproducibility digest | 508F3981EFE498ED1ECB19D6C3F2264FC9DBF5C34B45C14E1FB821C16A853B2E |

Canonical JSON uses sorted keys, compact separators and UTF-8 with
`ensure_ascii=False`. The reproducibility digest hashes the report before its
own digest field is added. `artifact_file_sha256` hashes actual file bytes.
These are distinct hash definitions and must not be interchanged.

The baseline configuration hash identifies one complete synthetic fixture
instance. It binds source hashes, revision, absolute bias interval and synthetic
lag as well as the shared policy. A new recording needs its own actual paths,
hashes and provenance values; do not copy this fixture hash into another session.

## 6. Reproducibility scope and runtime

Two complete Windows runs at the same functional revision produced equal
canonical report digests according to the supplied terminal output. Exact
reproduction is established for that tested environment, not for arbitrary
operating systems or Python versions.

An additional Linux reproduction, supplied with the same revision as a
caller-declared API argument, matched the selected policies and all pass/fail
outcomes. It matched 193 of the 302 recorded artifact hashes. In the report's
exposed numeric comparisons, the largest Windows/Linux difference was
5.551115123125783e-17, below the qualification tolerance of 1e-10. Other dependent
hashes differed. This is not a claim that all unuploaded Windows artifact bytes
were numerically compared or that cross-platform byte identity was demonstrated.
The Linux API report is not verified evidence that the user commit was checked
out there.

Record the exact Windows/Python runtime version during Task 18. Preserve both
existing run directories. Do not round or replace historical output solely to
force cross-platform hashes to match.

## 7. Scope limits and remaining Task 18 gates

The synthetic lag of 5 ms, three-row diagnostic window, native 125 Hz stream,
known bias values and accelerated guided trajectory are fixture parameters.
They do not select the final participant-study lag, model window or task geometry.
Controller gains, personalized solvers, learned-model architecture/adaptation,
Fitts implementation and participant outcomes remain outside this decision.

Source-verification claims are limited to the recorded scope. Clock fit residuals
do not establish absolute synchronization accuracy. Mapped event-time causality
does not establish availability at PC arrival time. Native-label manifest-chain,
transport and Android lifecycle qualification remain separate work. Full-study
readiness must not be inferred from this synthetic PASS.

Task 18 still requires the local 302-file inventory check, exact runtime record,
committed historical v1.0 and current v1.1 selection documents, and a worktree
clean except accepted untracked engineering evidence. The final decision must
record the functional implementation, selection and freeze/documentation commits
separately, retain the qualification digests, and complete the planned annotated
tag and remote verification workflow before declaring the published freeze.
