# Throughput Formula Realigned to Proposal 5.13

**Status:** accepted
**Date:** 2026-10-02
**Amended:** 2026-10-10, serial correction realigned to the additive form
of proposal 5.13 (`Ae_i = a_i + dx_i + dx_{i-1}`); see section 8.
**Scope:** `pc/experiment/task/throughput.py`,
`pc/experiment/tests/test_fitts_throughput.py`,
`docs/decisions/fitts-task-design.md`,
`docs/decisions/throughput-audit.md`
**Supersedes:** section 6 of `docs/decisions/fitts-task-design.md`
(never committed; the text below replaces it)

## 1. The conflict

Two repository documents specified **different** effective-throughput
estimators. Both were written as accepted, and the earlier one is what
the code implemented.

**Proposal section 5.13, "Definisi Operasional Throughput"** (locked
journal proposal, `proposal/Proposal_FINAL_JURNAL_TERKUNCI (1).docx`).
Per movement `i`, with `a_i` the distance from the from-target centre
to the to-target centre and `dx_i` the signed offset of the endpoint
against the to-target centre along the from-to direction:

```
Ae_1 = a_1 + dx_1
Ae_i = a_i + dx_i + dx_{i-1}   for i > 1, with dx_0 = 0
Ae   = mean(Ae_i)
We   = 4.133 * SDx           SDx = sample SD of the dx_i, n-1, including misses
ID_e = log2(Ae / We + 1)
TP   = ID_e / mean(MT)
```

and, verbatim:

> "Koreksi ini dipakai secara konsisten untuk tugas reciprocal serial
> dan bukan ukuran panjang lintasan kursor dua dimensi."

> "Endpoint initial acquisition tetap disimpan untuk audit, tetapi
> initial acquisition tidak dihitung sebagai transisi terukur."

> "Jika We=0 atau MT tidak valid, sequence ditandai flagged untuk audit
> dan tidak dianalisis sampai aturan beku disepakati; nilai tidak
> diganti secara ad hoc."

**`docs/decisions/fitts-task-design.md` section 6** (marked
"accepted (stage 2.11)") instead specified:

```
Ae_i  = dist(start_i, end_i)
IDe_i = log2(Ae_i / We + 1)
TP    = mean(IDe) / mean(MT)
```
## 2. Why the proposal wins

1. The proposal is the **locked** methodological artefact and 5.13 is
   literally titled the *operational definition* of the study's primary
   outcome. It is the authority for this metric.
2. It **explicitly rejects** the path-length reading, in the sentence
   quoted above. The design note asserts the opposite. One of them is
   wrong, and the proposal says which.
3. The design note is **not tracked by Git** at the time of this
   review. That is a statement about the repository index, not about
   approval: an untracked working file is still a record of a
   decision, and the header on it is not self-certifying either way.
   The correction below therefore rests on points 1, 2 and 4 — that the
   locked proposal says the opposite — and not on the tracking status.
4. The path-length estimator is **methodologically unsound** for this
   task, independent of the proposal:
   * it is orientation-blind, so a purely perpendicular miss inflates
     the amplitude by the full lateral deviation even though the
     movement along the task axis was unchanged;
   * its unit vector depends on the observed cursor start, so the same
     endpoint yields a different offset when the participant failed to
     land on the from-target centre;
   * it double-counts the miss carry-forward that the serial correction
     exists to model.
5. `mean(log2(Ae_i/We+1))` is not the quantity the proposal defines.
   For valid amplitudes and a fixed `We`, concavity of `log2` gives
   `mean(log2(Ae_i/We + 1)) <= log2(mean(Ae_i)/We + 1)`, with equality
   only when every `Ae_i` is equal, so the per-movement mean is biased
   low relative to the sequence-level value. That inequality is stated
   **only** for this estimator on valid amplitudes. It is not
   generalised to the older path-length estimator, whose amplitudes
   carry an additional orientation and cursor-origin error, so no bias
   direction is claimed for it here.
   `test_difficulty_is_sequence_level_not_mean_of_movements` pins the
   divergence on a deliberately uneven sequence.

## 3. What changed

`pc/experiment/task/throughput.py`:

