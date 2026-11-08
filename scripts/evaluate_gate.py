import argparse
import json
from pathlib import Path

from app.evaluation.gates import GateService, get_gate_repository, evaluate_rules
from app.evaluation.reporting import get_reporting_repository


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = PROJECT_ROOT / "evaluations/demo/gate_check.json"
EXIT_CODES = {"passed": 0, "failed": 2, "incomplete": 3}


def main() -> None:
    parser = argparse.ArgumentParser(description="执行ResearchFlow质量门禁")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", type=Path, nargs="?", const=DEFAULT_FIXTURE)
    mode.add_argument("--run-id")
    parser.add_argument("--policy-id")
    parser.add_argument("--user-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.fixture is not None:
        payload = json.loads(args.fixture.read_text(encoding="utf-8"))
        status, results = evaluate_rules(
            payload["candidate"], payload.get("baseline"), payload["policy"]["rules"]
        )
        expected = payload.get("expected_status")
        if expected and status != expected:
            print(f"夹具期望{expected}，实际{status}")
            raise SystemExit(1)
    else:
        if not args.policy_id or not args.user_id:
            parser.error("数据库模式需要--policy-id和--user-id")
        item = GateService(get_gate_repository(), get_reporting_repository()).evaluate(
            args.run_id, args.policy_id, args.user_id
        )
        if item is None:
            print("运行或已发布Gate Policy不存在")
            raise SystemExit(1)
        status, results = item.status, item.results

    document = {"status": status, "results": results}
    text = json.dumps(document, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    raise SystemExit(EXIT_CODES[status])


if __name__ == "__main__":
    main()
