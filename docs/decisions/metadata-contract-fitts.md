# Metadata contract for the Fitts selection export

**Status:** current, evidence-backed.
**Date:** 2026-10-10
**Scope:** what the selection CSV does and does not carry, and which
artefact actually supplies each piece of required metadata.

Every claim below is traceable to code in
`pc/experiment/task/selection_io.py` at the commit packaged alongside this
document. Nothing here is inferred from intent.

## 1. The reader, verbatim

```python
def read_selection_csv(
    path: str | Path,
    targets_by_label: Mapping[str, tuple[float, float]],
) -> list[SelectionRecord]:
```

**Two parameters. That is the entire contract.**

`targets_by_label` maps a label to a **centre only** -- a `(x, y)` tuple of
floats. It is caller-supplied geometry. This single fact drives most of what
follows.

## 2. The stored columns

`SELECTION_COLUMNS`, exactly as declared in `selection_io.py` line 28:

```
sequence_id, trial_index, trial_role,
from_target, to_target,
from_center_x_px, from_center_y_px,
to_center_x_px, to_center_y_px,
cursor_start_x_px, cursor_start_y_px,
cursor_end_x_px, cursor_end_y_px,
endpoint_x_px, endpoint_y_px,
selection_time_ms,
hit, miss, denominator_status
```

The reader rejects any file whose header tuple is not exactly this tuple
(`selection_io.py` line 223), so a file that has been reordered or extended
is refused rather than partially parsed.

## 3. Required metadata, and where each one actually comes from

| Metadata needed | In the CSV? | Supplied by | Strength of the link |
|---|---|---|---|
| Target centre | Yes -- four `*_center_*_px` columns per row | The CSV itself, cross-checked against the caller's `targets_by_label` | **Strong.** Mismatch raises `ValueError` (`_verify_centers`). |
| Target **width** | **No.** No width column exists | Caller, via whatever produced `targets_by_label` | **Caller obligation.** Not validated on read-back. |
| Layout / config identity | **No.** No layout id, no config hash | Caller | **Weak. Not validated.** See section 4. |
| Sequence identity | Yes -- `sequence_id` on every row | The CSV | **Moderate.** Present, but see section 5. |
| MT duration | Yes -- `selection_time_ms` | The CSV | **Strong for the value**, see section 6. |
| Technical status | Yes -- `hit`, `miss`, `denominator_status` | The CSV | **Strong.** Non-numeric and non-finite MT is rejected. |

## 4. Centre checking is not width checking and not layout identity

This distinction is easy to get wrong and matters for the audit:

`_verify_centers` compares the `from`/`to` centre columns **against the
caller-supplied `targets_by_label`**. That is a centre check. Concretely:

* It **can** detect a row exported against different target positions,
  because a moved target changes its centre.
* It **cannot** validate target **width**. Width never appears in the file
  and never reaches the reader, so a re-analysed export inherits whatever
  width the caller passes. `We = 4.133 * SDx` is computed from endpoints,
  but any separate width-dependent quantity is on the caller's honour.
* It **cannot** establish **layout or config identity**. Two different
  configs that happen to share target centres are indistinguishable to this
  reader. There is no layout id, no config hash, and no session id column in
  `SELECTION_COLUMNS`.

**Stated limitation, not a workaround:** the export is *not* self-describing.
Analysis code that needs width or config identity must obtain it from the
run configuration out of band. This document does not claim the CSV is
standalone, because it is not.

## 5. Sequence identity

`sequence_id` is stored on every row and is read back onto each
`SelectionRecord`. Identity is then *enforced* one level up, in
`audit_sequence()` / `sequence_throughput()`, which take
`expected_sequence_id` and treat heterogeneity as disqualifying:

* if the caller supplies an expectation, every measured record must carry
  that id, and any foreign id is named in the failure;
* if no expectation is supplied, more than one distinct id is still
  disqualifying on its own -- which id is the intruder cannot be named, but
  heterogeneity alone sinks the sequence;
* a blank / whitespace-only id is also rejected.

Ordering does **not** come from file order. `measured_records_in_order()`
sorts by `trial_index`, and the docstring is explicit that the terms take
their order from `trial_index` rather than from the list. A shuffled or
re-sorted export therefore still analyses correctly, and the reader does not
silently trust CSV row order.

## 6. MT duration and technical status

`selection_time_ms` is parsed as follows (`selection_io.py` lines 232-239):

* empty or whitespace-only -> `selection_time_ms = None`. This is a
  **permitted** state, not an error; the round-trip fixture exercises it
  deliberately.
* present but non-finite (`nan`, `inf`) -> `ValueError`. A non-finite
  timestamp is rejected rather than silently poisoning `mean(MT)`.
* present and finite -> used as the movement time.

Technical status is carried explicitly by `hit`, `miss` and
`denominator_status`, so a trial's role in the denominator is recorded
rather than inferred from a threshold.

## 7. API protection versus caller obligation

These are different things and the distinction is load-bearing.

**What the API guarantees.** Given the right arguments, the API refuses bad
input: it rejects a mismatched column header, mismatched target centres,
non-finite timestamps, duplicate trial indices, interior gaps, head and tail
truncation, and records from more than one sequence. `sequence_throughput()`
raises rather than returning a partial aggregate when `audit_sequence()`
reports the sequence incomplete.

**What only the caller can guarantee.** `expected_measured_transitions` is a
**required input from a trusted plan**. This is the honest limit of the
protection:

> The API cannot detect that a caller passed an `expected` count derived
> from a truncated recording instead of from the plan. If the plan says nine
> transitions and the truncated recording also contains nine rows, the API
> sees a complete sequence. Nothing in the record set distinguishes the two.

Interior-gap scanning has the mirror-image blind spot: trials 1..8 of a
nine-transition sequence are internally contiguous, so a head-truncated
recording is only detectable **when the expected count is supplied from the
plan**. Supplying it is a caller obligation, and `verify_fitts_28.py`
enforces this on itself -- it asserts that the count it passes equals the
layout's declared target count, and the rejection tests fail if that guard
is removed.

**Rule of thumb:** `expected_*` values are assertions by the caller. They
are only as trustworthy as the plan they came from.

