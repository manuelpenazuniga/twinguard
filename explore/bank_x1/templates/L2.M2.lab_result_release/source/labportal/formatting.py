"""{{UNRELATED_NOTE}}"""


def format_value(value, unit):
    if isinstance(value, float):
        text = f"{value:.2f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    return f"{text} {unit}".strip()


def format_reference_range(low, high, unit):
    if low is None and high is None:
        return ""
    if low is None:
        return f"< {format_value(high, unit)}"
    if high is None:
        return f"> {format_value(low, unit)}"
    return f"{format_value(low, '')}-{format_value(high, unit)}"


def flag_for(value, low, high):
    if not isinstance(value, (int, float)):
        return ""
    if low is not None and value < low:
        return "L"
    if high is not None and value > high:
        return "H"
    return ""


def format_result_lines(request):
    unit = request.get("unit", "")
    value = request["value"]
    low, high = request.get("ref_low"), request.get("ref_high")
    lines = [f"{request['test_code']}: {format_value(value, unit)}"]
    reference = format_reference_range(low, high, unit)
    if reference:
        lines.append(f"Reference range: {reference}")
    flag = flag_for(value, low, high)
    if flag:
        lines.append(f"Flag: {flag}")
    return tuple(lines)
