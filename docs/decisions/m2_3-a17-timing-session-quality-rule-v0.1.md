# M2.3 A17 Timing and Session Quality Rule

Version: 0.1
Status: PRE-FREEZE DECISION DRAFT
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

Status: NOT YET FROZEN.

The final numerical residual rule must be justified relative to the frozen analysis/resampling time grid and label-alignment requirements.

It must be specified before the post-freeze confirmation run.

It must not be chosen merely to make an already-observed characterization run pass.

## 9. Numerical transport/burst criterion

Status: NOT YET FROZEN.

The final allowable live-transport gap must be justified relative to the frozen cursor update/resampling and missing-sample handling policy.

It must be specified before the post-freeze confirmation run.

It must not be selected merely from the empirical distribution of existing qualification runs.

## 10. Existing A17 evidence classification

Existing 2-minute, 10-minute, and 25-minute runs are retained as characterization evidence.

They may inform failure-mode understanding and requirement design but cannot serve as confirmatory evidence for a numerical threshold introduced after those runs.

The latest 25-minute run demonstrates:
- continuous local acquisition;
- reconstructable affine clock mapping;
- intermittent end-to-end transport disturbance;
- no exact physical network substage isolated.

## 11. Confirmation principle

After the complete numerical rule is frozen, at least one new participant-representative confirmation run must be collected without source or threshold changes.

The confirmation result must be evaluated against the frozen rule exactly as written.

No threshold may be relaxed after viewing that confirmation result.

## 12. Current status

M2.3 final freeze: NOT COMPLETE

Frozen now:
- procedural integrity rule;
- Android local-acquisition integrity rule;
- official-analyzer reconstructability requirement;
- clock response rate >=95 percent;
- payload integrity requirement;
- required diagnostic metrics.

Still open:
- numerical clock-residual quality boundary;
- numerical transport/burst quality boundary;
- confirmation run under the final frozen rule.
