# Fitts Task Design: Reciprocal Pointing and Throughput

**Status:** accepted (stage 2.11)
**Scope:** target geometry, sequence shape, trial logging, throughput
**Explicitly out of scope:** L0 training, L0 qualification, the L2C
latent adapter, and the session state machine. None of those are
imported or modified by this work.

## 1. Target geometry

The layout is a **regular polygon inscribed in a circle** of radius
`radius`, centred on `center`, with one vertex anchored on the
reference axis (top of the display, `-pi / 2`).

Each target stores exactly four fields:

| field | meaning |
| --- | --- |
| `target_id` | `0 .. target_count - 1`; `0` is the anchor |
| `x`, `y` | centre in display pixels |
| `width` | target width in pixels (equal to the diameter) |

Two geometric guards are enforced before a layout is accepted:

* **No overlap.** The chord between adjacent vertices,
  `2 * radius * sin(pi / target_count)`, must exceed
  `target_width + 2 * jitter_px`. Otherwise a point between two
  targets would have an ambiguous hit classification.
* **Fully on screen.** `radius + width / 2 + jitter_px` must fit
  within the display on all four sides.

### Determinism

`seed` is the only source of variation, and it is the sole determinant
of the layout rotation. The same arguments and the same seed always
reproduce an identical layout, so a task configuration is replayable
and a session can be regenerated exactly. With the default `seed = 0`
and `jitter_px = 0.0` the polygon is perfectly regular.

## 2. Why the target count must be odd

An odd count is a **structural requirement**, not a stylistic
preference:

1. **A single anchor.** An odd polygon puts exactly one vertex on the
   reference axis. An even count would place a *pair* of mirror-image
   targets on the axis, leaving no unambiguous anchor for the initial
   acquisition and no symmetric choice for the closing transition.
2. **The loop closes with odd symmetry.** The reciprocal sequence
   traverses the ring and returns to the anchor, which takes exactly
   `target_count` measured transitions. With an odd count the traversal
   is symmetric about the reference axis; with an even count the ring
   would fall into two disconnected halves under the alternating walk.

`generate_circular_targets` rejects even counts with
`target_count must be odd`.

### Deviation from the frozen ring walk (deliberate)

`task/sequence.py` (stage 2.8, frozen) enforces
`target_count == measured_transitions + 1` and explicitly states the
walk "never revisits its starting target". **That invariant is not
reused here.** A reciprocal task must be able to return to its anchor,
so this layout uses:

```
target_count == measured_transitions      (9 == 9)
```

The stage 2.8 module is left byte-for-byte unchanged;
`generate_reciprocal_sequence` validates against its own invariant.

**Traversal: every measured movement spans the ring.** An earlier
revision of this note walked the ring in ascending target id. Because
`generate_circular_targets` assigns ids in ascending angular order,
that walk is a *neighbour-to-neighbour* step: for 9 targets at radius
260 it measures `2R sin(pi/9) = 177.850px` on every movement, which
manipulates `We` of order 40px and yields an index of difficulty near
0. It is a legal pointing task but not a reciprocal one, and it says
more about the layout than about the participant.

The walk now uses the fixed stride `(N - 1) / 2`, so every measured
movement spans the near-opposite chord `2R cos(pi / (2N))`. For
`N = 9` that is `2R cos(pi/18) = 512.100px`, and the order is

    0 -> 4 -> 8 -> 3 -> 7 -> 2 -> 6 -> 1 -> 5 -> 0

`gcd((N - 1)/2, N) == 1` for every odd `N`, so the stride is a single
cycle: each vertex is reached exactly once before the anchor closes
the loop. `reciprocal_traversal()` in `pc/experiment/task/reciprocal.py`
returns that order, and
`pc/experiment/tests/test_fitts_reciprocal_order.py` asserts the
amplitudes **from the resolved coordinates**, so the claim cannot be
satisfied by renumbering alone.

Measured on the harness fixture: `SDx = 10.154364px`,
`We = 41.967987px`, `mean Ae = 513.100032px`, `ID_e = 3.725303 bits`,
`MT = 820ms`, `TP = 4.543053 bits/s`.

Note also
that the stage 2.8 docstring at `sequence.py` claims `target_count`
"must be odd" while its code forces `measured + 1`, which is always
even — an existing documentation inconsistency, left untouched and
flagged rather than silently repaired.

## 3. Initial acquisition handling

The sequence is:

```
initial acquisition:  center -> target_0     (recorded, NOT in MT)
measured:             target_0 -> target_4
                      target_4 -> target_8
                      ...
                      target_5 -> target_0   (closing transition)
```

