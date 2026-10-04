# Effective amplitude for the reciprocal Fitts sequence

**Status:** current. This is the authoritative statement of the effective
amplitude rule used by `pc/experiment/task/throughput.py`.
**Date:** 2026-10-10
**Supersedes:** section 8.1 of `throughput-formula-proposal-alignment.md`
(the sign argument written there has been withdrawn; see section 7).
**Scope:** substage 2.8 analysis only. Nothing here changes the collection
protocol.

If you are looking for the rule, this is the page. Sections 1-7 of
`throughput-formula-proposal-alignment.md` are retained as history and are
explicitly marked superseded; they are not the rule.

## 1. The rule in force

    Ae_1 = a_1 + dx_1
    Ae_i = a_i + dx_i + dx_{i-1},   for i > 1,   with dx_0 = 0

* `a_i` -- nominal amplitude, the distance from the from-target centre to
  the to-target centre.
* `dx_i` -- the trial's own **signed axial** endpoint offset, positive in the
  direction of travel along that trial's movement axis.
* `dx_{i-1}` -- the previous movement's own axial offset, **measured on the
  previous movement's axis**. `dx_0 = 0` because the acquisition endpoint is
  never inherited.

Sequence-level aggregates are unchanged:

    We  = 4.133 * SDx          (SDx over the measured signed offsets)
    ID_e = log2(mean(Ae) / We + 1)
    TP   = ID_e / mean(MT)

## 2. Why the previous trial's offset is *added*

### 2.1 The claim that has been withdrawn

Earlier text in this repository asserted that an overshoot of the previous
trial always shortens the next movement, and that adding the previous offset
therefore "double counts" against the path length already travelled. **That
claim is wrong for a reciprocal task and has been withdrawn.**

### 2.2 What actually happens in a reciprocating movement

In a back-and-forth task the next movement reverses direction. If the
previous movement overshot, the cursor now sits *further along the previous
axis*, which is exactly where the reverse movement has to come back **from**.
The overshoot is therefore extra travel that the return movement must undo.
It lengthens the next movement.

Worked example, on the same axis, positive direction being the first
movement:

* Movement 1: target centre at `100`, cursor starts at `0`, ends at `110`.
  So `a_1 = 100`, `dx_1 = +10` (overshoot of 10 px).
* Movement 2: target centre at `0`. The cursor must travel from `110` to `0`,
  a genuine displacement of `110`. So `a_2 = 100`, `dx_2 = 0`, and

      Ae_2 = a_2 + dx_2 + dx_1 = 100 + 0 + 10 = 110

which is the travel that really occurred. The inherited `dx` **lengthened**
the movement, exactly as the physical trajectory requires.

The same rule shortens a movement when the previous trial undershot, for the
mirror-image reason: an undershoot leaves the cursor short of where the
reverse movement starts from. The additive form therefore both lengthens and
shortens depending on the sign of the inherited offset. Any earlier
description of it as inherently "shortening" was incorrect.

## 3. Primary sources for the serial addition

The additive serial treatment is standard practice in the Fitts' law
tooling used for rhythmic / reciprocal pointing, where the responses are
serially dependent and the deviation left at the end of one movement is
carried into the difficulty of the next:

