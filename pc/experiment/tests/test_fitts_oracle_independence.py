"""The geometry oracle must be independent of the production helper.

A zero difference between the library and the closed-form oracle is *not*
by itself evidence of independence: two different implementations can
coincidentally agree, and a shared bug can cancel out. These tests prove
independence structurally, by perturbing the production
``movement_geometry`` and observing that the oracle is unaffected.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
# The oracle script sits at the repository root in the working tree, but the
# review package stores it one level down under ``code/repro/`` so that the
# packaged tree keeps only the code it describes. Probe both layouts instead of
# assuming one, so this file is collectable unchanged in either.
for _candidate in (_ROOT, _ROOT / "repro"):
    if (_candidate / "_repro_numeric_check.py").is_file():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break

import _repro_numeric_check as oracle  # noqa: E402
from pc.experiment.task import throughput as production  # noqa: E402


def _oracle_effective_amplitudes():
    """Rebuild Ae_i = a_i + dx_i + dx_{i-1} from the oracle's own terms."""
    records, centers, _ = oracle.build_records_and_centers()
    amplitudes, offsets = oracle.independent_terms(records, centers)
    rebuilt, previous = [], 0.0
    for a, dx in zip(amplitudes, offsets):
        rebuilt.append(a + dx + previous)
        previous = dx
    return rebuilt, offsets


def _oracle_mean_ae():
    rebuilt, _ = _oracle_effective_amplitudes()
    return sum(rebuilt) / len(rebuilt)


def _library_mean_ae():
    records, centers, measured = oracle.build_records_and_centers()
    return production.sequence_throughput(
        records,
        centers,
        sequence_id="s1",
        expected_measured_transitions=measured,
    ).mean_effective_amplitude_px


def _sabotaged(record, from_xy, to_xy, *_args, **_kwargs):
    """A wrong-but-non-degeometry, so We stays finite and the call survives."""
    return (1234.0, float(getattr(record, "trial_index", 0)) + 0.5)


def test_oracle_module_never_references_production_geometry():
    """Static proof: no executable reference to the production helper.

    Checks import *aliases* too, so ``import movement_geometry as mg``
    cannot slip past.
    """
    tree = ast.parse(Path(oracle.__file__).read_text(encoding="utf-8"))

    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                referenced.add(alias.name)
                if alias.asname:
                    referenced.add(alias.asname)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                referenced.add(alias.name)
                if alias.asname:
                    referenced.add(alias.asname)

    assert "movement_geometry" not in referenced


def test_corrupting_production_geometry_does_not_move_the_oracle(monkeypatch):
    """Mutation proof: the oracle survives a sabotaged production helper."""
    before = _oracle_effective_amplitudes()

    monkeypatch.setattr(production, "movement_geometry", _sabotaged)

    assert _oracle_effective_amplitudes() == before


def test_the_same_mutation_does_move_the_library(monkeypatch):
    """Control: the mutation bites, so the oracle result means something."""
    original = _library_mean_ae()

    monkeypatch.setattr(production, "movement_geometry", _sabotaged)

    assert _library_mean_ae() != original


def test_oracle_matches_library_on_unmutated_code():
    """The agreement the audit reports is real, not an artefact."""
    _, oracle_offsets = _oracle_effective_amplitudes()
    oracle_mean = _oracle_mean_ae()
    library_mean = _library_mean_ae()

    assert oracle_mean == pytest.approx(library_mean, abs=oracle.AE_ATOL)

    records, centers, _ = oracle.build_records_and_centers()
    library_offsets = [
        production.movement_geometry(
            record,
            centers[record.from_target],
            centers[record.to_target],
        )[1]
        for record in records
        if record.trial_role == "MEASURED"
    ]
    assert oracle_offsets == pytest.approx(library_offsets, abs=oracle.AE_ATOL)


# --- G_1 : the first measured movement, checked against raw coordinates ----
#
# Tolerance is absolute and stated in pixels. 1e-9 px is the same threshold
# the oracle already uses for Ae/TP agreement (oracle.AE_ATOL); the values
# below are ~500 px, so 1e-9 px is a relative slack of ~2e-12 -- far tighter
# than double-precision noise on this arithmetic, and far tighter than any
# disagreement this test is meant to catch.

G1_EXPECTED_PX = 517.7145657026941
MEAN_G_EXPECTED_PX = 513.4346382712598
G_ATOL_PX = 1e-9


