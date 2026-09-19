cd "D:\IMU_Cursor_Research"

Write-Host ""
Write-Host "============================================================"
Write-Host "STAGE 2.5 TASK 16 - PREPROCESSING CANDIDATE SELECTION"
Write-Host "============================================================"

$decisionPath = `
".\docs\decisions\stage2_5_preprocessing_candidate_selection_v1_0.md"

$qualificationDigestPath = `
".\bench_data\stage2_5_preprocessing_candidate_qualification\qualification_v2\qualification_report.sha256"

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

if (Test-Path $decisionPath) {
    throw (
        "Stage 2.5 candidate-selection decision already exists. " +
        "STOP to avoid overwriting an unexpected decision."
    )
}

if (-not (Test-Path $qualificationDigestPath)) {
    throw "Qualification V2 digest is missing. STOP."
}

$qualificationDigest = (
    Get-Content $qualificationDigestPath
).Trim().ToUpper()

$expectedDigest = `
"D8E8FA9DC0A2B73765520E9B35CB8BE0B086D8636D54A2CF6500AA89E85DD5A4"

if ($qualificationDigest -ne $expectedDigest) {
    throw (
        "Qualification V2 digest does not match audited evidence. " +
        "STOP."
    )
}

$decisionContent = @'
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