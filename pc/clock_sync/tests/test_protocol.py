import pytest

from pc.clock_sync.protocol import (
    SyncResponse,
    build_sync_request,
    parse_sync_response,
)


def test_build_sync_request_exact_format():
    assert build_sync_request(
        seq=17,
        t1_pc_ns=583021455812300,
    ) == "SYNC_REQ,1,17,583021455812300"


def test_parse_valid_sync_response():
    response = parse_sync_response(
        (
            "SYNC_RESP,1,17,583021455812300,"
            "62199451233120,62199451310455"
        ),
        expected_seq=17,
        expected_t1_pc_ns=583021455812300,
    )

    assert response == SyncResponse(
        seq=17,
        t1_pc_ns=583021455812300,
        t2_phone_ns=62199451233120,
        t3_phone_ns=62199451310455,
    )


def test_reject_wrong_field_count():
    with pytest.raises(
        ValueError,
        match="6 fields",
    ):
        parse_sync_response(
            "SYNC_RESP,1,17",
            expected_seq=17,
            expected_t1_pc_ns=100,
        )


def test_reject_wrong_message_type():
    with pytest.raises(
        ValueError,
        match="message type",
    ):
        parse_sync_response(
            "OTHER,1,17,100,200,201",
            expected_seq=17,
            expected_t1_pc_ns=100,
        )


def test_reject_wrong_protocol_version():
    with pytest.raises(
        ValueError,
        match="protocol version",
    ):
        parse_sync_response(
            "SYNC_RESP,2,17,100,200,201",
            expected_seq=17,
            expected_t1_pc_ns=100,
        )


def test_reject_sequence_mismatch():
    with pytest.raises(
        ValueError,
        match="sequence mismatch",
    ):
        parse_sync_response(
            "SYNC_RESP,1,18,100,200,201",
            expected_seq=17,
            expected_t1_pc_ns=100,
        )


def test_reject_t1_echo_mismatch():
    with pytest.raises(
        ValueError,
        match="t1 echo mismatch",
    ):
        parse_sync_response(
            "SYNC_RESP,1,17,101,200,201",
            expected_seq=17,
            expected_t1_pc_ns=100,
        )


def test_reject_t3_before_t2():
    with pytest.raises(
        ValueError,
        match="t3 before t2",
    ):
        parse_sync_response(
            "SYNC_RESP,1,17,100,300,299",
            expected_seq=17,
            expected_t1_pc_ns=100,
        )


def test_reject_non_numeric_timestamp():
    with pytest.raises(
        ValueError,
        match="numeric",
    ):
        parse_sync_response(
            "SYNC_RESP,1,17,100,abc,201",
            expected_seq=17,
            expected_t1_pc_ns=100,
        )