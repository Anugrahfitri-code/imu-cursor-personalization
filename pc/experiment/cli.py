import argparse
from pathlib import Path
from collections.abc import Sequence

from pc.experiment.session_hash import (
    verify_session_hash_manifest,
    write_session_hash_manifest,
)
from pc.experiment.validator import (
    ValidationReport,
    validate_session,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pc.experiment.cli",
        description=(
            "Validate, finalize, or verify an "
            "IMU Cursor experimental session."
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    for command in (
        "validate",
        "finalize",
        "verify-hashes",
    ):
        command_parser = subparsers.add_parser(command)

        command_parser.add_argument(
            "session_dir",
            type=Path,
            help="Path to the experimental session directory.",
        )

    return parser


def _print_validation_report(
    report: ValidationReport,
) -> None:
    if report.is_valid:
        print("VALIDATION_STATUS=PASS")
        print("VALIDATION = PASS")
        return

    print("VALIDATION_STATUS=FAIL")
    print("VALIDATION = FAIL")

    for issue in report.issues:
        print(
            f"{issue.code}: {issue.message}"
        )


def _command_validate(
    session_dir: Path,
) -> int:
    report = validate_session(session_dir)

    _print_validation_report(report)

    if report.is_valid:
        return 0

    return 1


def _command_finalize(
    session_dir: Path,
) -> int:
    report = validate_session(session_dir)

    _print_validation_report(report)

    if not report.is_valid:
        print("FINALIZATION_STATUS=FAIL")
        print(
            "FINALIZE = REFUSED "
            "(session validation failed)"
        )
        return 1

    hash_manifest_path = write_session_hash_manifest(
        session_dir
    )

    print(
        "HASH MANIFEST = "
        f"{hash_manifest_path.name}"
    )

    hash_errors = verify_session_hash_manifest(
        session_dir
    )

    if hash_errors:
        print("HASH_VERIFY_STATUS=FAIL")
        print("HASH VERIFY = FAIL")

        for error in hash_errors:
            print(error)

        print("FINALIZATION_STATUS=FAIL")
        return 1

    print("HASH_VERIFY_STATUS=PASS")
    print("HASH VERIFY = PASS")
    print("FINALIZATION_STATUS=PASS")
    print("FINALIZE = PASS")

    return 0


def _command_verify_hashes(
    session_dir: Path,
) -> int:
    errors = verify_session_hash_manifest(
        session_dir
    )

    if errors:
        print("HASH_VERIFY_STATUS=FAIL")
        print("HASH VERIFY = FAIL")

        for error in errors:
            print(error)

        return 1

    print("HASH_VERIFY_STATUS=PASS")
    print("HASH VERIFY = PASS")

    return 0


def main(
    argv: Sequence[str] | None = None,
) -> int:
    parser = _build_parser()

    try:
        args = parser.parse_args(argv)

    except SystemExit as exc:
        code = exc.code

        if isinstance(code, int):
            return code

        return 2

    session_dir: Path = args.session_dir

    if args.command == "validate":
        return _command_validate(session_dir)

    if args.command == "finalize":
        return _command_finalize(session_dir)

    if args.command == "verify-hashes":
        return _command_verify_hashes(session_dir)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
