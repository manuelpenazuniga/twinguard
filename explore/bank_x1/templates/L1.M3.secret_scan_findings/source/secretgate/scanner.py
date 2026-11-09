"""Credential pattern scanner run over every file of a submitted build."""
import re

from secretgate.models import Finding, ScanReport
from secretgate.textfmt import mask_secret, truncate

DEFAULT_RULES = (
    ("aws-access-key", "critical", r"\bAKIA[0-9A-Z]{16}\b"),
    ("private-key-block", "critical", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ("hardcoded-password", "high", r"(?i)\bpassword\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
    ("placeholder-token", "low", r"(?i)\btoken\s*[:=]\s*['\"]?changeme"),
)


class CredentialScanner:
    """Matches each line of each file against a list of credential rules."""

    def __init__(self, rules=DEFAULT_RULES, ignored_prefixes=("docs/",)):
        self.rules = [(rule_id, severity, re.compile(pattern))
                      for rule_id, severity, pattern in rules]
        self.ignored_prefixes = tuple(ignored_prefixes)

    def scan(self, request):
        report = ScanReport(build_id=request.build_id, submitter=request.submitter)
        for path in sorted(request.files):
            if path.startswith(self.ignored_prefixes):
                continue
            report.findings.extend(self._scan_file(path, request.files[path]))
        return report

    def _scan_file(self, path, text):
        findings = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            for rule_id, severity, pattern in self.rules:
                match = pattern.search(line)
                if match is None:
                    continue
                snippet = truncate(line.replace(match.group(0), mask_secret(match.group(0))))
                findings.append(Finding(rule_id, severity, path, lineno, snippet))
        return findings