* `movement_geometry(record, from_center, to_center)` now returns the
  nominal `a_i` and the axial offset `dx_i`, both derived from the
  **layout** centres. Its signature gained the from-target centre,
  because the proposal's amplitude does not depend on the cursor.
* `sequence_throughput()` applies `Ae_1 = a_1 + dx_1` and
  `Ae_i = a_i + dx_i + dx_{i-1}` across the measured block.
* Difficulty is computed **once per sequence**. `MovementTerm` lost
  `effective_id_bits`; `SequenceThroughput` gained
  `mean_effective_amplitude_px` and `index_of_difficulty_bits`.
* `effective_width()` gained `SPREAD_TOLERANCE`, rejecting a spread
  below `SPREAD_TOLERANCE * max(|dx|)`. A constant overshoot is the
  physical case where `SDx = 0`, and float noise was letting it
  through as a near-zero `We`.
* A non-positive corrected amplitude now raises.
* The measured-run contiguity check moved **into**
`pc/experiment/tests/test_fitts_throughput.py` grew from 32 to 38
tests. Two tests asserted the old behaviour by name and were replaced
rather than edited, because the behaviour they pinned is the defect:

* `test_actual_amplitude_is_not_nominal_distance_or_radius`
  -> `test_movement_geometry_amplitude_is_nominal_not_path_length`
* `test_orthogonal_miss_uses_actual_path_but_zero_axial_offset`
  -> `test_orthogonal_miss_leaves_amplitude_nominal_and_offset_zero`

`docs/decisions/throughput-audit.md` section 2.1 previously recorded
the amplitude rule as **PASS** with the regression name above. That
verdict is retracted in place rather than deleted, so the audit trail
shows what was believed and why it was wrong.

## 4. What did *not* change

These already matched the proposal and were left alone:

* `We = 4.133 * SDx` with the **sample** standard deviation
  (`n - 1`), including valid misses.
* `We` is computed once per sequence and shared by every movement.
* Hits and misses are both retained in the denominator with their own
  movement time and endpoint.
* The initial acquisition is recorded in full but excluded from
  `mean(MT)`.
* No teleport: the next movement starts from the previous trial's
  observed endpoint.
* `4.133` and the ms -> s conversion performed exactly once at the
  final division.

## 5. Consequences to check before the pilot

Realigning the estimator changes the **numbers**, so anything computed
under the old formula is not comparable with anything computed now.

* Any Fitts outcome already produced under `dist(start, end)` must be
  recomputed. If real participant data has been collected with the old
  estimator, discard or recompute it; do not mix.
* Proposal section 5.13 also states that if the throughput
  implementation or the serial logging changes after the freeze, the
  unit tests and the real-sequence audit must be repeated before the
  evaluation/SAP freeze. This change is exactly that kind of change.
* The reciprocal layout has a constant inter-target chord, so for
  balanced data `mean(Ae_i)` collapses to the nominal chord and the
  serial correction largely cancels. That is a property of the
  reciprocal task, not a sign the correction is inert: it still
  matters for the per-movement terms used in audit and for any
  unbalanced or shortened sequence. Confirm this empirically on real
  data rather than assuming it.

## 6. Sequence completeness and the endpoint export

The guard on `sequence_throughput()` was raised, not lowered, and it is
now a structured verdict rather than a single contiguity check.
`audit_sequence()` returns a `SequenceIntegrity` naming exactly how the
measured block failed, and it accepts
`expected_measured_transitions` so that head and tail truncation are
detectable. An interior-gap scan alone cannot see them: trials 1..8 of
a nine-transition sequence are internally contiguous.

Recognised statuses: `COMPLETE`, `TRUNCATED_HEAD`, `TRUNCATED_TAIL`,
`INTERNAL_GAP`, `DUPLICATE_TRIAL`, `MIXED_SEQUENCE_IDENTITY`,
`TECHNICAL_FAILURE`. A valid miss is none of these; it stays in the
denominator and is never reported as a technical failure.

