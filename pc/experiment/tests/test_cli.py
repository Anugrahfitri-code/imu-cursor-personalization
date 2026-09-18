from pc.experiment.cli import main
from pc.experiment.session_hash import HASH_MANIFEST_NAME
from pc.experiment.tests.fixture_builder import (
    build_synthetic_session,
)


def test_validate_valid_session_returns_zero(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    exit_code = main([
        "validate",
        str(session_dir),
    ])

    assert exit_code == 0


def test_validate_invalid_session_returns_one(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    (
        session_dir
        / "raw"
        / "trial_events.csv"
    ).unlink()

    exit_code = main([
        "validate",
        str(session_dir),
    ])

    assert exit_code == 1


def test_finalize_invalid_session_refuses_hash_manifest(
    tmp_path,
):
    session_dir = build_synthetic_session(tmp_path)

    (
        session_dir
        / "raw"
        / "cursor_samples.csv"
    ).unlink()

    exit_code = main([
        "finalize",
        str(session_dir),
    ])

    assert exit_code == 1
    assert not (
        session_dir / HASH_MANIFEST_NAME
    ).exists()


def test_finalize_valid_closed_session_writes_hash_manifest(
    tmp_path,
):
    session_dir = build_synthetic_session(tmp_path)

    exit_code = main([
        "finalize",
        str(session_dir),
    ])

    assert exit_code == 0
    assert (
        session_dir / HASH_MANIFEST_NAME
    ).is_file()


def test_verify_hashes_returns_zero_for_unchanged_session(
    tmp_path,
):
    session_dir = build_synthetic_session(tmp_path)

    finalize_code = main([
        "finalize",
        str(session_dir),
    ])

    assert finalize_code == 0

    verify_code = main([
        "verify-hashes",
        str(session_dir),
    ])

    assert verify_code == 0


def test_verify_hashes_returns_one_after_evidence_change(
    tmp_path,
):
    session_dir = build_synthetic_session(tmp_path)

    finalize_code = main([
        "finalize",
        str(session_dir),
    ])

    assert finalize_code == 0

    evidence_path = (
        session_dir
        / "raw"
        / "trial_events.csv"
    )

    with evidence_path.open(
        "a",
        encoding="utf-8",
        newline="",
    ) as handle:
        handle.write("\n")

    verify_code = main([
        "verify-hashes",
        str(session_dir),
    ])

    assert verify_code == 1


def test_usage_failure_returns_two():
    exit_code = main([])

    assert exit_code == 2
