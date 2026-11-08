import argparse
import json
from pathlib import Path

from app.evaluation.catalog import get_evaluation_catalog_repository
from app.evaluation.catalog_importer import (
    import_dataset_payload,
    import_rubric_payload,
)


def _json_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON顶层必须是对象：{path}")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将版本化评测集和量表幂等导入PostgreSQL",
    )
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--rubric", type=Path)
    arguments = parser.parse_args()
    if arguments.dataset is None and arguments.rubric is None:
        parser.error("--dataset和--rubric至少提供一个")
    return arguments


def main() -> None:
    arguments = parse_args()
    repository = get_evaluation_catalog_repository()
    result: dict[str, dict] = {}
    if arguments.dataset is not None:
        record = import_dataset_payload(
            repository,
            workspace_id=arguments.workspace_id,
            user_id=arguments.user_id,
            payload=_json_object(arguments.dataset),
        )
        result["dataset"] = {
            "dataset_id": record.dataset_id,
            "dataset_version_id": record.dataset_version_id,
            "version": record.version,
            "content_hash": record.content_hash,
        }
    if arguments.rubric is not None:
        record = import_rubric_payload(
            repository,
            workspace_id=arguments.workspace_id,
            user_id=arguments.user_id,
            payload=_json_object(arguments.rubric),
        )
        result["rubric"] = {
            "rubric_id": record.rubric_id,
            "rubric_version_id": record.rubric_version_id,
            "version": record.version,
            "content_hash": record.content_hash,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
