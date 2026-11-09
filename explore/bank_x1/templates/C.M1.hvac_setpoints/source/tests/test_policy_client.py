import pytest
from conftest import StubTransport, make_change

from setpoints import Decision, EnergyPolicyClient, PolicyServiceError, PolicyTimeout
from setpoints.units import c_to_f, f_to_c, format_temp, round_to_controller


def test_decisions_are_parsed():
    client = EnergyPolicyClient(StubTransport({"a": "ALLOW", "b": "hold"}))
    assert client.evaluate(make_change("a")) is Decision.ALLOW
    assert client.evaluate(make_change("b")) is Decision.HOLD


def test_transport_timeout_becomes_policy_timeout():
    client = EnergyPolicyClient(StubTransport({"a": "timeout"}), timeout_s=1.5)
    with pytest.raises(PolicyTimeout) as info:
        client.evaluate(make_change("a"))
    assert info.value.change_id == "a"


def test_unknown_decision_is_rejected():
    client = EnergyPolicyClient(StubTransport({"a": "maybe"}))
    with pytest.raises(PolicyServiceError):
        client.evaluate(make_change("a"))


def test_unit_helpers():
    assert c_to_f(20.0) == 68.0
    assert f_to_c(68.0) == 20.0
    assert round_to_controller(21.2) == 21.0
    assert format_temp(21.0, "F") == "69.8°F"
