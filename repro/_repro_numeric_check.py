"""Independent numeric check of the substage 2.8 throughput snapshot.

This is deliberately NOT a copy of the production computation. It rebuilds
the sequence terms from first principles (closed-form Shannon arithmetic with
``math.log2``) and compares against the values produced by
``pc.experiment.tests.verify_fitts_28`` and
``pc.experiment.task.throughput``.

Two independent checks are performed for the headline numbers:

1. **Structural / algebraic check** -- the effective amplitudes are rebuilt
   from the printed geometry using the documented rule
   ``Ae_i = a_i + dx_i + dx_{i-1}`` (``dx_0 = 0``), then ``SDx``, ``We``,
   ``ID_e`` and ``TP`` are recomputed in closed form and required to match
   the library to within an absolute tolerance. This is a mathematical
   verification.
2. **Exact-float check** -- the library value is additionally printed next to
   the recorded reference literals so the reviewer can see whether the last
   bits moved. This is a *runtime fingerprint only*: it holds for CPython
   3.13 on this host and is not a mathematical statement. A different
   platform, Python build, or fused multiply-add behaviour may legitimately
   change the last bits, so check 1 is the one carrying the correctness claim.

Run with::

    python _repro_numeric_check.py

Exit code 0 means every algebraic check passed.
"""

from __future__ import annotations

import math
import statistics
import sys

from pc.experiment.task.throughput import sequence_throughput
from pc.experiment.tests import verify_fitts_28 as harness

# Absolute tolerances. These are floating-point budgets, not equality.
AE_ATOL = 1e-9
TP_ATOL = 1e-9

# Runtime fingerprint of the deterministic harness on CPython 3.13 / this host.
REFERENCE_MEAN_AE = 513.1000315663482
REFERENCE_TP = 4.54305292772511


def build_records_and_centers() -> tuple[list, dict, int]:
    """Rebuild the same deterministic sequence the harness prints."""
    targets = harness.generate_circular_targets(
        screen_width=harness.SCREEN_W,
        screen_height=harness.SCREEN_H,
        center=harness.CENTER,
        radius=harness.RING_RADIUS,
        target_count=harness.TARGET_COUNT,
        target_width=harness.TARGET_WIDTH,
        # Forward the harness seed/jitter explicitly. Omitting them falls
        # back to the generator default (seed 0), which silently builds a
        # *different* layout from the one the harness and package fixture
        # use, so the comparison would not be against the same data.
        seed=harness.SEED,
        jitter_px=harness.JITTER_PX,
    )
    centers, widths = harness.label_map(targets)
    centers["CENTER"] = harness.START_POINT
    widths["CENTER"] = harness.TARGET_WIDTH

    steps = harness.generate_reciprocal_sequence(targets, sequence_id="s1")
    measured_steps = [s for s in steps if s.trial_role == harness.MEASURED]

    # Same deterministic endpoint construction the harness uses.
    cursor_ends = [
        harness.endpoint_along(harness.START_POINT, centers[steps[0].to_target], 4.0)
    ]
    for step, offset in zip(measured_steps, harness.OFFSETS_PX):
        start = centers[step.from_target]
        stop = centers[step.to_target]
        cursor_ends.append(harness.endpoint_along(start, stop, offset))

    records = harness.log_sequence(
        steps,
        centers,
        widths,
        origin=harness.START_POINT,
        cursor_ends=cursor_ends,
        selection_times_ms=harness.SELECTION_TIMES_MS,
    )
    measured_transitions = len(measured_steps)
    return records, centers, measured_transitions


def geometry(record, from_xy, to_xy) -> tuple[float, float]:
    """Return ``(a_i, dx_i)`` from raw coordinates only.

    This is a deliberate re-derivation, not a call into
    ``pc.experiment.task.throughput.movement_geometry``. The oracle has to be
    independent of the code under test, otherwise a defect in the production
    helper is reproduced here and compared against itself. Only
    ``math.hypot`` and a dot product are used.

    * ``a_i`` -- centre-to-centre distance of the movement.
    * ``dx_i`` -- axial offset of the endpoint from the target centre,
      projected on the unit vector of the movement axis.
    """
    axis = (to_xy[0] - from_xy[0], to_xy[1] - from_xy[1])
    nominal = math.hypot(axis[0], axis[1])
    if nominal == 0.0:
        raise ValueError("degenerate movement axis in the fixture")

    unit = (axis[0] / nominal, axis[1] / nominal)
    endpoint = (record.endpoint_x, record.endpoint_y)
    offset = (
        (endpoint[0] - to_xy[0]) * unit[0] + (endpoint[1] - to_xy[1]) * unit[1]
    )

    return nominal, offset


