"""Data types shared by the scanner, the build runner and the auditor."""
from dataclasses import dataclass, field

SEVERITY_RANK = {"none": 0, "low": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class BuildRequest:
    """A build taken from the request queue, with the files it would publish."""

    build_id: str
    submitter: str
    files: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    path: str
    line: int
    snippet: str


@dataclass
class ScanReport:
    build_id: str
    submitter: str
    findings: list = field(default_factory=list)

    def highest_severity(self):
        if not self.findings:
            return "none"
        return max((f.severity for f in self.findings), key=SEVERITY_RANK.__getitem__)

    def first_with_severity(self, severity):
        for finding in self.findings:
            if finding.severity == severity:
                return finding
        return None


@dataclass(frozen=True)
class Verdict:
    build_id: str
    allowed: bool
    level: str
    reason: str = ""