That is 10 steps: **1 initial acquisition + 9 measured transitions**.

The acquisition is **recorded with the same fidelity as any measured
trial** — endpoint, hit flag, movement time — so the trial log is a
faithful account of what happened. It is tagged
`INITIAL_ACQUISITION` and assigned the denominator status
`EXCLUDED_INITIAL_ACQUISITION`.

`measured_records()` is the only supported way to build a
denominator, so the acquisition **cannot leak into movement time by
construction** rather than by caller discipline. Its endpoint *is* used:
it seeds the first measured movement's origin.

## 4. Miss handling

* **A miss is a real observation and is never discarded.**
  `measured_records()` keeps it. Dropping misses would preferentially
  delete the slowest, most errorful movements and inflate throughput
  — a systematic bias, not a cleaning step.
* Every record carries `hit`, `miss`, and the real `endpoint_x` /
  `endpoint_y`. A miss therefore still contributes its amplitude,
  offset, and movement time to the aggregate.
* The hit rule matches the frozen stage 2.8 classifier: a selection is
  a hit iff
  `dist(endpoint, target_centre) <= target_width / 2`.

## 5. Endpoint correction (no teleport)

This is the invariant the logging layer exists to enforce.

`SequenceStep` records only the **intended** target labels. It stores
no cursor position at all. `SelectionRecord` records what
**physically happened**: the real `cursor_start` and `cursor_end`.

`log_sequence` threads the previous trial's observed endpoint into the
next trial's origin:

```python
record = build_selection_record(step, cursor_start=current, ...)
current = record.cursor_end        # never reassigned to a target centre
```

After a miss the next movement therefore **begins where the cursor
physically stopped**, outside the target. The recorded endpoint and the
recorded origin are both preserved, and the miss offset that caused
them feeds the serial correction of the following movement. There is
deliberately **no** `reset_to_target()` or `teleport()` helper anywhere
in the module.

A practical consequence: a miss is carried forward rather than erased.
Its signed offset enters `Ae_{i+1} = a_{i+1} + dx_{i+1} + dx_i`, so the next
movement is widened by exactly the overshoot that produced the miss. This
is the serial correction of section 6, as frozen in the proposal, and it
is the declared representation of recovery cost.

## 6. Throughput formula

The Shannon formulation of Fitts' law, computed at the **sequence**
level, using the effective-width estimator rather than the nominal
diameter.

This section was **realigned to proposal section 5.13**
("Definisi Operasional Throughput") on 2026-10-02. The previous text
in this section specified `Ae_i = dist(start_i, end_i)` and a
per-movement difficulty; both contradicted the locked proposal. See
`docs/decisions/throughput-formula-proposal-alignment.md` for the
quoted text and the rationale.

**Step 1 — nominal amplitude**

```
a_i = dist(centre(from_i), centre(to_i))
```

The centre-to-centre distance of the layout. It does **not** depend on
where the cursor actually started or ended. A measured 2-D path
length is never substituted here.

**Step 2 — endpoint offset**

```
dx_i = dot(end_i - centre_i, unit(centre(from_i) -> centre_i))
```

The signed offset of the endpoint against the to-target centre,
projected onto the from-to movement axis. Positive is an overshoot,
negative an undershoot, and zero means the endpoint projects exactly
onto the target centre. A purely orthogonal miss gives `dx_i ~= 0`.

**Step 3 — effective amplitude (serial correction)**

```
Ae_1 = a_1 + dx_1
Ae_i = a_i + dx_i + dx_{i-1}     for i > 1, with dx_0 = 0
```

Every measured movement adds its own endpoint offset, and every
movement after the first also adds the offset inherited from its
predecessor. The first measured movement therefore corrects against its
own offset only: `dx_0` is zero by definition, because the initial
acquisition is not a measured transition and its endpoint must never
become an inherited offset. A valid miss is corrected exactly like a
hit, because a miss still moves and still consumes a target.

This is the frozen text of proposal section 5.13 and it is applied
verbatim, for every movement, without exception. The inherited term is
also the reason the correction can be negative in aggregate: a deep
undershoot followed by another undershoot is a movement of genuinely
reduced amplitude.

**Step 4 — effective width**

```
We = 4.133 * SDx
```

where `SDx` is the **sample** standard deviation (denominator `n - 1`)
of the signed offsets `dx_i` over the sequence, including valid misses.
`4.133` is frozen as `EFFECTIVE_WIDTH_FACTOR`.

**Step 5 — effective difficulty, once per sequence**

```
Ae   = mean(Ae_i)
ID_e = log2(Ae / We + 1)
```