def independent_terms(records, centers) -> tuple[list[float], list[float]]:
    """Return (a_i, dx_i) rebuilt from geometry, independently of the library."""
    amplitudes: list[float] = []
    offsets: list[float] = []
    for record in records:
        if record.trial_role != "MEASURED":
            continue
        nominal, offset = geometry(
            record,
            centers[record.from_target],
            centers[record.to_target],
        )
        amplitudes.append(nominal)
        offsets.append(offset)
    return amplitudes, offsets


def exact_projection_terms(records, centers):
    """Endpoint-to-endpoint displacement projection ``G_i``.

    ``G_i = dot(E_i - S_i, u_i)`` projects the displacement between the two
    endpoints of the movement itself -- ``S_i`` the cursor start and ``E_i`` the
    cursor end -- onto the current movement axis ``u_i``. It is a *projection*,
    not a travelled path length: the path taken between those two endpoints is
    never measured, only the net displacement along the axis.

    The same expression is used for every movement, including the first. For
    the first measured movement ``S_1`` is the acquisition endpoint, so ``G_1``
    is a genuine endpoint-to-endpoint displacement rather than ``a_1 + dx_1``,
    which would silently drop the acquisition offset and report the
    from-centre-to-endpoint projection instead.

    ``previous_axis`` is consulted *only* to decide whether an inter-axis
    turning angle is available; it never influences ``G_i``. This is *not* the
    estimator the study uses: the adopted estimator keeps ``dx_0 = 0`` and its
    own serial form, and is checked separately below.
    """
    measured = [r for r in records if r.trial_role == "MEASURED"]
    previous_axis = None
    g_values = []
    angles = []
    for index, record in enumerate(measured):
        f_i = centers[record.from_target]
        t_i = centers[record.to_target]
        axis = (t_i[0] - f_i[0], t_i[1] - f_i[1])
        length = math.hypot(axis[0], axis[1])
        u_i = (axis[0] / length, axis[1] / length)
        # Displacement between this movement's own two endpoints, projected on
        # its own axis. Identical expression for every movement; the first is
        # no longer special-cased.
        g_values.append(
            (record.cursor_end[0] - record.cursor_start[0]) * u_i[0]
            + (record.cursor_end[1] - record.cursor_start[1]) * u_i[1]
        )
        if previous_axis is not None:
            # Only the inter-axis turning angle needs an earlier axis.
            dot = previous_axis[0] * u_i[0] + previous_axis[1] * u_i[1]
            angles.append(math.degrees(math.acos(max(-1.0, min(1.0, dot)))))
        previous_axis = u_i
    return g_values, angles


def independent_aggregate(ae_values: list[float], offsets: list[float],
                          mt_values: list[float]) -> dict[str, float]:
    """Closed-form Shannon throughput from rebuilt terms."""
    mean_ae = sum(ae_values) / len(ae_values)
    sd_x = statistics.stdev(offsets)
    we = 4.133 * sd_x
    id_e = math.log2(mean_ae / we + 1.0)
    mean_mt = sum(mt_values) / len(mt_values)
    tp = id_e / (mean_mt / 1000.0)
    return {
        "mean_ae": mean_ae,
        "sd_x": sd_x,
        "we": we,
        "id_e": id_e,
        "mean_mt": mean_mt,
        "tp": tp,
    }


