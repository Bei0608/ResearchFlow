from copy import deepcopy

from app.evaluation.gates import (
    GateService, InMemoryGateRepository, evaluate_rules,
)
from app.evaluation.reporting import InMemoryReportingRepository
from tests.unit.test_reporting import reporting_snapshot


RULES = [
    {"rule_id":"absolute","source":"program","namespace_key":"quality@1.0",
     "metric_key":"correct","kind":"absolute_min","min_value":0.4},
    {"rule_id":"regression","source":"program","namespace_key":"quality@1.0",
     "metric_key":"correct","kind":"max_regression","max_drop":0.1},
]


def complete_snapshot(run_id: str, correct_values=(1.0, 0.0)) -> dict:
    value=reporting_snapshot();value["run"]["run_id"]=run_id
    value["cases"]=value["cases"][:2]
    value["program_metrics"]=[
        {"case_result_id":f"cr-{index+1}","evaluator_key":"quality",
         "evaluator_version":"1.0","metric_key":"correct","value":score}
        for index,score in enumerate(correct_values)
    ]
    value["reviews"]=[];value["human_dimensions"]=[];value["human_scores"]=[]
    return value


def test_gate_rules_pass_fail_and_incomplete() -> None:
    from app.evaluation.reporting import build_summary
    baseline=build_summary(complete_snapshot("baseline",(1.0,1.0)))
    candidate=build_summary(complete_snapshot("candidate",(1.0,0.0)))
    status,results=evaluate_rules(candidate,baseline,RULES)
    assert status=="failed"
    assert [x["status"] for x in results["rules"]]==["passed","failed"]
    status,results=evaluate_rules(candidate,None,RULES)
    assert status=="incomplete"
    assert all(x["reason"]=="应用尚未设置活动Baseline" for x in results["rules"])
    missing=deepcopy(candidate);missing["program_metrics"][0]["missing_count"]=1
    status,_=evaluate_rules(missing,baseline,[RULES[0]])
    assert status=="incomplete"


def test_human_gate_requires_complete_reviews() -> None:
    from app.evaluation.reporting import build_summary
    candidate=build_summary(reporting_snapshot())
    baseline=deepcopy(candidate);baseline["run"]["run_id"]="baseline"
    human=candidate["human_metrics"][0]
    rule={"rule_id":"human-min","source":"human","namespace_key":human["namespace_key"],
          "metric_key":human["metric_key"],"kind":"absolute_min","min_value":3}
    status,results=evaluate_rules(candidate,baseline,[rule])
    assert status=="incomplete"
    assert "样本不完整" in results["rules"][0]["reason"] or "尚未完成" in results["rules"][0]["reason"]


def test_gate_service_is_repeatable() -> None:
    gates=InMemoryGateRepository();reporting=InMemoryReportingRepository();owner="owner"
    for run_id in ("baseline","candidate"):
        gates.seed_run(run_id,"app","ws",owner)
    reporting.seed_snapshot("baseline",owner,complete_snapshot("baseline"))
    reporting.seed_snapshot("candidate",owner,complete_snapshot("candidate"))
    gates.set_baseline("app","baseline",owner)
    policy=gates.create_policy("ws","release","1.0",RULES,owner)
    gates.publish_policy(policy.policy_id,owner)
    service=GateService(gates,reporting)
    first=service.evaluate("candidate",policy.policy_id,owner)
    second=service.evaluate("candidate",policy.policy_id,owner)
    assert first.status==second.status=="passed"
    assert first.results==second.results
    assert first.gate_evaluation_id!=second.gate_evaluation_id
