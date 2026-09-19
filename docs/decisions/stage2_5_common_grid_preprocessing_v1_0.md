# Stage 2.5 Common-Grid Preprocessing Freeze Decision v1.0

Decision date: 2026-09-19

Decision: APPROVED FOR SOFTWARE FREEZE, subject to the publication acceptance
rule in section 8. Local evidence gates have passed. Creating this document does
not assert that a release tag already exists or has been remotely verified.

Branch: `research/stage2.5-common-grid-preprocessing-v1.0`

Release tag: `stage2.5-common-grid-preprocessing-v1.0` (annotated tag required)

Selected configuration: `stage2.5-preprocessing-final-v1.1`

The stage-release version v1.0 and audited configuration version v1.1 identify
different objects. This is the first Stage 2.5 software freeze decision; the
configuration identifier distinguishes the corrected behavior from historical
pre-audit v1.0 configuration evidence.

## 1. Separate implementation, selection and documentation identities

| Role | Identity |
| --- | --- |
| Audit hardening | 12618fa |
| Functional implementation used by both Task 17 runs | 4f98f70b8b99faa2a390b67cf7317e53fbf007b7 |
| Final configuration-selection and report-archive commit | 5e4aa586807b17b55d3f27e481dd03883a4ed9d7 |
| Freeze/documentation commit | D: the commit introducing this decision and its Windows verification record; the release tag must target D |
| Canonical qualification-report digest | 020A4C121EDE1F177D33DBE6C1E079B27FA53C08B98EF8CF51D626105CFC71E4 |
| Reproducibility digest | 508F3981EFE498ED1ECB19D6C3F2264FC9DBF5C34B45C14E1FB821C16A853B2E |

D is determined when this document is committed. Record its full hash in the
annotated tag message and the publication verification output. A commit cannot
contain its own literal final hash; resolve D from Git history rather than
substituting either of the already-known implementation/selection hashes:

```text
git log --diff-filter=A -1 --format=%H -- docs/decisions/stage2_5_common_grid_preprocessing_v1_0.md
```

After publication, the peeled annotated tag must resolve to that same D. The
functional implementation and recorded qualification digests continue to refer
to 4f98f70, even though the release tag includes subsequent documentation.

## 2. Contract approved for freeze

The governing selection decision is
`stage2_5_preprocessing_candidate_selection_v1_1.md` in this directory.
Its numerical policy and scientific boundaries are incorporated here:

| Component | Selected behavior |
| --- | --- |
| Grid | 100 Hz; 10,000,000 ns interval; integer origin 0; ALIGN_TO_ORIGIN |
| Domain and time coordinate | INTERSECTION; pc_mapped_ts_ns |
| Source ordering and duplicates | SORT_AND_REPORT; KEEP_FIRST with production stable ordering |
| ACCEL/GYRO resampling | PREVIOUS_SAMPLE_HOLD; no future source timestamps |
| Gap handling | EXPLICIT_STATUS; previous-source age <= 20,000,000 ns for usable rows |
| Axis transform | Identity x/y/z with positive sign in both sensor families |
| Bias | MEAN_PC_WINDOW; x/y/z; at least two eligible samples per family; explicit session-specific stationary pre-motion interval |
| Bias causality boundary | Publish only grid timestamps strictly greater than bias-window end |
| Low-pass filter | ONE_POLE_IIR; order 1; cutoff 10 Hz; grid frequency 100 Hz |
| Filter initialization/reset | FIRST_SAMPLE; EXPLICIT_BOUNDARIES; restart each valid run after an invalid gap |
| Active motion | GYRO x/y L2 norm >= 0.1; annotation separate from sensor validity |
| Padding | REPEAT_FIRST; history confined to the current contiguous sequence run |
| Supervision lag sign | grid_label_pc_time_ns = grid_pc_time_ns - alignment_lag_ns |

