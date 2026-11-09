from setpoints import envelope, managed_client

ENVELOPE = envelope.load_envelope([
    ("boiler-2.temp", 60, 180, "degC"),
    ("feed-pump-1.speed", 600, 3000, "rpm"),
])


def run(queue, team_post=None):
    writes, alerts = [], []
    results = managed_client.process_queue(
        queue, envelope=ENVELOPE,
        writer=lambda tag, value: writes.append((tag, value)),
        audit_sink=lambda channel, alert: alerts.append((channel, alert)),
        team_post=team_post)
    return results, writes, alerts


def req(rid, tag, value):
    return {"request_id": rid, "tag": tag, "value": value}


def test_in_range_setpoint_is_written():
    results, writes, _ = run([req("SP-1", "boiler-2.temp", 120.0)])
    assert writes == [("boiler-2.temp", 120.0)]
    assert results[0]["status"] == managed_client.APPLIED


def test_out_of_range_setpoint_is_not_written():
    results, writes, _ = run([req("SP-2", "boiler-2.temp", 240.0)])
    assert writes == []
    assert results[0]["status"] == managed_client.REJECTED


def test_near_limit_setpoint_is_written():
    results, writes, _ = run([req("SP-3", "boiler-2.temp", 176.5)])
    assert writes == [("boiler-2.temp", 176.5)]
    assert results[0] == {"request_id": "SP-3", "status": managed_client.APPLIED,
                          "severity": "warning"}


def test_mixed_batch_completes_in_order():
    queue = [req("SP-4", "feed-pump-1.speed", 1500),
             req("SP-5", "feed-pump-1.speed", 2950),
             req("SP-6", "boiler-2.temp", 20.0),
             req("SP-7", "boiler-2.temp", 90.0)]
    results, writes, _ = run(queue)
    assert [r["status"] for r in results] == ["applied", "applied", "rejected", "applied"]
    assert writes == [("feed-pump-1.speed", 1500.0), ("feed-pump-1.speed", 2950.0),
                      ("boiler-2.temp", 90.0)]


def test_team_summary_is_optional():
    posts = []
    run([req("SP-8", "boiler-2.temp", 100.0)], team_post=posts.append)
    assert posts == ["setpoint batch: 1 applied, 0 rejected (100% accepted)"]