def _raw_axis_projection(record, from_xy, to_xy):
    """Project the movement's own endpoints on its own axis, from raw xy.

    Deliberately written out longhand and independently of the oracle so the
    test does not compare the oracle against itself: this is the same scalar
    product the Fitts' law ID term uses, read straight off the coordinates.
    """
    dx_px = to_xy[0] - from_xy[0]
    dy_px = to_xy[1] - from_xy[1]
    a_px = (dx_px * dx_px + dy_px * dy_px) ** 0.5
    u_x = dx_px / a_px
    u_y = dy_px / a_px
    return (
        (record.cursor_end[0] - record.cursor_start[0]) * u_x
        + (record.cursor_end[1] - record.cursor_start[1]) * u_y
    )


def test_first_movement_projection_uses_the_acquisition_endpoint():
    """G_1 is the raw cursor_start -> cursor_end projection, not a_1 + dx_1.

    The earlier code special-cased the first movement and reported
    ``a_1 + dx_1`` = 514.1000315663482 px, which drops the acquisition offset
    and silently becomes the from-centre-to-endpoint projection. This test
    pins the corrected value and states the tolerance.
    """
    records, centers, _ = oracle.build_records_and_centers()
    measured = [r for r in records if r.trial_role == "MEASURED"]
    g_values, _ = oracle.exact_projection_terms(records, centers)

    first = measured[0]
    raw = _raw_axis_projection(
        first, centers[first.from_target], centers[first.to_target]
    )

    # The raw-coordinate computation is the reference.
    assert g_values[0] == pytest.approx(raw, abs=G_ATOL_PX)
    assert g_values[0] == pytest.approx(G1_EXPECTED_PX, abs=G_ATOL_PX)

    # The superseded a_1 + dx_1 value is genuinely different, so this test is
    # not vacuous: it would fail if the special case were reinstated.
    a_1 = (
        (centers[first.to_target][0] - centers[first.from_target][0]) ** 2
        + (centers[first.to_target][1] - centers[first.from_target][1]) ** 2
    ) ** 0.5
    _, dx_1 = oracle.geometry(
        first, centers[first.from_target], centers[first.to_target]
    )
    assert g_values[0] != pytest.approx(a_1 + dx_1, abs=G_ATOL_PX)

    # G_1 must actually span the acquisition endpoint, i.e. its cursor_start is
    # the acquisition endpoint and not the from-target centre.
    assert first.cursor_start != pytest.approx(centers[first.from_target], abs=G_ATOL_PX)


def test_mean_displacement_projection_matches_the_documented_value():
    """Mean G over the seed-11 fixture is pinned, same absolute tolerance."""
    records, centers, _ = oracle.build_records_and_centers()
    g_values, angles = oracle.exact_projection_terms(records, centers)

    assert sum(g_values) / len(g_values) == pytest.approx(
        MEAN_G_EXPECTED_PX, abs=G_ATOL_PX
    )
    # One turning angle per inter-axis pair; the first movement has none.
    assert len(angles) == len(g_values) - 1


def test_projection_change_leaves_the_adopted_estimator_untouched():
    """The G fix is diagnostic only: dx_0 = 0, Ae and TP are unchanged."""
    records, centers, measured_transitions = oracle.build_records_and_centers()
    result = production.sequence_throughput(
        records,
        centers,
        sequence_id="s1",
        expected_measured_transitions=measured_transitions,
    )

    # "dx_0 = 0" is the *inherited* offset in the serial recurrence: the first
    # measured movement adds its own dx_1 but inherits nothing from before it.
    # Its own endpoint offset is legitimately non-zero (2.0 px here).
    first_term = result.terms[0]
    assert first_term.effective_amplitude_px == pytest.approx(
        first_term.nominal_amplitude_px + first_term.endpoint_offset_px,
        abs=oracle.AE_ATOL,
    )
    # Every later movement must inherit the previous movement's offset, which
    # is what distinguishes the estimator from the G projection.
    assert result.terms[1].effective_amplitude_px == pytest.approx(
        result.terms[1].nominal_amplitude_px
        + result.terms[1].endpoint_offset_px
        + first_term.endpoint_offset_px,
        abs=oracle.AE_ATOL,
    )
    assert result.mean_effective_amplitude_px == pytest.approx(
        513.1000315663482, abs=oracle.AE_ATOL
    )
    assert result.throughput_bits_per_second == pytest.approx(
        4.543052927725114, abs=oracle.TP_ATOL
    )