`pc/experiment/task/selection_io.py` is the export for the corrected
path. The frozen stage 2.8 row schema (`schema.TRIAL_COLUMNS`, 31
columns) keeps `endpoint_error_px`, `signed_axial_error_px` and
`orthogonal_error_px` but has **no** `endpoint_x_px` / `endpoint_y_px`
and no `sequence_id`, so those rows cannot be turned back into a
`SelectionRecord` and cannot be re-analysed. The new export carries
both target centres, the raw endpoint, the timestamp, the sequence id,
the trial role and the denominator status, and rejects a read-back
against a layout it was not exported with.
`pc/experiment/tests/test_fitts_selection_roundtrip.py` asserts the
replayed throughput is bit-identical.

`build_sequence_trials()` — the frozen-2.8 row builder — has no caller
outside `pc/experiment/tests/test_fitts_miss_handling.py`. It is
therefore still live code with no production entry point, and the
endpoint loss above is documented rather than silently patched, because
changing `TRIAL_COLUMNS` would alter the frozen schema version.

## 7. Open items

* `docs/decisions/fitts-task-design.md` and
  `docs/decisions/throughput-audit.md` are still untracked. They should
  be committed, or the corrections recorded here will be lost.
* The reciprocal layout claim that a 9-target ring gives a balanced
  layout deserves an empirical check on real data before the SAP is
  frozen. Geometry is now verified from coordinates
  (`test_fitts_reciprocal_order.py`); what remains unmeasured is
  *participant* balance, i.e. that the nine amplitudes really do draw
  comparable endpoint spreads across participants.
* This note covers substage 2.8 only. It says nothing about whether
  stage 2 as a whole is ready for the pilot.

  `sequence_throughput()`. It previously lived only in
  `find_sequence_breaks()`, so an incomplete sequence could be pooled
  by any caller that forgot to call it. The proposal requires an
  incomplete sequence to be handled by the frozen missing/repeat rule
  instead of being analysed.


with the rationale that the amplitude is "the distance the cursor
actually travelled".

**Rencana substage 2.8 item 6** is closer to the proposal than to the
design note, reading "Simpan actual target-to-target amplitude, bukan
hanya diameter nominal layout" — the point of that requirement is that
the amplitude must be *recorded per movement* and not silently
replaced by a layout constant, which the serial-corrected `Ae_i`
satisfies.

> **SUPERSEDED 2026-10-10 -- sections 1-7 below are historical.**
> They record the **subtractive** reading `Ae_i = a_i - dx_{i-1}` that the
> repository carried before the additive correction. That reading is **no
> longer the rule**. The formula in force is the additive form
> `Ae_1 = a_1 + dx_1`, `Ae_i = a_i + dx_i + dx_{i-1}` (`dx_0 = 0`).
>
> **If you are looking for the current rule, go to
> `throughput-effective-amplitude.md`.** Do not take the formula from this
> file. The rest of this document is retained only so the change is auditable.

## 8. Amendment 2026-10-10: the serial correction is additive

Sections 1-7 above recorded the subtractive reading
`Ae_i = a_i - dx_{i-1}`. That reading is **superseded**. Proposal
section 5.13 states the effective amplitude of movement `i > 1` as

```
Ae_i = a_i + dx_i + dx_{i-1}
```

with the inherited term zero for the first measured movement,
`dx_0 = 0`. The proposal is the frozen protocol text, and the
implementation must follow it verbatim.

What changed:

* `pc/experiment/task/throughput.py` now computes
  `effective_amplitude_px = nominal_amplitude_px + endpoint_offset_px + previous_offset`,
  with `previous_offset` initialised to `0.0` and updated to the current
  endpoint offset after each measured movement. The `position == 0`
  branch is gone, because one expression now covers both cases.
* Every guard of sections 3 and 6 is unchanged: layout-derived `a_i`,
  axial `dx_i`, sequence-level `ID_e`, `We = 4.133 * SDx`, miss
  retention, refusal on `We = 0`, on invalid `MT`, and on incomplete
  sequences.
* The tests that pinned the subtractive behaviour were replaced rather
  than edited, because the behaviour they pinned is not the proposal's:
  `test_serial_correction_carries_offset_into_next_movement`,
  `test_serial_correction_never_uses_its_own_offset` ->
  `test_serial_correction_sums_own_and_inherited_offsets`, and
  `test_miss_endpoint_still_corrects_the_following_movement`. The last
  one now asserts `Ae_2 = a + 50`, not `a - 50`.