def main() -> int:
    records, centers, measured_transitions = build_records_and_centers()
    result = sequence_throughput(
        records,
        centers,
        sequence_id="s1",
        expected_measured_transitions=measured_transitions,
    )

    amplitudes, offsets = independent_terms(records, centers)
    mt_values = [r.selection_time_ms for r in records if r.trial_role == "MEASURED"]

    # Rebuild Ae by the documented additive rule, from scratch.
    rebuilt_ae = []
    previous = 0.0
    for a, dx in zip(amplitudes, offsets):
        rebuilt_ae.append(a + dx + previous)
        previous = dx
    assert len(rebuilt_ae) == len(offsets) == len(mt_values), "term count drift"

    mine = independent_aggregate(rebuilt_ae, offsets, mt_values)

    print("=" * 78)
    print("INDEPENDENT NUMERIC CHECK -- substage 2.8")
    print("=" * 78)
    print("\n[A] PER-TRIAL REBUILD (a_i, dx_i, Ae_i from the additive rule)")
    print(f"{'trial':>5} {'a_i':>12} {'dx_i':>10} {'dx_i-1':>10} {'Ae_i':>14}")
    previous = 0.0
    for index, (a, dx, ae) in enumerate(zip(amplitudes, offsets, rebuilt_ae), start=1):
        print(f"{index:>5} {a:>12.6f} {dx:>10.3f} {previous:>10.3f} {ae:>14.6f}")
        previous = dx

    print("\n[B] ALGEBRAIC AGREEMENT (library vs independent closed form)")
    failures: list[str] = []
    pairs = [
        ("mean Ae", result.mean_effective_amplitude_px, mine["mean_ae"], AE_ATOL),
        ("SDx", result.endpoint_offset_sd_px, mine["sd_x"], AE_ATOL),
        ("We", result.effective_width_px, mine["we"], AE_ATOL),
        ("ID_e", result.index_of_difficulty_bits, mine["id_e"], TP_ATOL),
        ("mean MT", result.mean_movement_time_ms, mine["mean_mt"], AE_ATOL),
        ("TP", result.throughput_bits_per_second, mine["tp"], TP_ATOL),
    ]
    for name, got, want, atol in pairs:
        delta = abs(got - want)
        ok = delta <= atol
        print(f"  {name:<8} library={got!r:<22} independent={want!r:<22} "
              f"|delta|={delta:.3e} atol={atol:.0e} {'OK' if ok else 'FAIL'}")
        if not ok:
            failures.append(name)

    print("\n[C] RUNTIME FLOAT FINGERPRINT (informational, not a math claim)")
    print(f"  mean Ae library = {result.mean_effective_amplitude_px!r}")
    print(f"  mean Ae recorded= {REFERENCE_MEAN_AE!r}")
    print(f"  TP     library = {result.throughput_bits_per_second!r}")
    print(f"  TP     recorded= {REFERENCE_TP!r}")
    print(f"  mean Ae exact match = {result.mean_effective_amplitude_px == REFERENCE_MEAN_AE}")
    print(f"  TP     exact match = {result.throughput_bits_per_second == REFERENCE_TP}")
    print("  Note: exact float equality on one runtime is a fingerprint only;")
    print("        section [B] carries the mathematical verification.")
    reference_alt = 4.543052927725114
    print(f"\n  Cross-fixture float spread: this harness = "
          f"{result.throughput_bits_per_second!r}")
    print(f"  round-trip test literal    = {reference_alt!r}")
    print(f"  absolute difference        = "
          f"{abs(result.throughput_bits_per_second - reference_alt):.3e}")
    print("  Two independent constructions of the same quantity differ by a few")
    print("  units in the last place. That is why the exact-float assertion in")
    print("  the test suite is a fixture fingerprint, and the tolerance-based")
    print("  assertion beside it is the portable statement.")

    print("\n" + "=" * 78)
    if failures:
        print(f"RESULT: FAIL ({', '.join(failures)})")
        return 1
    print("RESULT: PASS (all algebraic checks within tolerance)")
    print("=" * 78)

    print("\n[D] ADOPTED ESTIMATOR vs ENDPOINT-TO-ENDPOINT PROJECTION")
    print("  Informational. The study uses the axial serial estimator")
    print("  Ae_i = a_i + dx_i + dx_{i-1}. The displacement projection is")
    print("  G_i  = a_i + dx_i - dot(P_{i-1} - F_i, u_i).")
    print("  They coincide only when the previous movement axis is exactly")
    print("  anti-parallel to the current one (1D reciprocation on one line).")
    g_values, angles = exact_projection_terms(records, centers)
    print(f"\n  {'trial':>5} {'Ae_i (adopted)':>16} {'G_i (projection)':>17} {'G_i - Ae_i':>12}")
    max_gap = 0.0
    for index, (ae, g) in enumerate(zip(rebuilt_ae, g_values), start=1):
        gap = g - ae
        max_gap = max(max_gap, abs(gap))
        print(f"  {index:>5} {ae:>16.6f} {g:>16.6f} {gap:>12.6f}")
    mean_ae = sum(rebuilt_ae) / len(rebuilt_ae)
    mean_g = sum(g_values) / len(g_values)
    print(f"\n  mean Ae_i = {mean_ae!r}")
    print(f"  mean G_i  = {mean_g!r}")
    print(f"  largest per-trial gap = {max_gap:.6f} px")
    if angles:
        print(f"  angle between consecutive movement axes: "
              f"min {min(angles):.2f} deg, max {max(angles):.2f} deg")
        print("  (180 deg would be pure 1D reciprocation, where the two")
        print("   estimators agree exactly.)")
    print("\n  Interpretation: the adopted estimator is NOT the endpoint-to-endpoint")
    print("  displacement projection, and neither quantity is a measured path")
    print("  length. On this ring layout the movement axes turn, so the two")
    print("  genuinely differ. Report this as a bound on interpretation, not")
    print("  as an error.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())

