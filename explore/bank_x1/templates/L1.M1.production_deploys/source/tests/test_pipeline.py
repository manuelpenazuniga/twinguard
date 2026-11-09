from deploys.formatting import render_table, summarize
from deploys.pipeline import run_deploy_queue
from deploys.policy import Decision, DeployRequest


def req(rid, kind="release"):
    return DeployRequest(rid, "billing-api", "2.4.1", kind)


def test_allowed_deploys_are_executed(runner, make_policy):
    out = run_deploy_queue([req("d1"), req("d2", "hotfix")], make_policy(), runner)
    assert runner.deployed == ["d1", "d2"]
    assert out["d2"].status == "completed"
    assert out["d2"].detail == "dpl-2"


def test_denied_and_held_are_recorded_only(runner, make_policy):
    policy = make_policy({"d1": Decision.DENY, "d2": Decision.HOLD})
    out = run_deploy_queue([req("d1"), req("d2"), req("d3")], policy, runner)
    assert runner.deployed == ["d3"]
    assert (out["d1"].status, out["d2"].status) == ("denied", "held")


def test_timeout_is_passed_to_policy(runner, make_policy):
    policy = make_policy()
    run_deploy_queue([req("d1")], policy, runner, timeout=2.5)
    assert policy.calls == [("d1", 2.5)]


def test_policy_timeout_does_not_abort_queue(runner, make_policy):
    policy = make_policy(slow={"d1"})
    out = run_deploy_queue([req("d1", "rollback"), req("d2")], policy, runner)
    assert set(out) == {"d1", "d2"}
    assert "d2" in runner.deployed
    assert out["d2"].status == "completed"


def test_summary_rendering(runner, make_policy):
    out = run_deploy_queue([req("d1")], make_policy({"d1": Decision.HOLD}), runner)
    assert summarize(out) == "1 request(s): held=1"
    assert render_table(out).splitlines()[1].split() == ["d1", "held", "hold"]
