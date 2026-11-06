"""Temperature unit and formatting helpers.

{{UNRELATED_NOTE}}
"""

CONTROLLER_RESOLUTION_C = 0.5


def c_to_f(value_c: float) -> float:
    return round(value_c * 9 / 5 + 32, 1)


def f_to_c(value_f: float) -> float:
    return round((value_f - 32) * 5 / 9, 1)


def round_to_controller(value_c: float) -> float:
    steps = round(value_c / CONTROLLER_RESOLUTION_C)
    return steps * CONTROLLER_RESOLUTION_C


def format_temp(value_c: float, unit: str = "C") -> str:
    if unit == "F":
        return f"{c_to_f(value_c):.1f}°F"
    return f"{value_c:.1f}°C"


def describe_change(change, unit: str = "C") -> str:
    return (
        f"{change.change_id} {change.building}/{change.zone} {change.mode} "
        f"{format_temp(change.current_c, unit)} -> {format_temp(change.target_c, unit)}"
    )
