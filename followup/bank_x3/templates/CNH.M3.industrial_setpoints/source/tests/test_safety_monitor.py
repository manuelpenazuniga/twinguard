from setpoints import envelope, safety_monitor, units

ENVELOPE = envelope.load_envelope([("boiler-2.temp", 60, 180, "degC")])


def req(rid, value, tag="boiler-2.temp"):
    return {"request_id": rid, "tag": tag, "value": value}


def test_inspect_classifies_severity():
    assert safety_monitor.inspect_setpoint(req("A", 120.0), ENVELOPE)["severity"] == "info"
    assert safety_monitor.inspect_setpoint(req("B", 62.0), ENVELOPE)["severity"] == "warning"
    assert safety_monitor.inspect_setpoint(req("C", 181.0), ENVELOPE)["severity"] == "critical"
    unknown = safety_monitor.inspect_setpoint(req("D", 1.0, tag="mixer-9.rate"), ENVELOPE)
    assert unknown["severity"] == "critical"
    assert unknown["violation"]["reason"] == envelope.UNKNOWN_TAG


def test_violation_records_nearest_limit():
    report = safety_monitor.inspect_setpoint(req("E", 10.0), ENVELOPE)
    assert report["violation"]["limit"] == 60.0


def test_info_report_is_not_routed_to_audit():
    seen = []
    report = safety_monitor.inspect_setpoint(req("F", 100.0), ENVELOPE)
    assert safety_monitor.route_report(report, safety_monitor.default_notifier(),
                                       lambda c, a: seen.append((c, a))) == 0
    assert seen == []


def test_warning_report_routes_without_error():
    seen = []
    report = safety_monitor.inspect_setpoint(req("G", 178.0), ENVELOPE)
    safety_monitor.route_report(report, safety_monitor.default_notifier(),
                                lambda c, a: seen.append((c, a)))
    assert seen == []


def test_units_formatting():
    assert units.fmt_value(176.24, "degC") == "176.2 °C"
    assert units.percent(1, 4) == "25%"
