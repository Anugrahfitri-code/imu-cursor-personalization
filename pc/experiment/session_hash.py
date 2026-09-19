import hashlib
from pathlib import Path, PurePosixPath


HASH_MANIFEST_NAME = "SESSION_SHA256SUMS.txt"


def is_session_relative_path(value: object) -> bool:
    """Require a portable, unambiguous relative file name."""
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and not any(character in value for character in ("\\", ":", "\n", "\r", "\x00"))
        and not PurePosixPath(value).is_absolute()
        and all(part not in ("", ".", "..") for part in value.split("/"))
    )


def session_file_path(session_dir: Path, relative_path: str) -> Path:
    if not is_session_relative_path(relative_path):
        raise ValueError(f"Invalid session-relative path: {relative_path!r}")
    root = session_dir.resolve()
    path = root
    for part in PurePosixPath(relative_path).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"Session evidence must not use symlinks: {relative_path}")
    if not path.resolve().is_relative_to(root):
        raise ValueError(f"Session evidence escapes session directory: {relative_path}")
    return path


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

    for path in session_dir.rglob("*"):
        relative_path = path.relative_to(session_dir).as_posix()
        if path.is_symlink():
            raise ValueError(f"Session evidence must not use symlinks: {relative_path}")
        if not path.is_file():
            continue
        session_file_path(session_dir, relative_path)
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
    hash_manifest_path = (
        session_dir / HASH_MANIFEST_NAME
    )
    if hash_manifest_path.exists() or hash_manifest_path.is_symlink():
        errors = verify_session_hash_manifest(session_dir)
        if errors:
            raise ValueError("Existing session hash manifest failed verification: " + "; ".join(errors))
        return hash_manifest_path

    entries = generate_session_hashes(session_dir)
    if not entries:
        raise ValueError("Cannot hash an empty session.")

    contents = "".join(
        f"{digest}  {relative_path}\n"
        for digest, relative_path in entries
    )

    with hash_manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(contents)

    return hash_manifest_path


def verify_session_hash_manifest(
    session_dir: Path,
) -> list[str]:
    errors: list[str] = []

    hash_manifest_path = (
        session_dir / HASH_MANIFEST_NAME
    )

    if hash_manifest_path.is_symlink():
        return ["Session hash manifest must not be a symlink."]

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

    seen_paths: set[str] = set()
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

        if not is_session_relative_path(relative_path):
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

        if relative_path in seen_paths:
            errors.append(f"Duplicate hash entry: {relative_path}")
            continue
        seen_paths.add(relative_path)

        try:
            evidence_path = session_file_path(session_dir, relative_path)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
            continue

        if not evidence_path.is_file():
            errors.append(
                f"Missing file: {relative_path}"
            )
            continue

        try:
            actual_hash = sha256_file(evidence_path)
        except OSError as exc:
            errors.append(f"Could not hash {relative_path}: {exc}")
            continue

        if actual_hash != expected_hash:
            errors.append(
                (
                    f"SHA-256 mismatch: {relative_path}; "
                    f"expected={expected_hash}, "
                    f"actual={actual_hash}"
                )
            )

    if not seen_paths:
        errors.append("Session hash manifest contains no evidence entries.")
    try:
        actual_paths = set()
        for path in session_dir.rglob("*"):
            relative_path = path.relative_to(session_dir).as_posix()
            if path.is_symlink():
                raise ValueError(f"Session evidence must not use symlinks: {relative_path}")
            if path.is_file() and relative_path != HASH_MANIFEST_NAME:
                session_file_path(session_dir, relative_path)
                actual_paths.add(relative_path)
        for relative_path in sorted(actual_paths - seen_paths):
            errors.append(f"File absent from session hash manifest: {relative_path}")
    except (OSError, ValueError) as exc:
        errors.append(f"Could not inventory session evidence: {exc}")
    return errors
