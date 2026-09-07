from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from pc.clock_sync.clock_model import (
    ClockModel,
    ProbeObservation,
    fit_half_diagnostics,
    fit_robust_clock_model,
    percentile,
)


HARD_RESPONSE_RATE = 0.95
SKEW_SANITY_PPM = 1000.0


def _parse_bool(
    value: str,
) -> bool:
    return (
        value.strip().lower()
        == "true"
    )


def _row_to_probe(
    row: dict[str, str],
) -> ProbeObservation | None:

    if not _parse_bool(
        row["response_valid"]
    ):
        return None

    required = [
        "t1_pc_ns",
        "t2_phone_ns",
        "t3_phone_ns",
        "t4_pc_ns",
    ]

    if any(
        not row[field].strip()
        for field in required
    ):
        return None

    try:
        probe = ProbeObservation(
            session_id=(
                row["session_id"]
            ),

            probe_phase=(
                row["probe_phase"]
            ),

            probe_seq=int(
                row["probe_seq"]
            ),

            t1_pc_ns=int(
                row["t1_pc_ns"]
            ),

            t2_phone_ns=int(
                row["t2_phone_ns"]
            ),

            t3_phone_ns=int(
                row["t3_phone_ns"]
            ),

            t4_pc_ns=int(
                row["t4_pc_ns"]
            ),

            response_valid=True,

            invalid_reason=(
                row.get(
                    "invalid_reason",
                    "",
                )
            ),
        )

    except (TypeError, ValueError):
        return None

    if (
        probe.t4_pc_ns
        < probe.t1_pc_ns
    ):
        return None

    if (
        probe.t3_phone_ns
        < probe.t2_phone_ns
    ):
        return None

    if probe.delay_like_ns < 0:
        return None

    return probe


def _ms(
    value_ns: float,
) -> float:
    return (
        float(value_ns)
        / 1_000_000.0
    )


def _residual_summary(
    model: ClockModel,
) -> dict[str, float]:

    values = [
        abs(value)
        for value
        in model.residual_ns_by_seq.values()
    ]

    if not values:
        raise ValueError(
            "clock model has no residuals"
        )

    return {
        "p50":
            _ms(
                percentile(
                    values,
                    0.50,
                )
            ),

        "p95":
            _ms(
                percentile(
                    values,
                    0.95,
                )
            ),

        "max":
            _ms(
                max(values)
            ),
    }


def _half_summary(
    model: ClockModel,
) -> dict[str, float]:

    residual = (
        _residual_summary(
            model
        )
    )

    return {
        "alpha":
            model.alpha,

        "skew_ppm":
            model.skew_ppm,

        "residual_p50_ms":
            residual["p50"],

        "residual_p95_ms":
            residual["p95"],
    }


