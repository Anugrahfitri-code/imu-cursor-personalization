import hashlib
from pathlib import Path, PurePosixPath


HASH_MANIFEST_NAME = "SESSION_SHA256SUMS.txt"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest().upper()


def generate_session_hashes(
    session_dir: Path,
) -> list[tuple[str, str]]:
    if not session_dir.is_dir():
        raise ValueError(
            f"Session directory does not exist: {session_dir}"
        )

    entries: list[tuple[str, str]] = []

    files = [
        path
        for path in session_dir.rglob("*")
        if path.is_file()
    ]

    for path in files:
        relative_path = path.relative_to(session_dir).as_posix()

        if relative_path == HASH_MANIFEST_NAME:
            continue

        entries.append(
            (
                sha256_file(path),
                relative_path,
            )
        )

    entries.sort(
        key=lambda entry: entry[1]
    )

    return entries


def write_session_hash_manifest(
    session_dir: Path,
) -> Path:
    entries = generate_session_hashes(session_dir)

    hash_manifest_path = (
        session_dir / HASH_MANIFEST_NAME
    )

    contents = "".join(
        f"{digest}  {relative_path}\n"
        for digest, relative_path in entries
    )

    hash_manifest_path.write_text(
        contents,
        encoding="utf-8",
        newline="\n",
    )

    return hash_manifest_path


def verify_session_hash_manifest(
    session_dir: Path,
) -> list[str]:
    errors: list[str] = []

    hash_manifest_path = (
        session_dir / HASH_MANIFEST_NAME
    )

    if not hash_manifest_path.is_file():
        return [
            (
                "Session hash manifest does not exist: "
                f"{HASH_MANIFEST_NAME}"
            )
        ]

    try:
        lines = hash_manifest_path.read_text(
            encoding="utf-8"
        ).splitlines()

    except (OSError, UnicodeError) as exc:
        return [
            f"Could not read session hash manifest: {exc}"
        ]

    for line_number, line in enumerate(
        lines,
        start=1,
    ):
        if not line.strip():
            continue

        expected_hash, separator, relative_path = (
            line.partition("  ")
        )

        if separator != "  ":
            errors.append(
                (
                    f"Malformed hash entry at line "
                    f"{line_number}: missing two-space separator."
                )
            )
            continue

        if (
            len(expected_hash) != 64
            or any(
                character not in "0123456789ABCDEF"
                for character in expected_hash
            )
        ):
            errors.append(
                (
                    f"Malformed SHA-256 at line "
                    f"{line_number}: {expected_hash!r}"
                )
            )
            continue

        if not relative_path:
            errors.append(
                (
                    f"Malformed hash entry at line "
                    f"{line_number}: empty relative path."
                )
            )
            continue

        relative_posix = PurePosixPath(relative_path)

        if (
            relative_posix.is_absolute()
            or ".." in relative_posix.parts
        ):
            errors.append(
                (
                    f"Invalid relative path at line "
                    f"{line_number}: {relative_path!r}"
                )
            )
            continue

        if relative_path == HASH_MANIFEST_NAME:
            errors.append(
                (
                    "Hash manifest must not contain "
                    "an entry for itself."
                )
            )
            continue

        evidence_path = session_dir.joinpath(
            *relative_posix.parts
        )

        if not evidence_path.is_file():
            errors.append(
                f"Missing file: {relative_path}"
            )
            continue

        actual_hash = sha256_file(evidence_path)

        if actual_hash != expected_hash:
            errors.append(
                (
                    f"SHA-256 mismatch: {relative_path}; "
                    f"expected={expected_hash}, "
                    f"actual={actual_hash}"
                )
            )

    return errors
