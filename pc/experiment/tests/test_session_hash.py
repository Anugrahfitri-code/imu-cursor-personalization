from pathlib import Path

import pytest

from pc.experiment.session_hash import (
    generate_session_hashes,
    sha256_file,
    verify_session_hash_manifest,
    write_session_hash_manifest,
)
from pc.experiment.tests.fixture_builder import (
    build_synthetic_session,
)


HASH_MANIFEST_NAME = "SESSION_SHA256SUMS.txt"


def _manifest_lines(
    hash_manifest_path: Path,
) -> list[str]:
    return [
        line
        for line in hash_manifest_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def _relative_paths_from_manifest(
    hash_manifest_path: Path,
) -> list[str]:
    paths: list[str] = []

    for line in _manifest_lines(hash_manifest_path):
        digest, separator, relative_path = line.partition("  ")

        assert separator == "  "
        assert len(digest) == 64
        assert digest == digest.upper()

        paths.append(relative_path)

    return paths


def test_sha256_file_is_deterministic(tmp_path):
    path = tmp_path / "evidence.bin"
    path.write_bytes(b"imu-cursor-synthetic-evidence\n")

    first = sha256_file(path)
    second = sha256_file(path)

    assert first == second
    assert len(first) == 64
    assert first == first.upper()


def test_hash_manifest_is_sorted_by_relative_path(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    hash_manifest_path = write_session_hash_manifest(
        session_dir
    )

    paths = _relative_paths_from_manifest(
        hash_manifest_path
    )

    assert paths == sorted(paths)


def test_hash_manifest_uses_relative_paths(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    hash_manifest_path = write_session_hash_manifest(
        session_dir
    )

    paths = _relative_paths_from_manifest(
        hash_manifest_path
    )

    assert paths

    for relative_path in paths:
        assert not Path(relative_path).is_absolute()
        assert "\\" not in relative_path
        assert not relative_path.startswith("/")
        assert str(session_dir) not in relative_path


def test_hash_manifest_excludes_itself(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    first_manifest = write_session_hash_manifest(
        session_dir
    )

    assert first_manifest.name == HASH_MANIFEST_NAME

    second_manifest = write_session_hash_manifest(
        session_dir
    )

    paths = _relative_paths_from_manifest(
        second_manifest
    )

    assert HASH_MANIFEST_NAME not in paths

    generated = generate_session_hashes(session_dir)

    assert all(
        HASH_MANIFEST_NAME not in str(entry)
        for entry in generated
    )


def test_hash_manifest_detects_modified_file(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    write_session_hash_manifest(session_dir)

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

    errors = verify_session_hash_manifest(
        session_dir
    )

    assert errors


def test_hash_manifest_detects_missing_file(tmp_path):
    session_dir = build_synthetic_session(tmp_path)

    write_session_hash_manifest(session_dir)

    evidence_path = (
        session_dir
        / "raw"
        / "cursor_samples.csv"
    )
    evidence_path.unlink()

    errors = verify_session_hash_manifest(
        session_dir
    )

    assert errors


@pytest.mark.parametrize("tamper", ["empty", "omitted", "duplicate", "added"])
def test_hash_verification_requires_exact_file_inventory(tmp_path, tamper):
    session_dir = build_synthetic_session(tmp_path)
    manifest = write_session_hash_manifest(session_dir)
    lines = manifest.read_text(encoding="utf-8").splitlines()
    if tamper == "empty":
        manifest.write_text("\n", encoding="utf-8")
    elif tamper == "omitted":
        manifest.write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
    elif tamper == "duplicate":
        manifest.write_text("\n".join(lines + [lines[0]]) + "\n", encoding="utf-8")
    else:
        (session_dir / "new_evidence.txt").write_text("unlisted", encoding="utf-8")
    assert verify_session_hash_manifest(session_dir)


def test_hash_manifest_rejects_external_symlink(tmp_path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("outside evidence", encoding="utf-8")
    (session_dir / "linked.txt").symlink_to(external)
    (session_dir / HASH_MANIFEST_NAME).write_text(
        f"{sha256_file(external)}  linked.txt\n", encoding="utf-8"
    )
    assert verify_session_hash_manifest(session_dir)
    with pytest.raises(ValueError):
        generate_session_hashes(session_dir)


@pytest.mark.parametrize("path", ["./evidence.txt", "a/../evidence.txt", "C:/evidence.txt", "a\\evidence.txt"])
def test_hash_manifest_rejects_nonportable_paths(tmp_path, path):
    (tmp_path / "evidence.txt").write_text("evidence", encoding="utf-8")
    (tmp_path / HASH_MANIFEST_NAME).write_text(
        f"{sha256_file(tmp_path / 'evidence.txt')}  {path}\n", encoding="utf-8"
    )
    assert verify_session_hash_manifest(tmp_path)


def test_hash_manifest_writer_preserves_existing_failed_baseline(tmp_path):
    session_dir = build_synthetic_session(tmp_path)
    manifest = write_session_hash_manifest(session_dir)
    original = manifest.read_bytes()
    (session_dir / "raw/trial_events.csv").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError):
        write_session_hash_manifest(session_dir)
    assert manifest.read_bytes() == original