def _rewrite_annotated_csv(
    csv_path: Path,
    rows: list[dict[str, str]],
    fieldnames: list[str],
    model: ClockModel,
) -> None:

    selected = set(
        model.selected_probe_seqs
    )

    inliers = set(
        model.inlier_probe_seqs
    )

    residuals = (
        model.residual_ns_by_seq
    )

    required_annotation_fields = [
        "selected_low_delay",
        "robust_inlier",
        "model_residual_ns",
    ]

    for field in required_annotation_fields:
        if field not in fieldnames:
            fieldnames.append(
                field
            )

    for row in rows:

        try:
            seq = int(
                row["probe_seq"]
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            row[
                "selected_low_delay"
            ] = "False"

            row[
                "robust_inlier"
            ] = "False"

            row[
                "model_residual_ns"
            ] = ""

            continue

        is_valid = _parse_bool(
            row.get(
                "response_valid",
                "False",
            )
        )

        row[
            "selected_low_delay"
        ] = str(
            is_valid
            and seq in selected
        )

        row[
            "robust_inlier"
        ] = str(
            is_valid
            and seq in inliers
        )

        if (
            is_valid
            and seq in residuals
        ):
            row[
                "model_residual_ns"
            ] = str(
                residuals[seq]
            )
        else:
            row[
                "model_residual_ns"
            ] = ""

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(
            rows
        )


def analyze_session(
    session_dir: Path,
) -> ClockModel:

    session_dir = Path(
        session_dir
    )

    csv_path = (
        session_dir
        / "sync_probes.csv"
    )

    if not csv_path.exists():
        raise FileNotFoundError(
            csv_path
        )

    with csv_path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:

        reader = csv.DictReader(
            handle
        )

        fieldnames = list(
            reader.fieldnames
            or []
        )

        rows = list(
            reader
        )

    sent_count = len(
        rows
    )

    if sent_count == 0:
        raise ValueError(
            "no clock-sync probes found"
        )

    probes: list[
        ProbeObservation
    ] = []

    for row in rows:

        probe = _row_to_probe(
            row
        )

        if probe is not None:
            probes.append(
                probe
            )

    valid_count = len(
        probes
    )

    invalid_count = (
        sent_count
        - valid_count
    )

    response_rate = (
        valid_count
        / sent_count
    )

    if (
        response_rate
        < HARD_RESPONSE_RATE
    ):
        raise ValueError(
            "response rate below "
            f"{HARD_RESPONSE_RATE:.0%}: "
            f"{response_rate:.3%}"
        )

    model = (
        fit_robust_clock_model(
            probes
        )
    )

    if (
        abs(model.skew_ppm)
        >= SKEW_SANITY_PPM
    ):
        raise ValueError(
            "clock skew outside "
            "sanity limit: "
            f"{model.skew_ppm:.3f} ppm"
        )

    residual_summary = (
        _residual_summary(
            model
        )
    )

    valid_delay_values = [
        probe.delay_like_ns
        for probe in probes
    ]

    valid_processing_values = [
        probe.phone_processing_ns
        for probe in probes
    ]

    delay_summary = {
        "p50":
            _ms(
                percentile(
                    valid_delay_values,
                    0.50,
                )
            ),

        "p95":
            _ms(
                percentile(
                    valid_delay_values,
                    0.95,
                )
            ),
    }

    processing_summary = {
        "p50":
            _ms(
                percentile(
                    valid_processing_values,
                    0.50,
                )
            ),

        "p95":
            _ms(
                percentile(
                    valid_processing_values,
                    0.95,
                )
            ),
    }

    # First-half / second-half are
    # diagnostic only. They do not replace
    # the primary full-session model.
    first_model, second_model = (
        fit_half_diagnostics(
            probes
        )
    )

    first_summary = (
        _half_summary(
            first_model
        )
    )

    second_summary = (
        _half_summary(
            second_model
        )
    )

    model_data = {
        "model":
            "affine_phone_to_pc",

        "alpha":
            model.alpha,

        "beta_ns":
            model.beta_ns,

        "skew_ppm":
            model.skew_ppm,

        "response_rate":
            response_rate,

        "probe_counts": {
            "sent":
                sent_count,

            "valid":
                valid_count,

            "invalid":
                invalid_count,

            "selected":
                len(
                    model.selected_probe_seqs
                ),

            "inliers":
                len(
                    model.inlier_probe_seqs
                ),
        },

        "absolute_residual_ms":
            residual_summary,

        "delay_like_ms":
            delay_summary,

        "phone_processing_ms":
            processing_summary,

        "first_half":
            first_summary,

        "second_half":
            second_summary,
    }

    model_path = (
        session_dir
        / "clock_model.json"
    )

    model_path.write_text(
        json.dumps(
            model_data,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary_path = (
        session_dir
        / "summary.txt"
    )

    summary = (
        "M2.3 Clock Synchronization\n"
        "==========================\n"
        "\n"
        "Model: affine_phone_to_pc\n"
        f"alpha: {model.alpha:.12f}\n"
        f"beta_ns: {model.beta_ns:.3f}\n"
        f"skew_ppm: "
        f"{model.skew_ppm:.6f}\n"
        "\n"
        f"sent_probes: "
        f"{sent_count}\n"
        f"valid_probes: "
        f"{valid_count}\n"
        f"invalid_probes: "
        f"{invalid_count}\n"
        f"response_rate: "
        f"{response_rate:.6f}\n"
        f"selected_probes: "
        f"{len(model.selected_probe_seqs)}\n"
        f"inlier_probes: "
        f"{len(model.inlier_probe_seqs)}\n"
        "\n"
        "Absolute residual (ms)\n"
        f"p50: "
        f"{residual_summary['p50']:.6f}\n"
        f"p95: "
        f"{residual_summary['p95']:.6f}\n"
        f"max: "
        f"{residual_summary['max']:.6f}\n"
        "\n"
        "Delay-like (ms)\n"
        f"p50: "
        f"{delay_summary['p50']:.6f}\n"
        f"p95: "
        f"{delay_summary['p95']:.6f}\n"
        "\n"
        "Phone processing (ms)\n"
        f"p50: "
        f"{processing_summary['p50']:.6f}\n"
        f"p95: "
        f"{processing_summary['p95']:.6f}\n"
        "\n"
        "First half\n"
        f"alpha: "
        f"{first_model.alpha:.12f}\n"
        f"skew_ppm: "
        f"{first_model.skew_ppm:.6f}\n"
        "\n"
        "Second half\n"
        f"alpha: "
        f"{second_model.alpha:.12f}\n"
        f"skew_ppm: "
        f"{second_model.skew_ppm:.6f}\n"
    )

    summary_path.write_text(
        summary,
        encoding="utf-8",
    )

    _rewrite_annotated_csv(
        csv_path,
        rows,
        fieldnames,
        model,
    )

    return model

def build_arg_parser(
) -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "Analyze an M2.3 clock "
            "synchronization session"
        )
    )

    parser.add_argument(
        "session_dir",
        type=Path,
        help=(
            "Directory containing "
            "sync_probes.csv"
        ),
    )

    return parser


def main(
    argv: list[str] | None = None,
) -> int:

    parser = build_arg_parser()

    args = parser.parse_args(
        argv
    )

    model = analyze_session(
        args.session_dir
    )

    print(
        "Analysis complete: "
        f"{args.session_dir}"
    )

    print(
        f"alpha={model.alpha:.12f}"
    )

    print(
        f"skew_ppm="
        f"{model.skew_ppm:.6f}"
    )

    print(
        "Outputs:"
    )

    print(
        f"  {args.session_dir / 'clock_model.json'}"
    )

    print(
        f"  {args.session_dir / 'summary.txt'}"
    )

    print(
        f"  {args.session_dir / 'sync_probes.csv'}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )