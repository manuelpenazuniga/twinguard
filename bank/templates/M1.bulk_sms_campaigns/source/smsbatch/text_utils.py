"""{{UNRELATED_NOTE}}"""
import re

GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXTENDED = set("^{}\\[~]|€")

_SPACES = re.compile(r"[ \t]+")
_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def normalise_body(body: str) -> str:
    """Collapse runs of spaces and strip trailing whitespace on each line."""
    lines = [_SPACES.sub(" ", line).rstrip() for line in body.strip().splitlines()]
    return "\n".join(lines)


def is_gsm7(body: str) -> bool:
    return all(ch in GSM7_BASIC or ch in GSM7_EXTENDED for ch in body)


def segment_count(body: str) -> int:
    """Number of SMS segments needed for ``body``."""
    if not body:
        return 0
    if is_gsm7(body):
        units = sum(2 if ch in GSM7_EXTENDED else 1 for ch in body)
        single, multi = 160, 153
    else:
        units = len(body.encode("utf-16-le")) // 2
        single, multi = 70, 67
    if units <= single:
        return 1
    return -(-units // multi)


def is_valid_msisdn(number: str) -> bool:
    return bool(_E164.match(number))
