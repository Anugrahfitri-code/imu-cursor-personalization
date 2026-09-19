# Stage 2.5 Task 17 synthetic qualification v1.0

Status: implementation for local verification; final research freeze pending.

This implements Task 17 of the approved Stage 2.5 plan after audit hardening
commit `12618fa` on the research branch. It does not replace the existing
candidate-selection decision or its historical qualification evidence.

## Configuration and evidence identity

The runner uses `stage2.5-preprocessing-final-v1.1`. The new identifier separates
the audited implementation (including output strictly after the bias window and
verified source artifacts) from historical v1.0 evidence. The selected numerical
policies remain: 100 Hz grid, 20 ms maximum source age, previous-sample hold,
identity axes, explicit pre-motion mean bias, one-pole 10 Hz low-pass filter,
GYRO x/y norm >= 0.1, and REPEAT_FIRST padding. Filters restart at the beginning
of each valid run after an invalid gap. Reference-label boundaries do not reset
the sensor filter.

Per-fixture paths, hashes and stationary bias intervals are explicit. The 5 ms
label lag, three-row diagnostic window, 125 Hz native stream and accelerated
guided trajectory are synthetic engineering parameters. They do not select a
participant-study lag, predictive-model window, or movement protocol.

## What is actually exercised

The runner constructs an Android-shaped raw CSV, 120 raw clock probes, a fitted
clock model, Stage 2.4 mapped sensor rows, a full two-cycle / sixteen-sequence
guided reference, and a calibration source-selection manifest. Every ordinary
scenario invokes `build_stage25_from_artifacts`, including its byte-hash,
identity, source-join and reconstructed clock-quality checks.

| Scenario | Expected evidence |
| --- | --- |
| Regular, 4 ms sensor offset, timestamp jitter | Exact integer grid; independently calculated hold and filtered channels |
| Reorder and conflicting duplicate | Anomaly count; stable sort and KEEP_FIRST values |
| Missing sample, bounded burst, excessive gap | Explicit hold-age semantics; invalid rows and filter restart where necessary |
| Basis vectors and known bias | All axes/signs; subtraction of the known injected stationary bias |
| Filter impulse and step | Closed-form one-pole response independently of the production recurrence |
| Positive and negative future perturbation | Earlier sensor values, flags and padded windows unchanged; later values change |
| Motion threshold boundaries | Below / exactly at / above 0.1; excluded z channel has no effect |
| Sequence-start padding | Current/past history only; independent expected windows and padding masks |
| Reference-label boundaries | Independent lagged lookup; unresolved transitions and outside-reference rows |
| Deterministic rebuild | Identical full production bundle and hashes |
| Invalid timestamp, altered clock, foreign identity | Specific rejection despite recomputed source hashes |
| Source boundaries | Grid stays within common support and strictly after the bias interval |
| Changed reference | Sensor channels/flags unchanged while supervision changes |
| Receive time / outcome / condition perturbation | Trusted in-memory kernel ignores these fields |

The bounded burst removes two 8 ms GYRO samples, creating a 24 ms native gap.
Whether a particular grid row is usable depends on its age from the preceding
sample (<= 20 ms), not solely on the adjacent native gap's classification.
An excessive gap invalidates affected rows; it does not automatically invalidate
the whole build. This distinction is recorded in the report.

The independent filter oracle uses a closed-form weighted sum with absolute
tolerance 1e-10. Grid timestamps and categorical statuses require exact equality.
Regression tests deliberately replace the production filter with lookahead and
shift the production grid by 1 ns; neither may produce a VALID qualification.

## Running and interpreting evidence

First commit the implementation and its tests. The CLI refuses an uncommitted
implementation or tracked changes under `pc/clock_sync` and `pc/experiment`.
Unrelated engineering logs and the pending candidate-selection document do not
prevent this software check. Use a new output directory for every run:

```powershell
python -m pc.experiment.preprocessing.synthetic_qualification --output-dir "bench_data/stage2_5_preprocessing_qualification/task17_v1_run01"
```

Exit code 0 means every listed scenario passed; 1 means at least one scenario
failed; 2 means execution was refused or an input/build error occurred. A failed
or partial directory is preserved and must not be reused. No previous evidence
is deleted or overwritten.

`qualification_report.json` contains each check's actual/expected values, all
selected policies, baseline config/grid/quality/manifest hashes, functional
revision, source-verification scope and a reproducibility digest. The CLI binds
the revision to clean Git HEAD at startup. The Python API instead labels the
revision as caller-declared; unit-test reports are not commit-verified evidence.

`artifact_file_sha256` hashes actual file bytes. The standalone report `.sha256`
hashes canonical JSON (sorted keys, compact separators, UTF-8), not the formatted
JSON file bytes. The reproducibility digest hashes the report before adding its
own digest field. This avoids self-reference. Source CSV, raw probes, expected
values and production artifacts are retained for inspection.

## Limits and next gate

VALID here qualifies synthetic software behavior. It does not establish
participant validity, model performance, absolute clock accuracy, PC arrival-time
availability, transport quality, Android lifecycle safety, or the native-label
manifest chain. Stationarity is constructed in these fixtures. Real-recording
stationarity still needs independent evidence.

Task 18 remains pending: run this committed implementation on the research
machine, inspect its new evidence, reconcile and commit the existing candidate
decision, then perform the final regression/freeze workflow. Do not replace
historical reports with the new output or infer research readiness from pytest
alone.
