from publisher.formatting import format_outcome, format_summary, short_digest


def test_short_digest():
    assert short_digest("sha256:" + "ab" * 32) == "sha256:abababababab"
    assert short_digest(None) == "-"


def test_format_outcomes_and_summary():
    outcomes = [
        {"request_id": "r-1", "status": "published", "artifact": "builds/app:1.0.0",
         "digest": "sha256:" + "0" * 64, "changed": False},
        {"request_id": "r-2", "status": "rejected", "reason": "bad tag"},
    ]
    assert format_outcome(outcomes[0]) == "[r-1] published builds/app:1.0.0 sha256:000000000000 (unchanged)"
    assert format_summary(outcomes).splitlines()[-1] == "total: published=1, rejected=1"
