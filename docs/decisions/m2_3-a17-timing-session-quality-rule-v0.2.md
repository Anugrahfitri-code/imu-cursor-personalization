# M2.3 A17 Timing and Session Quality Rule

Version: 0.2
Status: PRE-FREEZE NUMERICAL RULE DRAFT
Device: Samsung Galaxy A17 4G (SM-A175F)
Repository baseline: 89b6512
Date: 2026-09-15

## 1. Purpose

This document defines the prospective quality framework for M2.3 clock synchronization and transport validity before participant pilot work.

Existing characterization runs are evidence used to understand failure modes. They are not used as confirmation runs for thresholds introduced after those runs were observed.

A new confirmation run must be performed after the final numerical rule is frozen.

## 2. Scope

M2.3 establishes whether smartphone sensor timestamps can be mapped to the PC monotonic timebase with sufficient integrity for supervised label construction and whether the real-time transport path is technically usable for the experimental cursor loop.

This rule does not define Fitts outcome success and does not use participant performance.

## 3. Procedural hard gate

A run is procedurally eligible only if:

- device is Samsung SM-A175F;
- Android/PC software commit and configuration are recorded;
- receiver is active before the recording stream is evaluated;
- the current phone IP and PC target IP are verified;
- raw Android IMU, Android metadata, PC UDP capture, clock probes, and run metadata are preserved;
- no raw evidence is manually edited.

Failure of any item makes the run procedural-invalid for primary qualification.

## 4. Local Android acquisition hard gate

The local Android acquisition path must satisfy:

- global local sequence missing = 0;
- no unreconciled local duplicate sequence;
- sensor timestamps remain monotonic;
- final_network_queue_drops = 0;
- final_udp_send_errors = 0;
- final_local_queue_remaining = 0;
- final_network_queue_remaining = 0.

These requirements are integrity invariants and are not derived from observed PC packet-loss rates.

## 5. Clock-model hard gate

The official version-controlled M2.3 analyzer must successfully reconstruct an affine phone-to-PC clock model.

The pre-existing implementation requirement is:

clock_response_rate >= 0.95

The 95 percent boundary existed in the M2.3 analyzer before the current final-device characterization and is therefore retained as a hard eligibility rule rather than selected from the observed A17 results.

The analyzer's absolute skew sanity check:

abs(skew_ppm) < 1000

is retained as an implementation sanity check and must not be interpreted as the scientific timing-quality target.

Analyzer failure means the session clock mapping is invalid for label-dependent analysis.

## 6. Clock diagnostics required for every eligible run

The following must always be archived:

- response rate;
- valid and invalid probe counts;
- invalid reason counts;
- alpha;
- beta;
- overall skew;
- first-half skew;
- second-half skew;
- absolute residual P50;
- absolute residual P95;
- absolute residual maximum;
- delay-like P50/P95;
- phone-processing P50/P95;
- selected/inlier probe counts.

## 7. Transport integrity

For every run record:

- Android UDP packets sent;
- PC unique packets received;
- missing packet count;
- packet-loss percentage;
- missing-burst distribution;
- maximum global missing burst;
- maximum per-sensor contiguous delivery gap;
- duplicate packets;
- out-of-order packets;
- payload mismatches.

Packet-loss percentage alone must not determine validity because equal total loss can have different closed-loop consequences depending on burst structure.

For packets received at both endpoints, payload mismatch must equal zero.

## 8. Numerical timing residual criterion

The qualification time grid is 100 Hz, corresponding to a 10 ms grid interval.

Raw Android IMU remains preserved at the native observed acquisition rate. The 100 Hz grid is a derived common timebase for qualification and subsequent preprocessing; raw acquisition is not downsampled destructively.

Clock mapping is timing-valid only if:

- absolute residual P95 <= 1.0 ms;
- absolute residual maximum <= 5.0 ms;
- the official analyzer successfully reconstructs the affine model;
- clock response rate >= 95 percent.

Rationale:

- 1.0 ms is 10 percent of the 10 ms analysis-grid interval;
- 5.0 ms is one half of the analysis-grid interval;
- therefore accepted mapping uncertainty remains substantially below one analysis sample for the great majority of mapped timestamps.

P50 residual, alpha, beta, overall skew, half-run skew, delay-like values, and phone-processing values remain mandatory diagnostics but do not introduce additional post-hoc numerical pass/fail boundaries.

The analyzer's abs(skew_ppm) < 1000 requirement remains an implementation sanity check rather than the scientific timing target.

## 9. Numerical transport/burst criterion

For a participant-representative qualification run, end-to-end live transport is eligible only if all of the following hold:

- packet loss <= 0.10 percent;
- maximum per-sensor contiguous delivery gap <= 50 ms;
- payload mismatch = 0;
- duplicate and out-of-order events are detected and recorded;
- no duplicate or reordered packet may produce an unreconciled extra or temporally incorrect cursor update in the final experimental pipeline.

The per-sensor delivery gap is measured from the last received sample before a missing run to the first received sample after that run using the sensor timestamp sequence. It is not estimated only from aggregate packet-loss percentage.

Rationale:

- 0.10 percent limits aggregate missing delivery to at most one packet per thousand;
- the separate burst rule prevents a low aggregate loss percentage from hiding a long live-control interruption;
- 50 ms corresponds to five intervals on the 100 Hz qualification grid and is treated as a hard engineering ceiling, not as a claim of imperceptible interaction latency.

The 25-minute soak/stress runs are retained as robustness characterization and are not required to satisfy the participant-representative 10-minute transport gate.

## 10. Existing A17 evidence classification

Existing 2-minute, 10-minute, and 25-minute runs are retained as characterization evidence.

They may inform failure-mode understanding and requirement design but cannot serve as confirmatory evidence for a numerical threshold introduced after those runs.

The latest 25-minute run demonstrates:
- continuous local acquisition;
- reconstructable affine clock mapping;
- intermittent end-to-end transport disturbance;
- no exact physical network substage isolated.

## 11. Confirmation principle

After the complete numerical rule is frozen, two new independent participant-representative confirmation runs of 10 minutes each must be collected without source, configuration, or threshold changes.

Both planned confirmation runs must satisfy every frozen hard gate.

The confirmation results must be evaluated against the frozen rule exactly as written.

If either confirmation run fails a hard gate, M2.3 final freeze is blocked. The run must be preserved. Thresholds must not be relaxed and additional runs must not simply be repeated until a passing result appears.

If an engineering or protocol change is made after a failed confirmation, the rule/version and software/configuration baseline must be updated prospectively and a new confirmation set must begin.

## 12. Current status

M2.3 final freeze: NOT COMPLETE

Frozen now:
- procedural integrity rule;
- Android local-acquisition integrity rule;
- official-analyzer reconstructability requirement;
- clock response rate >=95 percent;
- payload integrity requirement;
- required diagnostic metrics.

Numerical rules proposed in v0.2:
- qualification grid = 100 Hz;
- absolute clock residual P95 <= 1.0 ms;
- absolute clock residual maximum <= 5.0 ms;
- end-to-end packet loss <= 0.10 percent;
- maximum per-sensor contiguous delivery gap <= 50 ms;
- payload mismatch = 0.

Still open:
- independent review of these numerical rules before final freeze;
- implementation/test of deterministic session-quality evaluation;
- two new 10-minute confirmation runs under the final frozen rule.
