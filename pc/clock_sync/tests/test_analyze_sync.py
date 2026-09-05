import csv
import json
import pc.clock_sync.analyze_sync as analyze_sync_module
import pytest

from pc.clock_sync.analyze_sync import (
    analyze_session,
    build_arg_parser,
    main,
)


def test_analyze_session_writes_model_and_summary(
    tmp_path,
):
    session_dir = (
        tmp_path
        / "m2_clock_test"
    )

    session_dir.mkdir()

    csv_path = (
        session_dir
        / "sync_probes.csv"
    )

    fieldnames = [
        "session_id",
        "probe_phase",
        "probe_seq",
        "t1_pc_ns",
        "t2_phone_ns",
        "t3_phone_ns",
        "t4_pc_ns",
        "pc_rtt_ns",
        "phone_processing_ns",
        "delay_like_ns",
        "phone_mid_ns",
        "pc_mid_ns",
        "response_valid",
        "invalid_reason",
        "selected_low_delay",
        "robust_inlier",
        "model_residual_ns",
    ]

    alpha = 1.000010
    beta = 3_000_000_000_000

    phone0 = (
        50_000_000_000_000
    )

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

        for i in range(12):

            phone_mid = (
                phone0
                + i * 10_000_000_000
            )

            pc_mid = round(
                alpha * phone_mid
                + beta
            )

            t2 = (
                phone_mid
                - 50_000
            )

            t3 = (
                phone_mid
                + 50_000
            )

            t1 = (
                pc_mid
                - 550_000
            )

            t4 = (
                pc_mid
                + 550_000
            )

            writer.writerow(
                {
                    "session_id":
                        "m2_clock_test",

                    "probe_phase":
                        "background",

                    "probe_seq":
                        i + 1,

                    "t1_pc_ns":
                        t1,

                    "t2_phone_ns":
                        t2,

                    "t3_phone_ns":
                        t3,

                    "t4_pc_ns":
                        t4,

                    "pc_rtt_ns":
                        1_100_000,

                    "phone_processing_ns":
                        100_000,

                    "delay_like_ns":
                        1_000_000,

                    "phone_mid_ns":
                        phone_mid,

                    "pc_mid_ns":
                        pc_mid,

                    "response_valid":
                        True,

                    "invalid_reason":
                        "",

                    "selected_low_delay":
                        False,

                    "robust_inlier":
                        False,

                    "model_residual_ns":
                        "",
                }
            )

    model = analyze_session(
        session_dir
    )

    model_path = (
        session_dir
        / "clock_model.json"
    )

    summary_path = (
        session_dir
        / "summary.txt"
    )

    assert model_path.exists()
    assert summary_path.exists()

    data = json.loads(
        model_path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        data["model"]
        == "affine_phone_to_pc"
    )

    assert data["alpha"] == pytest.approx(
        alpha,
        abs=1e-9,
    )

    assert model.alpha == pytest.approx(
        alpha,
        abs=1e-9,
    )
    
CSV_FIELDS = [
    "session_id",
    "probe_phase",
    "probe_seq",
    "t1_pc_ns",
    "t2_phone_ns",
    "t3_phone_ns",
    "t4_pc_ns",
    "pc_rtt_ns",
    "phone_processing_ns",
    "delay_like_ns",
    "phone_mid_ns",
    "pc_mid_ns",
    "response_valid",
    "invalid_reason",
    "selected_low_delay",
    "robust_inlier",
    "model_residual_ns",
]


def _write_synthetic_session(
    session_dir,
    *,
    valid_count,
    invalid_count=0,
    alpha=1.000010,
    beta=3_000_000_000_000,
):
    csv_path = (
        session_dir
        / "sync_probes.csv"
    )

    phone0 = (
        50_000_000_000_000
    )

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=CSV_FIELDS,
        )

        writer.writeheader()

        for i in range(valid_count):
            phone_mid = (
                phone0
                + i * 10_000_000_000
            )

            pc_mid = round(
                alpha * phone_mid
                + beta
            )

            t2 = phone_mid - 50_000
            t3 = phone_mid + 50_000

            t1 = pc_mid - 550_000
            t4 = pc_mid + 550_000

            writer.writerow(
                {
                    "session_id":
                        session_dir.name,

                    "probe_phase":
                        "background",

                    "probe_seq":
                        i + 1,

                    "t1_pc_ns":
                        t1,

                    "t2_phone_ns":
                        t2,

                    "t3_phone_ns":
                        t3,

                    "t4_pc_ns":
                        t4,

                    "pc_rtt_ns":
                        1_100_000,

                    "phone_processing_ns":
                        100_000,

                    "delay_like_ns":
                        1_000_000,

                    "phone_mid_ns":
                        phone_mid,

                    "pc_mid_ns":
                        pc_mid,

                    "response_valid":
                        True,

                    "invalid_reason":
                        "",

                    "selected_low_delay":
                        False,

                    "robust_inlier":
                        False,

                    "model_residual_ns":
                        "",
                }
            )

        for j in range(
            invalid_count
        ):
            writer.writerow(
                {
                    "session_id":
                        session_dir.name,

                    "probe_phase":
                        "background",

                    "probe_seq":
                        valid_count + j + 1,

                    "t1_pc_ns":
                        1_000_000 + j,

                    "t2_phone_ns":
                        "",

                    "t3_phone_ns":
                        "",

                    "t4_pc_ns":
                        1_100_000 + j,

                    "pc_rtt_ns":
                        "",

                    "phone_processing_ns":
                        "",

                    "delay_like_ns":
                        "",

                    "phone_mid_ns":
                        "",

                    "pc_mid_ns":
                        "",

                    "response_valid":
                        False,

                    "invalid_reason":
                        "timeout",

                    "selected_low_delay":
                        False,

                    "robust_inlier":
                        False,

                    "model_residual_ns":
                        "",
                }
            )

    return csv_path