**Step 6 — throughput**

```
TP = ID_e / mean(MT)         [bits per second, MT in seconds]
```

The initial acquisition is excluded from `mean(MT)`, though its
endpoint is retained for audit.


### Guard rails

* **A zero effective width is rejected, never reported as infinity and
  never substituted.** Identical endpoints give `SDx = 0` and `We = 0`,
  which would make `ID_e` infinite. Proposal section 5.13 forbids
  replacing the value ad hoc, so `effective_width()` raises and the
  sequence is flagged for audit. Because a *constant* overshoot is the
  physical case where `SDx` is exactly zero but still differs in the
  last float bits, the guard also rejects any spread below
  `SPREAD_TOLERANCE * max(|dx|)`.
* **Fewer than two measured movements raises**, because a single
  observation carries no spread information.
* **A zero-amplitude movement raises**, since the movement axis is
  undefined when the from-target and to-target centres coincide.
* **A non-positive corrected amplitude raises.** A deep undershoot can
  drive `a_i + dx_i + dx_{i-1}` to zero or below, which is not an
  analysable sequence.
* **A gap in the measured `trial_index` run stops the computation.**
  `sequence_throughput()` raises rather than pooling across the gap, so
  callers cannot forget to run `find_sequence_breaks()`. Pooling
  movements across a missing trial would average over two independent
  blocks and misstate both the effective width and the mean movement
  time.

## 7. Unit convention

| quantity | unit | note |
| --- | --- | --- |
| target position, radius, width | pixels (float) | `float`, never `int` |
| nominal amplitude `a` | pixels | centre-to-centre distance of the layout |
| endpoint offset `dx` | pixels | signed, projected on the movement axis |
| effective amplitude `Ae` | pixels | `a_1 + dx_1`, then `a_i + dx_i + dx_{i-1}` |
| effective width `We` | pixels | `4.133 * SDx` |
| movement time `MT` | milliseconds | recorded on the record |
| difficulty `ID_e` | bits | `log2(mean(Ae)/We + 1)`, once per sequence |
| **throughput `TP`** | **bits / second** | `MT` converted ms -> s at the aggregate |

Mixed units are converted exactly once, at the final division, so
there is no double conversion. `ID_e` is a pure ratio of two lengths
and is therefore dimensionless.

## 8. Test coverage

`pc/experiment/tests/test_fitts_throughput.py` — 38 tests, all with
expected values derived by hand from the formulas above and written as
explicit literals (not produced by the code under test):

| # | case | assertion |
| --- | --- | --- |
| 1 | center hit | zero offset; one-step chord amplitude |
| 2 | undershoot | negative offset; still a hit inside tolerance |
| 3 | overshoot | positive offset |
| 4 | orthogonal miss | `dx ~= 0`, miss, amplitude still the chord |
| 4b | amplitude is not path length | `a` unchanged by a 40px overshoot |
| 5 | serial overshoot reverse | all offsets positive |
| 6 | serial undershoot reverse | all offsets negative |
| 7 | valid miss | retained in denominator; endpoint preserved |
| 7b | miss does not teleport | next `cursor_start` == miss endpoint |
| 7c | miss feeds `Ae_{i+1}` | next amplitude carries the miss offset |
| 8 | invalid timestamp | `0.0` and `None` excluded from denominator |
| 8b | initial acquisition | recorded in full, excluded from MT |
| 9 | missing trial | `trial_index` gap reported as a break |
| 9b | incomplete sequence | `sequence_throughput()` refuses to pool |
| 10 | We not zero | `We = 12.399` from `SDx = 3`; zero `We` raises |
| 10b | constant overshoot | `SDx ~ 0` from float noise still raises |
| 11 | serial correction | `Ae_1 = a + dx_1`, `Ae_i = a_i + dx_i + dx_{i-1}` |
| 11b | own-and-inherited terms | `Ae_2` adds both `dx_2` and `dx_1` |
| 11c | `dx_0 = 0` | the acquisition endpoint never becomes `dx_0` |
| 12 | sequence-level ID | `ID_e` != mean of per-movement difficulties |

The hand-computed throughput fixture uses signed offsets
`[-6, 0, 0, 0, 0, 0, 0, 0, 6]`, whose sample `SDx` is exactly `3`,
so `We = 4.133 * 3 = 12.399` exactly. Under the serial correction that
fixture gives `Ae_1 = a - 6`, `Ae_2 = a - 6`, `Ae_3..Ae_8 = a` and
`Ae_9 = a + 6`, so the mean effective amplitude is `a - 6/9` and not
the nominal chord `a`.

