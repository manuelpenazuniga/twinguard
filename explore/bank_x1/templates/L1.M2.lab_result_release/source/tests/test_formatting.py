from labportal.formatting import format_reference_range, format_result_lines, format_value


def test_format_value_trims_trailing_zeros():
    assert format_value(5.40, "mmol/L") == "5.4 mmol/L"
    assert format_value(12, "g/dL") == "12 g/dL"


def test_reference_range_open_ended():
    assert format_reference_range(None, 200, "mg/dL") == "< 200 mg/dL"
    assert format_reference_range(3.9, 5.6, "mmol/L") == "3.9-5.6 mmol/L"


def test_result_lines_include_flag():
    lines = format_result_lines({"test_code": "K", "value": 6.1, "unit": "mmol/L",
                                 "ref_low": 3.5, "ref_high": 5.1})
    assert lines == ("K: 6.1 mmol/L", "Reference range: 3.5-5.1 mmol/L", "Flag: H")