* New regression test
  `test_serial_correction_never_inherits_the_acquisition_offset` pins
  `dx_0 = 0`: the acquisition endpoint is logged for audit and never
  becomes the inherited offset of movement 1, which is the code-level
  form of the proposal's "initial acquisition is not counted as a
  measured transition".
* Two fixtures placed their endpoints on the ring order instead of on
  the measured traversal axis
  (`test_difficulty_is_sequence_level_not_mean_of_movements`,
  `test_incomplete_sequence_is_refused_before_pooling`) and were
  rebuilt from the generated measured steps. The subtractive form had
  masked the error, because it ignored `dx_i` and could only shrink a
  term, so an endpoint hundreds of pixels off the movement axis still
  produced a positive amplitude.
* `pc/experiment/tests/verify_fitts_28.py` now prints the inherited
  `dx_{i-1}` column and the rule itself, and
  `review_evidence_fitts28.txt` was regenerated from that harness: mean
  `Ae` 513.100032 px, `We` 41.967987 px, `ID_e` 3.725303 bits, `TP`
  4.543053 bits/s for the frozen 2.8 fixture, against 511.211143 px,
  3.720386 bits and 4.537056 bits/s under the superseded form.
* `review_evidence_pytest_pc.txt` and
  `review_evidence_pytest_experiment_tests.txt` were re-run after the
  change: `968 passed, 4 skipped` for `python -m pytest pc -q -ra` and
  `862 passed, 4 skipped` for the experiment-test subset. The four skips
  are environment-only (symlink creation is not permitted on this
  Windows host) and are unrelated to throughput.
* The two worked examples in
  `pc/experiment/tests/test_fitts_spread_tolerance.py` were requoted
  from the same arithmetic, and the hand-computed values in
  `pc/experiment/tests/test_fitts_throughput.py` now follow the additive
  rule instead of the cancelling-pair claim.

No participant data had been analysed under the subtractive form when
this amendment landed, so nothing has to be discarded. If any Fitts
outcome was produced with the subtractive code it must be recomputed,
per section 5.

`review_package_substage_28/` is deliberately left untouched. It is a
review snapshot pinned to base commit `4ea85f9`, with its own tracked
diff and its own copy of the harness output, so it still shows the
superseded subtractive numbers. That is historical evidence of what was
reviewed at that commit, not current code; the live code and the live
`review_evidence_fitts28.txt` are the ones above.

### 8.1 WITHDRAWN 2026-10-10 -- superseded reasoning, kept for the audit trail

> **DO NOT READ THIS AS A CURRENT CLAIM.** The argument in this subsection
> was withdrawn on 2026-10-10. It is reproduced below unchanged so the
> decision history is auditable. The corrected methodology, including why
> the sign claim fails and which conclusions are withdrawn, is in
> `throughput-effective-amplitude.md` sections 2 and 5.
>
> Summary of why it fails: in a reciprocating task the next movement
> reverses direction, so a predecessor overshoot leaves the cursor further
> along the previous axis and *lengthens* the return movement. Example --
> movement onto centre `100` ends at `110`; the next movement onto centre `0`
> must cover `110`, giving `100 + 0 + 10`. The "double counting" conclusion
> and the protocol-change recommendation that rested on this argument are
> both withdrawn. The **implementation is unchanged** and remains the
> additive form.

Under the sign convention the proposal fixes (`dx_i > 0` for an
overshoot), the distance movement `i` actually projects along the axis
is `a_i + dx_i - dx_{i-1}`, because an overshoot by the predecessor
*shortens* what the next movement still has to cover. The proposal's
`+ dx_{i-1}` therefore widens the amplitude instead of measuring the
travelled distance, and a single overshoot is counted twice: once on
the movement that made it and once on the movement that inherits it.

The code follows the proposal verbatim, because 5.13 is the authority
for this frozen protocol and changing it is a protocol amendment, not an
implementation detail. If the intended reading is the travelled
distance, then 5.13 must be amended first, and after that the unit
tests and the real sequence audit have to be repeated before
evaluation/SAP freeze, exactly as section 5 requires.