* I. S. MacKenzie (1992), *Fitts' law as a research and design tool in
  human-computer interaction*, Human-Computer Interaction 7(1), 91-139.
  DOI: [10.1207/s15327051hci0701_3](https://doi.org/10.1207/s15327051hci0701_3).
* I. S. MacKenzie (2015), *Fitts' throughput and the remarkable case of
  touch-based target selection*, in *Human-Computer Interaction International
  2015*, LNCS 9170, pp. 238-249.
  DOI: [10.1007/978-3-319-20916-6_23](https://doi.org/10.1007/978-3-319-20916-6_23).
  This is the work behind the hosted tutorial page
  <https://www.yorku.ca/mack/hcii2015a.html>; the page is a web rendering of
  it, not a separate publication, so the page URL must not be cited in place
  of the 2015 paper.
* Fitts Law software documentation, *Throughput* --
  <https://www.yorku.ca/mack/FittsLawSoftware/doc/Throughput.html>
  (effective width, `ID_e`, and throughput from a sequence of trials).

> **Provenance note, stated plainly.** The two claims attributed to these
> pages -- that throughput is accumulated over a sequence rather than per
> trial, and that the endpoint deviation of the previous trial is added to
> the effective amplitude of the following serial movement -- were read from
> those pages. They are recorded here as a **paraphrase of the rule**, not as
> a verbatim quotation, because a character-for-character transcription was
> not captured during this review. A reviewer confirming the citation should
> open both URLs directly rather than trust this restatement.

The repository's own frozen definition is proposal section 5.13, and the
implementation follows it. The sources justify the practice; 5.13 is the
binding internal spec.

## 4. This estimator is not the endpoint-to-endpoint projection

The proposal estimator is a **1D axial serial estimator**. It must not be
reported as the endpoint-to-endpoint displacement.

`G_i` below is a **projection of the displacement between two successive
endpoints**, not a two-dimensional travelled path length. The path actually
taken between those endpoints is never measured; only the net displacement,
projected on the movement axis, is. Neither quantity is a path length.

The projection expression, for the movement whose own endpoints are `S_i` (the
cursor start of that movement) and `E_i` (its cursor end), against the unit
movement axis `u_i`, is

    G_i = dot(E_i - S_i, u_i)

The **same expression applies to every movement**, including the first. For the
first measured movement `S_1` is the acquisition endpoint, so `G_1` is a genuine
endpoint-to-endpoint displacement. An earlier revision special-cased the first
movement as `a_1 + dx_1`; that silently dropped the acquisition offset and
reported a from-centre-to-endpoint projection instead. That branch has been
removed. The presence of a preceding movement axis is consulted **only** to
decide whether an inter-axis turning angle exists, and never to alter `G_i`.

The structural difference from the adopted estimator matters and is easy to
miss:

* `dx_{i-1}` in the adopted rule is the previous offset projected onto the
  **previous** movement axis `u_{i-1}`;
* `G_i` uses each movement's **own** two endpoints, on the **current** axis
  `u_i`.

**These two quantities are not the same object and must not be substituted
for one another.** They coincide only in the special case where consecutive
movement axes are exactly anti-parallel, i.e. pure 1D reciprocation along a
single line, where `u_{i-1} = -u_i` and `-dot(P_{i-1} - F_i, u_i)` reduces to
`dx_{i-1}` exactly.

### 4.1 Measured divergence on the harness layout

`_repro_numeric_check.py`, section [D], computes both estimators on the
deterministic 9-target ring layout used by the verification harness:

| quantity | value |
|---|---|
| angle between consecutive movement axes | 160.00 deg (min and max) |
| mean `Ae_i` (adopted estimator) | `513.1000315663482` px |
| mean `G_i` (endpoint-to-endpoint projection) | `513.4346382712598` px |
| `G_1` (first measured movement) | `517.7145657026941` px |
| largest per-trial gap `G_i - Ae_i` | `3.614534` px (trial 1) |
| largest per-trial gap `G_i - Ae_i`, trials 2..9 | `1.085533` px |

The largest gap is now on trial 1, where `Ae_1` carries no inherited offset
(`dx_0 = 0`) while `G_1` measures from the acquisition endpoint. On trials
2..9 the gap is at most `1.085533` px, which is the structural difference
described above.

The axes turn by 20 degrees per step on this ring, so the axes are 160
degrees apart rather than 180, and the two estimators genuinely diverge.
**No estimator change is proposed on this basis.** The research estimator
stays as specified in 5.13. This measurement is recorded as a bound on
interpretation: `Ae` is a serial axial difficulty term, not a path-length
measurement, and the report should say so.

## 5. Conclusions that are withdrawn

The following conclusions rested **only** on the sign argument of section
2.1. They are removed, not restated:

1. **"Double counting."** The claim that adding `dx_{i-1}` double counts the
   deviation already accounted for by travelled path length is withdrawn. It
   does not follow from the geometry of a reciprocating movement, where the
   inherited offset lengthens the reverse movement (section 2.2).
2. **"The protocol must change."** The earlier recommendation to change the
   acquisition/target protocol on the grounds that the sign made the metric
   invalid is withdrawn. Nothing in this review requires a protocol change.
3. **"The sign of the previous overshoot always shortens the next movement."**
   Withdrawn; see section 2.2.

### 5.1 What still stands

Withdrawing an argument is not the same as saying nothing was wrong. The
following remain valid and are unaffected:

* The original code substituted the **travelled path length** for the
  corrected amplitude. A path length is orientation-blind, so a purely
  lateral (perpendicular) miss inflated the amplitude although it costs
  little on the movement axis. That defect was real and is fixed.
* `ID_e` and `TP` are defined once per sequence, not averaged per movement.
* The acquisition endpoint is logged for audit and never inherited as
  `dx_0`.
* After a miss, the next movement genuinely starts from the miss endpoint.

## 6. Numerical verification and floating-point tolerance

`_repro_numeric_check.py` rebuilds the sequence terms from the printed
geometry and recomputes `SDx`, `We`, `ID_e` and `TP` in closed form, then
compares against `pc.experiment.task.throughput.sequence_throughput` with an
absolute tolerance of `1e-9`.

| quantity | library | independent | delta |
|---|---|---|---|
| mean `Ae` | `513.1000315663482` | `513.1000315663482` | `0.000e+00` |
| `SDx` | `10.154364141151882` | `10.154364141151882` | `0.000e+00` |
| `We` | `41.96798699538073` | `41.96798699538073` | `0.000e+00` |
| `ID_e` | `3.725303400734592` | `3.725303400734592` | `0.000e+00` |
| mean MT | `820.0` | `820.0` | `0.000e+00` |
| `TP` | `4.543052927725112` | `4.543052927725112` | `0.000e+00` |

**On exact float equality.** Exact equality on one runtime is a *fingerprint*,
not a mathematical verification, and must not be presented as one. This
package contains a direct demonstration:

* the verification harness, building the sequence through its own path,
  yields `TP = 4.543052927725112`;
* the round-trip fixture in `test_fitts_selection_roundtrip.py` asserts the
  literal `4.543052927725114`;
* the two differ by `1.776e-15`, about two units in the last place.

Two independent constructions of one mathematical quantity legitimately
disagree in the last bits because the summations are ordered differently. The
portable claim is the tolerance-based agreement above, and the exact-float
assertion in the suite should be read as fixture-specific. Any value quoted
in a report should be given to a stated precision, not to 15-17 significant
digits.

## 6a. Why the delta column does not prove independence

A `0.000e+00` delta is **not** evidence that the oracle is independent of the
library. Two implementations that share a defect agree perfectly, and two that
were transcribed from one another agree perfectly. The table above shows the
numbers match; on its own it cannot show that they were produced by separate
reasoning.

`test_fitts_oracle_independence.py` therefore establishes independence
structurally, with three checks that are independent of one another:

| check | mechanism | what a failure would mean |
|---|---|---|
| `test_oracle_module_never_references_production_geometry` | AST walk of `_repro_numeric_check.py` for any `Name`, `Attribute` or import alias equal to `movement_geometry` | the oracle is not a second implementation |
| `test_corrupting_production_geometry_does_not_move_the_oracle` | monkeypatches `movement_geometry` to a deliberately wrong, non-degenerate return, then asserts the oracle's rebuilt `Ae` and `dx` are bit-identical | the oracle is reading the production helper |
| `test_the_same_mutation_does_move_the_library` | the identical mutation, asserting the library value *does* change | the mutation never bit, so the test above proves nothing |

The third check is the control that makes the second meaningful, and
`test_oracle_matches_library_on_unmutated_code` keeps the reported agreement
honest by re-asserting it on unmutated code.

Both sabotage tests were validated by canary: a delegation was temporarily
injected into the oracle via `getattr(_t, 'movement_' + 'geometry')`, which
the AST check cannot see, and the behavioural test caught it. The static check
was separately validated against `import movement_geometry as _mg`, an alias
form that its first draft missed. A guard that has never been shown to fail is
not evidence.

**Shared inputs.** The oracle and every harness and export build from one
declared seed and jitter, `SEED = 11` and `JITTER_PX = 0.0` in
`pc/experiment/tests/verify_fitts_28.py`. `_repro_endpoint.py` and
`_repro_export_evidence.py` now import those two constants rather than relying
on the generator defaults, so "same seed and jitter" is enforced by the import
instead of being an assumption that happens to hold. With `JITTER_PX = 0.0` the
seed does not move the layout, which is precisely why an explicit import is
needed to make the claim checkable.

## 7. Where the withdrawn text lives

The withdrawn sign argument remains in
`throughput-formula-proposal-alignment.md` section 8.1 for the audit trail,
and it is marked as superseded at both ends. Readers landing on that file are
pointed back to this page.