Reference-label transitions must not alter sensor filtering. Sensor validity and
supervision validity remain separate. Explicit invalid rows/boundaries must not
be silently converted into valid supervision.

File-backed preprocessing uses `build_stage25_from_artifacts`. Its checks bind
source bytes, selected calibration slice, identities, raw/mapped joins and
reconstructed clock-only quality. The in-memory numerical builder is a trusted
kernel, not an independent artifact-authentication boundary.

The selected representation applies across P0/P2C/L0/L2C wherever the upstream
contracts are compatible. A condition identifier or participant evaluation
outcome must not privately choose another Stage 2.5 policy. Future changes to
these policies require a versioned decision and appropriate requalification.

## 3. Sensor rate versus preprocessing grid

The Android code requests 100 Hz (10,000 microseconds), while prior device
characterization and the user's observation report native behavior near 125 Hz.
The selected analysis grid is 100 Hz. These are separate quantities.

Task 17 explicitly exercises native synthetic 125 Hz streams, including a 4 ms
ACCEL/GYRO offset, on the 100 Hz grid. Raw records retain their sensor timestamps.
Resampling selects the most recent eligible source observation at each grid
time. Neither native-rate observations nor the requested Android period alone
establish a final analysis frequency. This decision does not claim a measured
performance advantage of 100 Hz over a separately qualified 125 Hz analysis grid.

## 4. Accepted local verification evidence

The archived run01 report and verification record are:

```text
docs/evidence/stage2_5/task17_v1_4f98f70/qualification_report.json
docs/evidence/stage2_5/task17_v1_4f98f70/qualification_report.sha256
docs/evidence/stage2_5/task17_v1_4f98f70/verification_windows.json
```

The user's full generated bundles remain at these paths in the Windows repository:

```text
bench_data/stage2_5_preprocessing_qualification/task17_v1_4f98f70_run01/
bench_data/stage2_5_preprocessing_qualification/task17_v1_4f98f70_run02/
```

| Gate | Observed evidence |
| --- | --- |
| Stage 2.5 and upstream PC regression | python -m pytest pc -q: 672 passed in 11.98 s; exit 0; includes clock-sync, experiment and receiver tests |
| Synthetic end-to-end qualification | Both user runs VALID; exit 0; functional revision 4f98f70b8b99faa2a390b67cf7317e53fbf007b7 |
| Required scenarios | 23/23 PASS; all 54 actual/expected checks in the uploaded report independently recalculated as passing |
| Data role | synthetic; real_participant_data_used=false |
| Reference scope | Two cycles; sixteen sequences |
| Repeated Windows run | Equal canonical report sidecar digests; REPRODUCIBLE=True in user terminal output |
| Report identity check | Canonical run01 report SHA-256 matched the independently reviewed pinned digest |
| Current run01 artifact bytes | FILES_LISTED=302; FILES_MATCHED=302; FAILED_FILES=0; EVIDENCE_CHECK_EXIT_CODE=0 |
| Selection decision committed | 5e4aa586807b17b55d3f27e481dd03883a4ed9d7 includes historical v1.0, governing v1.1 and archived report/digest |
| Last supplied Git state before this document | No tracked modifications; only the engineering files/directories and delivery patches listed in section 7 |

The Windows results are supported by the user's terminal transcripts. The
run01 JSON was separately uploaded and inspected. Run02's entire output bundle
was not separately uploaded or checked byte-by-byte by the assistant. The local
inventory check covers all 302 paths listed by run01; it is not a claim that no
additional unlisted files exist in the directory.

The recorded Windows regression ran after application of Task 17 and before
committing that same tested code. The supplied subsequent changes were
documentation-only. Before tagging, verify that D contains no functional-code
changes relative to 4f98f70; any additional functional change reopens its test and
qualification gates.

The inventory and runtime checks complete the gates that were still pending
when selection decision v1.1 was written. The historical document remains an
accurate record of its preparation stage; this decision records the later checks.

