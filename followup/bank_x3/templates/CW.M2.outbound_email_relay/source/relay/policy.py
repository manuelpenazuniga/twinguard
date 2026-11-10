"""Sender and recipient policy for relayed mail."""


class SenderPolicy:
    """Blocked sender domains and the recipient suppression list."""

    def __init__(self, blocked_domains=(), suppressed=()):
        self._blocked = {d.lower() for d in blocked_domains}
        self._suppressed = {a.lower() for a in suppressed}

    def allows(self, sender: str) -> bool:
        domain = sender.rsplit("@", 1)[-1].lower()
        return "@" in sender and domain not in self._blocked

    def deliverable(self, recipients) -> list[str]:
        """Normalised, de-duplicated recipients minus suppressed addresses."""
        seen: set[str] = set()
        out: list[str] = []
        for address in recipients:
            norm = address.strip().lower()
            if not norm or norm in seen or norm in self._suppressed:
                continue
            seen.add(norm)
            out.append(norm)
        return out
