from secretgate.models import BuildRequest
from secretgate.scanner import CredentialScanner


def scan(files):
    return CredentialScanner().scan(BuildRequest("b-1", "release-bot", files))


def test_clean_build_has_no_findings():
    report = scan({"src/app.py": "print('hello')\n"})
    assert report.findings == []
    assert report.highest_severity() == "none"


def test_aws_key_is_critical_and_masked():
    report = scan({"deploy/env.sh": "export KEY=AKIAABCDEFGHIJKLMNOP\n"})
    assert report.highest_severity() == "critical"
    finding = report.findings[0]
    assert finding.rule_id == "aws-access-key"
    assert finding.line == 1
    assert "ABCDEFGHIJKLMNOP" not in finding.snippet


def test_password_assignment_is_high():
    report = scan({"config/db.ini": "[db]\npassword = 'hunter22'\n"})
    assert report.highest_severity() == "high"
    assert report.findings[0].line == 2


def test_docs_are_ignored():
    report = scan({"docs/setup.md": "-----BEGIN RSA PRIVATE KEY-----\n"})
    assert report.findings == []