## 5. Runtime and reproducibility boundary

```text
PYTHON=3.13.0 (tags/v3.13.0:60403a5, Oct  7 2024, 09:38:07) [MSC v.1941 64 bit (AMD64)]
OS=Windows-11-10.0.26200-SP0
ARCH=AMD64
```

The demonstrated exact repeatability is within this tested Windows environment.
A Linux reproduction agreed on policies and pass/fail outcomes but did not
reproduce all artifact bytes. Exposed numerical differences in the reports were
at most 5.551115123125783e-17, below the 1e-10 qualification tolerance. This does
not establish a bound for all unuploaded Windows artifact values.

Preserve original evidence and runtime information. Do not rewrite report hashes
or round old outputs to make different environments appear byte-identical.

## 6. Hash meanings and scope limits

The report `.sha256` is its canonical JSON digest: sorted keys, compact
separators, UTF-8, ensure_ascii=False. The uploaded/archived formatted report's
file-byte SHA-256 is
`BB5AE18A54509A88010AC4DD2E1E618034DCF8A2D133AF380DE719CDF56F3E71`.
The reproducibility digest excludes only its own field from the report before
hashing. Inventory hashes refer to physical file bytes.

The exact baseline config/grid/quality/manifest hashes are recorded in the
selection decision and `verification_windows.json`. They identify the synthetic
instance, including source hashes, bias window, revision and fixture lag. Actual
recordings require their own source-bound configurations and hashes.

This is a software preprocessing freeze. It does not establish:

- participant or learned-model performance, or optimal preprocessing parameters;
- a final numerical alignment lag, model window, controller/solver configuration,
  task geometry, Fitts implementation or participant protocol;
- real-recording bias stationarity, absolute clock accuracy or PC arrival-time
  availability from mapped-time causality alone;
- native-label manifest-chain qualification, transport-session qualification,
  or Android STOP/drain/persistence/lifecycle correctness.

The 5 ms lag, three-row diagnostic window, 125 Hz native stream and accelerated
guided trajectory in Task 17 remain explicitly synthetic fixture parameters.
Behavioral fixtures supply finite evidence, not proof over every input. Existing
Android and real-device qualifications remain separate work.

## 7. Accepted untracked engineering material

The supplied clean-state exception comprises:

```text
PktMon.etl
audit_b_extended_20260913_153121_985/
audit_b_receiver_diag_20260913_160603_016/
audit_m2_3_422f20d/
diagnostic_package_20260913_154940_181/
pc/receiver/logs_diagnostic/
stage25-audit-hardening.patch
stage25-task17-synthetic-qualification.patch
stage25-selection-v1_1-evidence.patch
stage25-final-freeze.patch
```

The final item is the delivery patch for this decision. These files remain local
and outside the release commit. They do not justify ignoring uncommitted source,
tests or decision documents. Preserve the two generated qualification bundles;
the tracked report archive is not a complete backup of those bundles.

## 8. Publication acceptance rule

Complete the approved Task 18 workflow on the research branch:

1. Commit this decision and the Windows verification record together as D.
2. Confirm the expected branch, clean tracked state, source equality with the
   functional implementation, and that the selection commit is an ancestor of D.
3. Create annotated tag `stage2.5-common-grid-preprocessing-v1.0` targeting D.
   Its annotation must record D, the functional and selection commits, and the
   canonical report and reproducibility digests. Check for an existing tag first;
   a conflicting existing tag requires investigation, not silent replacement.
4. Publish the research branch and annotated tag to the intended GitHub remote.
5. Verify the remote branch head equals D, the remote tag object equals the
   local annotated tag object, and the remote peeled tag target equals D.

The published freeze is complete only when these checks pass. It does not merge
the research branch into main or imply that participant data collection is ready.
Remote publication evidence is the captured ref-comparison output; this
immutable decision records the acceptance rule rather than claiming a future
network operation has already succeeded.
