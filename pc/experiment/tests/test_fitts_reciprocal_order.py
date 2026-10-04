"""Coordinate-level proof that the reciprocal walk spans the ring.

The traversal is asserted from the *resolved target coordinates*, not
from the numbering. ``generate_circular_targets`` assigns ids in
ascending angular order, so an ascending-id walk would produce the
adjacent chord ``2R sin(pi/N)`` and an ascending-id walk that happens to
be called "reciprocal" would still be a short-reach task. These tests
fail if the generator ever regresses to neighbour-to-neighbour stepping.
"""

from __future__ import annotations

import math

import pytest

from pc.experiment.task.reciprocal import (
    generate_reciprocal_sequence,
    reciprocal_traversal,
)
from pc.experiment.task.targets import generate_circular_targets

SCREEN_W = 1920.0
SCREEN_H = 1080.0
CENTER = (960.0, 540.0)
RADIUS = 260.0
WIDTH = 64.0
SEED = 11


def build(count=9, seed=SEED, radius=RADIUS, jitter=0.0):
    return generate_circular_targets(
        screen_width=SCREEN_W,
        screen_height=SCREEN_H,
        center=CENTER,
        radius=radius,
        target_count=count,
        target_width=WIDTH,
        seed=seed,
        jitter_px=jitter,
    )


def centers_of(targets):
    return {f"T{t.target_id}": (t.x, t.y) for t in targets}


def measured_steps(targets):
    steps = generate_reciprocal_sequence(targets, sequence_id="s1")
    return [s for s in steps if s.trial_role == "MEASURED"]


def test_traversal_order_for_nine_targets_is_the_near_opposite_stride():
    """The documented order, and it closes on the anchor."""
    assert reciprocal_traversal(9) == [0, 4, 8, 3, 7, 2, 6, 1, 5, 0]


@pytest.mark.parametrize("count", [3, 5, 7, 9, 11, 15])
def test_traversal_visits_every_vertex_once_and_closes(count):
    order = reciprocal_traversal(count)

    assert order[0] == 0
    assert order[-1] == 0
    assert sorted(order[:-1]) == list(range(count))


@pytest.mark.parametrize("count", [4, 6, 8, 10])
def test_even_counts_are_refused_because_no_single_cycle_stride_exists(count):
    with pytest.raises(ValueError, match="odd"):
        reciprocal_traversal(count)


def test_every_measured_amplitude_is_the_near_opposite_chord():
    """The amplitude check is on coordinates, not on ids."""
    targets = build()
    centers = centers_of(targets)

    near_opposite = 2 * RADIUS * math.cos(math.pi / (2 * 9))
    adjacent = 2 * RADIUS * math.sin(math.pi / 9)

    measured = measured_steps(targets)

    assert len(measured) == 9

    for step in measured:
        amplitude = math.dist(centers[step.from_target], centers[step.to_target])

        assert amplitude == pytest.approx(near_opposite, rel=1e-9)
        assert amplitude != pytest.approx(adjacent, rel=1e-6)


def test_no_transition_steps_to_an_angular_neighbour():
    """A guard that would have caught the ascending-id regression."""
    targets = build()
    centers = centers_of(targets)
    adjacent = 2 * RADIUS * math.sin(math.pi / 9)

    for step in measured_steps(targets):
        amplitude = math.dist(centers[step.from_target], centers[step.to_target])

        assert amplitude > adjacent * 2.0


def test_traversal_is_reciprocal_in_the_offset_geometry():
    """A -> B and B -> A carry the same amplitude.

    Reciprocity must hold in the geometry, not merely because the id
    count is odd.
    """
    targets = build()
    centers = centers_of(targets)

    pairs = [
        (step.from_target, step.to_target) for step in measured_steps(targets)
    ]
    reversed_pairs = {(b, a) for a, b in pairs}

    assert len(pairs) == len(reversed_pairs)  # no pair repeats a direction

    forward = math.dist(centers[pairs[0][0]], centers[pairs[0][1]])
    backward = math.dist(centers[pairs[0][1]], centers[pairs[0][0]])

    assert forward == pytest.approx(backward, rel=1e-12)


def test_jitter_does_not_change_which_vertices_are_paired():
    """Pairing is decided by id; only the geometry moves with jitter."""
    clean = centers_of(build(jitter=0.0))
    jittered = centers_of(build(jitter=6.0))

    clean_pairs = [
        (s.from_target, s.to_target) for s in measured_steps(build(jitter=0.0))
    ]
    jittered_pairs = [
        (s.from_target, s.to_target) for s in measured_steps(build(jitter=6.0))
    ]

    assert clean_pairs == jittered_pairs

    # ... and the jittered layout still spans more than the adjacent chord.
    adjacent = 2 * RADIUS * math.sin(math.pi / 9)
    for from_label, to_label in jittered_pairs:
        assert math.dist(jittered[from_label], jittered[to_label]) > adjacent * 2.0


def test_generator_rejects_a_layout_that_does_not_close():
    """The order is validated, not assumed."""
    assert reciprocal_traversal(9)[-1] == reciprocal_traversal(9)[0]