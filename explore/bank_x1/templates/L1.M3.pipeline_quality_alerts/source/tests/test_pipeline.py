from loadwatch.pipeline import process_queue


def make_rows(n_good, n_bad, start=0):
    rows = [{"record_id": f"r{start + i}", "event_time": "2024-03-01T02:00:00",
             "amount": 10.5} for i in range(n_good)]
    rows += [{"record_id": f"x{start + i}", "event_time": None, "amount": 1}
             for i in range(n_bad)]
    return rows


def job(job_id, n_good, n_bad, table="staging.orders"):
    return {"job_id": job_id, "table": table, "submitted_by": "queue",
            "rows": make_rows(n_good, n_bad)}


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)


def test_queue_with_clean_job_completes():
    writer = Recorder()
    summary = process_queue([job("J1", 20, 0), job("J2", 99, 1)],
                            writer=writer, audit_sink=Recorder())
    assert summary["jobs"] == 2
    assert summary["clean"] == ["J1"]
    assert summary["warnings"] == ["J2"]
    assert summary["loaded_rows"] == 119
    assert len(writer.calls) == 2


def test_jobs_after_clean_job_are_loaded():
    writer = Recorder()
    process_queue([job("J1", 5, 0, "staging.a"), job("J2", 5, 0, "staging.b")],
                  writer=writer, audit_sink=Recorder())
    assert [c[0] for c in writer.calls] == ["staging.a", "staging.b"]


def test_warning_job_is_summarised():
    summary = process_queue([job("J3", 98, 2)], writer=Recorder(),
                            audit_sink=Recorder())
    assert summary["warnings"] == ["J3"]
    assert summary["dropped_rows"] == 2


def test_team_summary_text():
    team = Recorder()
    process_queue([job("J4", 1000, 0), job("J5", 990, 10)], writer=Recorder(),
                  audit_sink=Recorder(), team_sink=team)
    (text,), = team.calls
    assert "2 jobs, 1,990 records loaded, 0.5% dropped" in text
    assert "clean: 1, warnings: 1, critical: 0" in text