def test_analysis_reports_required_diagnostics_and_annotations(
    tmp_path,
):
    session_dir = (
        tmp_path
        / "diagnostic_test"
    )

    session_dir.mkdir()

    csv_path = (
        _write_synthetic_session(
            session_dir,
            valid_count=19,
            invalid_count=1,
        )
    )

    analyze_session(
        session_dir
    )

    model_data = json.loads(
        (
            session_dir
            / "clock_model.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert (
        model_data["probe_counts"]["sent"]
        == 20
    )

    assert (
        model_data["probe_counts"]["valid"]
        == 19
    )

    assert (
        model_data["probe_counts"]["invalid"]
        == 1
    )

    assert (
        model_data["response_rate"]
        == pytest.approx(0.95)
    )

    assert (
        model_data[
            "probe_counts"
        ]["selected"]
        > 0
    )

    assert (
        model_data[
            "probe_counts"
        ]["inliers"]
        > 0
    )

    residual = (
        model_data[
            "absolute_residual_ms"
        ]
    )

    assert residual["p50"] >= 0
    assert residual["p95"] >= 0
    assert residual["max"] >= 0

    delay = (
        model_data["delay_like_ms"]
    )

    assert delay["p50"] >= 0
    assert delay["p95"] >= 0

    processing = (
        model_data[
            "phone_processing_ms"
        ]
    )

    assert processing["p50"] >= 0
    assert processing["p95"] >= 0

    assert "first_half" in model_data
    assert "second_half" in model_data

    assert (
        "skew_ppm"
        in model_data["first_half"]
    )

    assert (
        "skew_ppm"
        in model_data["second_half"]
    )

    with csv_path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        rows = list(
            csv.DictReader(handle)
        )

    valid_rows = [
        row
        for row in rows
        if (
            row["response_valid"]
            == "True"
        )
    ]

    invalid_rows = [
        row
        for row in rows
        if (
            row["response_valid"]
            == "False"
        )
    ]

    assert any(
        row["selected_low_delay"]
        == "True"
        for row in valid_rows
    )

    assert any(
        row["robust_inlier"]
        == "True"
        for row in valid_rows
    )

    assert any(
        row["model_residual_ns"]
        != ""
        for row in valid_rows
    )

    assert all(
        row["selected_low_delay"]
        == "False"
        for row in invalid_rows
    )

    assert all(
        row["robust_inlier"]
        == "False"
        for row in invalid_rows
    )


def test_analysis_rejects_response_rate_below_95_percent(
    tmp_path,
):
    session_dir = (
        tmp_path
        / "low_response_test"
    )

    session_dir.mkdir()

    _write_synthetic_session(
        session_dir,
        valid_count=18,
        invalid_count=2,
    )

    with pytest.raises(
        ValueError,
        match="response rate",
    ):
        analyze_session(
            session_dir
        )


def test_analysis_accepts_exactly_95_percent_response_rate(
    tmp_path,
):
    session_dir = (
        tmp_path
        / "boundary_response_test"
    )

    session_dir.mkdir()

    _write_synthetic_session(
        session_dir,
        valid_count=19,
        invalid_count=1,
    )

    model = analyze_session(
        session_dir
    )

    assert model.alpha > 0


def test_analysis_rejects_implausible_clock_skew(
    tmp_path,
):
    session_dir = (
        tmp_path
        / "bad_skew_test"
    )

    session_dir.mkdir()

    # alpha = 1.002
    # => +2000 ppm, outside
    # the broad 1000 ppm sanity gate.
    _write_synthetic_session(
        session_dir,
        valid_count=12,
        invalid_count=0,
        alpha=1.002,
    )

    with pytest.raises(
        ValueError,
        match="skew",
    ):
        analyze_session(
            session_dir
        )   
        
def test_analyze_cli_parser_accepts_session_dir(
    tmp_path,
):
    parser = build_arg_parser()

    args = parser.parse_args(
        [
            str(
                tmp_path
                / "m2_clock_test"
            )
        ]
    )

    assert args.session_dir == (
        tmp_path
        / "m2_clock_test"
    )


def test_analyze_cli_main_calls_session_analysis(
    tmp_path,
    monkeypatch,
    capsys,
):
    session_dir = (
        tmp_path
        / "m2_clock_cli_test"
    )

    called = {}

    class FakeModel:
        alpha = 1.00001
        skew_ppm = 10.0

    def fake_analyze_session(
        path,
    ):
        called["path"] = path
        return FakeModel()

    monkeypatch.setattr(
        analyze_sync_module,
        "analyze_session",
        fake_analyze_session,
    )

    result = main(
        [
            str(session_dir)
        ]
    )

    output = capsys.readouterr().out

    assert result == 0
    assert called["path"] == session_dir
    assert "Analysis complete" in output         
    
    