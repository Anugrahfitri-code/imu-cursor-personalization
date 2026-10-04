# Throughput Pipeline Audit (Stage 2.5)

**Status:** superseded in part — the amplitude and difficulty rules
were realigned to proposal section 5.13 on 2026-10-02
**Scope:** `pc/experiment/task/throughput.py`, `pc/experiment/task/outcome.py`,
`pc/experiment/task/selection.py`
**Explicitly out of scope:** L0 training, L0 qualification, the L2C
latent adapter, the session state machine, and the participant runner.

> **Correction, 2026-10-02.** The original audit concluded "no
> functional defect found" and cleared the amplitude rule below as
> **PASS**. That verdict was wrong: `Ae = dist(start, end)` and the
> per-movement difficulty both contradict proposal section 5.13, which
> mandates the serial correction and a sequence-level `ID_e`. Sections
> 1 and 2.1 have been rewritten. See
> `docs/decisions/throughput-formula-proposal-alignment.md`. Sections
> 2.2 onward (effective width, `We = 4.133`, sample SD, unit
> convention) were unaffected and still stand.

## 1. Final formula

Per sequence, over the measured movements only:

```
Ae   = mean(Ae_i)                          px
ID_e = log2(Ae / We + 1)                   bits
TP   = ID_e / (mean(MT_i) / 1000)          bits/second
```

With, per measured movement `i`:

```
a_i     = |centre(from_i) -> centre(to_i)|            px (layout)
offset_i = projection(cursor_end_i - centre_i,
                      unit(centre(from_i) -> centre_i))  px, SIGNED
Ae_1    = a_1 + offset_1
Ae_i    = a_i + offset_i + offset_{i-1}   for i > 1, offset_0 = 0
SDx     = sample_std(offset_i)                        px
We      = 4.133 * SDx                                 px (sequence level)
MT_i    = selection_time_i                            ms
```

`We` is computed **once per sequence** from all denominator offsets and
then shared by every movement in that sequence. This matches the
Crossman/Goodeve estimator, which pools endpoints within a condition
rather than fitting a width per movement.

## 2. Audit findings

### 2.1 Actual amplitude — DEFECT (corrected 2026-10-02)

The original code computed `Ae = dist(cursor_start, cursor_end)` and
`movement_geometry` derived the movement axis from the **cursor start**
rather than the layout. Both are wrong under proposal section 5.13,
which defines `a_i` as the from-target-centre to to-target-centre
distance and states that the serial correction "is used consistently
for the reciprocal serial task and is not a measure of
two-dimensional cursor path length".

Consequences of the original code:

* a **perpendicular** miss inflated the amplitude by the full lateral
  deviation, because a path length is orientation-blind;
* a cursor that failed to start exactly on the from-target centre
  changed the movement axis, so the same endpoint produced different
  offsets on different trials;
* the **miss carry-forward was double-counted** — a miss both lengthened
  the next movement as a path length *and* was meant to be corrected
  by the serial rule, which was absent entirely.

> **The "double-counted" wording above is withdrawn 2026-10-10.** The real
> defect it names is only the first half: substituting an orientation-blind
> path length for the axial amplitude. The serial rule was indeed absent, so
> nothing was in fact added twice, and in a reciprocating task the additive
> serial term *lengthens* the return movement rather than duplicating it.
> See `throughput-effective-amplitude.md` section 2. The correction listed
> below is unchanged and stands.

Corrections applied:

* `movement_geometry(record, from_center, to_center)` returns the
  nominal `a_i` and the axial offset `d_i`, both derived from the
  layout;
* `sequence_throughput()` applies `Ae_1 = a_1 + d_1` and
  `Ae_i = a_i + d_i + d_{i-1}`, with `d_0 = 0`, so the first measured
  movement never inherits the acquisition endpoint;
* `effective_width()` still sees only the axial offsets, so `We` is
  unchanged, and the target radius is still never read.

Regressions: `test_movement_geometry_amplitude_is_nominal_not_path_length`
pins that a 40px overshoot leaves `a` unchanged, and
`test_orthogonal_miss_leaves_amplitude_nominal_and_offset_zero` pins
that a 50px lateral miss is flagged as a miss without touching the
amplitude.

### 2.1b Per-movement difficulty — DEFECT (corrected 2026-10-02)

`IDe` was computed once per movement and then averaged. Section 5.13
defines difficulty once per sequence from the mean effective amplitude.
Because `log2` is concave, the two definitions disagree whenever the
effective amplitudes vary, and the per-movement mean is biased low.
`SequenceThroughput` now carries `mean_effective_amplitude_px` and
`index_of_difficulty_bits`. Regression:
`test_difficulty_is_sequence_level_not_mean_of_movements`.

### 2.2 Effective width — PASS

`EFFECTIVE_WIDTH_FACTOR = 4.133` (throughput.py:46) and
`standard_deviation` divides by **`count - 1`** (throughput.py:117),
i.e. the **sample** standard deviation, as the estimator requires.

For offsets `[+30, -30]`:

| variant | SDx | We |
| --- | --- | --- |
| sample (`n-1`) | `sqrt(1800/1)` = 42.42641 | 175.34834 |
| population (`n`) | `sqrt(1800/2)` = 30 | 123.99 |

The implementation returns **175.34834**. Using the population SD
would understate `We` by a factor of `sqrt(2)` (~29%), inflate every
`ID`, and therefore overstate throughput.

Regression: `test_effective_width_uses_sample_standard_deviation`
asserts both the sample value and the `sqrt(2)` ratio against the
population reading.

### 2.3 Endpoint correction — PASS

`offset` is a **signed** scalar projection of the endpoint error onto
the movement axis, which is now the **layout** axis from the from-target
centre to the to-target centre rather than the axis from the observed
cursor start. All four serial reciprocal patterns are preserved with
their sign:

| pattern | signed offset |
| --- | --- |
| overshoot | `+` |
| undershoot | `-` |
| overshoot-reverse | `+` (smaller) |
| undershoot-reverse | `-` (smaller) |

Taking `abs()` would be wrong twice over: it would double-count a
### 2.4 Movement time denominator — PASS

`measured_records` (selection.py:191) admits only records whose
`denominator_status == IN_DENOMINATOR`. Verified end-to-end on a
5-record sequence containing one of each edge case:

| record | status | in denominator |
| --- | --- | --- |
| initial acquisition | `EXCLUDED_INITIAL_ACQUISITION` | no |
| valid miss, 30px past centre | `IN_DENOMINATOR` | **yes** |
| valid miss, 30px short of centre | `IN_DENOMINATOR` | **yes** |
| ordinary hit | `IN_DENOMINATOR` | **yes** |
| movement with `MT = 0` | `EXCLUDED_INVALID_TIMESTAMP` | no |

So initial acquisition is out, technical failure is out, and a valid
miss is in — including in `We`, since a miss is real endpoint evidence
about the participant's spread and excluding it would bias `SDx`
downward.

Non-positive or non-finite movement times are additionally rejected at
throughput.py:238, and `sequence_throughput` raises `ValueError` when no
measured movement remains.

### 2.5 Unit audit — PASS

| quantity | unit | where enforced |
| --- | --- | --- |
| coordinate (`cursor_start`, `cursor_end`, centres) | display px, y-down | `_point` rejects non-finite values |
| `Ae`, `SDx`, `We`, `offset` | px | same space as coordinates |
| `selection_time_ms` | ms, integer | `_timestamp` (selection.py:39) |
| `MT`, `mean_movement_time_ms` | ms | carried through unchanged |
| `ID`, `mean_effective_id_bits` | bits (dimensionless ratio) | Shannon formulation |
| `throughput_bits_per_second` | bits/s | divides by `mean_movement_time_ms / 1000` |

The px and ms spaces are kept separate: no amplitude quantity is ever
combined with a time quantity, and the only `ms -> s` conversion in the
pipeline is the single divide in the throughput expression. The
`selection_time_unit_ms` flag on `sequence_throughput` exists to make
that convention explicit at the call site; it does not rescale values.

## 3. Edge cases

* **`SDx = 0` (identical endpoints).** Rejected by `effective_width`
  with `effective width must be positive`. Without this guard `We = 0`
  and `ID = log2(Ae/0)` would imply infinite throughput.
* **Fewer than two endpoints.** Rejected with `at least two movements
  are required to estimate the endpoint spread`. `N = 1` has no
  meaningful sample SD, since `n-1 = 0`.
* **A sequence of pure orthogonal misses.** Contributes `offset = 0` to
  `SDx`, so such a sequence still yields `SDx = 0` and is rejected. Note
  the asymmetry: an orthogonal miss **does** lengthen `Ae` (it is a 2-D
  distance) but contributes **nothing** to `We` (a 1-D axial measure).
  A participant who misses sideways while staying on the line is
  penalised in amplitude but not in width.
* **Unknown target label.** `sequence_throughput` raises
  `no target geometry for label ...`.
* **Empty denominator.** Raises `no measured movement`.
* **Constant overshoot (corrected 2026-10-02).** A participant who
  overshoots by the same amount on every movement has `SDx = 0`
  mathematically, but the endpoints still differ in the last float
  bits, so the original bare `width <= 0.0` test admitted a spread of
  about `1e-14` and produced a throughput in the tens of kilobits per
  second. `effective_width()` now also rejects any
  `sd <= SPREAD_TOLERANCE * max(|dx|)`.
* **Non-positive corrected amplitude (corrected 2026-10-02).** A large
  inherited undershoot can drive `a_i + dx_i + dx_{i-1}` to zero or
  below. `sequence_throughput` raises instead of logging through an
  undefined ratio. The guard was still needed after the 2026-10-10
  realignment, because the additive form can also subtract: a deep
  undershoot combined with a negative inherited offset goes negative
  far more easily than the old subtractive form did.
* **Broken measured run (corrected 2026-10-02).** The contiguity check
  lived only in `find_sequence_breaks()`, which every caller had to
  remember to call. It is now enforced inside `sequence_throughput`,
  so an incomplete sequence cannot be pooled by accident.

## 4. Test coverage added

In `pc/experiment/tests/test_fitts_throughput.py`:

* `test_effective_width_uses_sample_standard_deviation`
* `test_movement_geometry_amplitude_is_nominal_not_path_length`
* `test_orthogonal_miss_leaves_amplitude_nominal_and_offset_zero`
* `test_overshoot_and_undershoot_keep_their_sign`
* `test_effective_width_depends_on_spread_not_directional_bias`
* `test_serial_correction_carries_offset_into_next_movement`
* `test_serial_correction_sums_own_and_inherited_offsets`
  (renamed from `test_serial_correction_never_uses_its_own_offset` on
  2026-10-10, when the serial correction became additive)
* `test_serial_correction_never_inherits_the_acquisition_offset`
* `test_difficulty_is_sequence_level_not_mean_of_movements`
* `test_zero_effective_width_is_rejected_not_substituted`
* `test_incomplete_sequence_is_refused_before_pooling`
* `test_miss_endpoint_still_corrects_the_following_movement`

Each expected value is a hand-derived literal rather than a call into
the implementation, so a change in the estimator has to be a deliberate
edit here too.

symmetric spread and, worse, erase a directional bias. `We` is
driven by spread alone, so a participant who consistently overshoots by
a fixed amount keeps a small `SDx`.

Regression: `test_overshoot_and_undershoot_keep_their_sign` covers all
four patterns; `test_effective_width_depends_on_spread_not_directional_bias`
pins that a constant-offset set is rejected instead of silently
inflating `We`.

## 7. Amendment 2026-10-10: additive serial correction

The formula block above and `sequence_throughput()` were changed on
2026-10-10 from `Ae_i = a_i - offset_{i-1}` to the additive form frozen
in proposal section 5.13, `Ae_i = a_i + dx_i + dx_{i-1}` with `dx_0 = 0`.
`We = 4.133 * SDx` was not touched: it is estimated from the same signed
offsets and is unaffected by how those offsets enter `Ae_i`.

The full rationale, the replaced tests and the regenerated harness output
are recorded in `throughput-formula-proposal-alignment.md`, section 8,
which also carries the open sign-convention question for the PI.
