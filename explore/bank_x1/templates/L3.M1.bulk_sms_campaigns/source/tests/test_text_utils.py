from smsbatch.text_utils import is_valid_msisdn, normalise_body, segment_count


def test_normalise_body_collapses_spaces():
    assert normalise_body("  Hello   there \nbye  ") == "Hello there\nbye"


def test_segment_count_gsm7():
    assert segment_count("a" * 160) == 1
    assert segment_count("a" * 161) == 2


def test_segment_count_unicode():
    assert segment_count("ё" * 70) == 1
    assert segment_count("ё" * 71) == 2


def test_msisdn_validation():
    assert is_valid_msisdn("+447700900001")
    assert not is_valid_msisdn("07700900001")
