"""The frozen condition chain and session termination behaviour."""

import pytest

from pc.experiment.session import (
    CONDITION_ORDER,
    CONDITION_STATES,
    SESSION_TIME_CAP_NS,
    SessionMachine,
    validate_order_reachable,
)


def _machine(**overrides):
    params = {
        "session_id": "S-TEST",
        "participant_id": "P-TEST",
        "condition_order": ["P0", "P2C", "L0", "L2C"],
    }
    params.update(overrides)
    return SessionMachine(**params)


def test_condition_order_is_the_frozen_chain():
    assert CONDITION_ORDER == (
        "CONDITION_P0",
        "CONDITION_P2C",
        "CONDITION_L0",
        "CONDITION_L2C",
    )

    # The unordered set and the ordered tuple must not drift apart.
    assert set(CONDITION_ORDER) == set(CONDITION_STATES)


@pytest.mark.parametrize(
    "order",
    [
        ["P0", "P2C", "L0", "L2C"],
        ["P0", "P2C", "L0"],
        ["P0", "L0", "L2C"],
        ["P2C", "L0", "L2C"],
        ["P0"],
        ["L2C"],
        [],
    ],
)
def test_counterbalancing_may_skip_but_not_reorder(order):
    validate_order_reachable(order)


@pytest.mark.parametrize(
    "order",
    [
        ["L0", "P0"],
        ["P2C", "P0"],
        ["L2C", "P0", "L2C"],
        ["P0", "L0", "P2C"],
        ["P0", "P0", "L0"],
        ["P0", "NOT_A_CONDITION"],
    ],
)
def test_reordered_or_repeated_orders_are_rejected(order):
    with pytest.raises(ValueError):
        validate_order_reachable(order)


def test_machine_rejects_reordered_condition_order_at_construction():
    with pytest.raises(ValueError):
        _machine(condition_order=["L0", "P0"])


def test_machine_accepts_skipped_condition_order():
    machine = _machine(condition_order=["P0", "L0", "L2C"])
    assert machine.condition_order == ["P0", "L0", "L2C"]


def test_machine_requires_identity_fields():
    with pytest.raises(ValueError):
        _machine(session_id="")

    with pytest.raises(ValueError):
        _machine(participant_id="")


def test_time_cap_blocks_further_work():
    machine = _machine()
    machine.transition("INITIALIZATION")
    machine.advance_to(SESSION_TIME_CAP_NS)

    with pytest.raises(RuntimeError):
        machine.transition("CALIBRATION_2C")

    machine.stop_session("TIME_CAP_REACHED")

    assert machine.stopped
    assert machine.stop_reason == "TIME_CAP_REACHED"

    # Terminal: nothing may continue, not even silently.
    with pytest.raises(RuntimeError):
        machine.transition("CALIBRATION_2C")

    with pytest.raises(RuntimeError):
        machine.assert_continuable()


def test_pause_resumes_into_the_state_it_left():
    machine = _machine()
    machine.transition("INITIALIZATION")
    machine.transition("PAUSE")

    assert machine.state == "PAUSE"
    assert machine.next_state() == "INITIALIZATION"

    machine.transition("INITIALIZATION")
    assert machine.state == "INITIALIZATION"

    # Resuming may not be used to skip required setup: jumping from
    # INITIALIZATION straight into a condition block is illegal.
    with pytest.raises(ValueError):
        machine.transition("CONDITION_P0")


def test_every_terminal_transition_records_a_stop_reason():
    machine = _machine()
    machine.transition("INITIALIZATION")
    machine.stop_session("EXPERIMENTER_ABORT")

    assert machine.state == "COMPLETE"
    assert machine.transitions[-1].stop_reason == "EXPERIMENTER_ABORT"

    # A low-performance stop is legitimate and is not treated as a
    # technical failure by the continuation guard.
    machine.assert_continuable()