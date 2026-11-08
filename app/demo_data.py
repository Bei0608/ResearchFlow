from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path("data/demo/manifest.json")
DEFAULT_INSTALL_ROOT = PROJECT_ROOT / "runtime/demo"
MARKER_NAME = ".researchflow-demo-install.json"


class DemoDataError(ValueError):
    """Raised when the bundled demo data is unsafe or inconsistent."""


@dataclass(frozen=True)
class DemoBundleReport:
    bundle_id: str
    environment: str
    file_count: int
    case_count: int
    metric_case_count: int
    contains_human_scores: bool
    bundle_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DemoInstallResult:
    status: str
    target: str
    managed_file_count: int
    bundle_sha256: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DemoDataError(f"无法读取演示JSON：{path}") from exc
    if not isinstance(value, dict):
        raise DemoDataError(f"演示JSON顶层必须是对象：{path}")
    return value


def _safe_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise DemoDataError(f"演示清单包含不安全路径：{value}")
    return path


def _resolved_child(root: Path, relative: Path) -> Path:
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise DemoDataError(f"路径逃出演示命名空间：{relative}")
    return resolved


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bundle_sha256(
    project_root: Path,
    relative_paths: list[Path],
) -> str:
    digest = hashlib.sha256()
    for relative in sorted(relative_paths, key=lambda item: item.as_posix()):
        path = _resolved_child(project_root, relative)
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _require_demo_environment(
    name: str,
    payload: dict[str, Any],
) -> None:
    if payload.get("environment") != "demo":
        raise DemoDataError(f"{name} 必须明确标记 environment=demo")


def _require_unique_case_ids(
    name: str,
    rows: Any,
) -> set[str]:
    if not isinstance(rows, list) or not rows:
        raise DemoDataError(f"{name} 必须包含非空案例列表")
    case_ids: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(
            row.get("case_id"), str
        ):
            raise DemoDataError(f"{name} 包含无效 case_id")
        case_ids.append(row["case_id"])
    if len(case_ids) != len(set(case_ids)):
        raise DemoDataError(f"{name} 包含重复 case_id")
    return set(case_ids)


def _load_manifest(project_root: Path) -> tuple[dict[str, Any], list[Path]]:
    manifest = _read_json(_resolved_child(project_root, MANIFEST_PATH))
    _require_demo_environment("manifest", manifest)
    if manifest.get("contains_private_data") is not False:
        raise DemoDataError("演示清单必须声明 contains_private_data=false")
    if manifest.get("contains_human_scores") is not False:
        raise DemoDataError("演示清单不得声明包含人工评分")
    bundle_id = manifest.get("bundle_id")
    if not isinstance(bundle_id, str) or not bundle_id.strip():
        raise DemoDataError("演示清单缺少 bundle_id")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise DemoDataError("演示清单必须包含文件列表")
    relative_paths = [_safe_relative_path(str(value)) for value in raw_files]
    if len(relative_paths) != len(set(relative_paths)):
        raise DemoDataError("演示清单包含重复文件")
    for relative in relative_paths:
        path = _resolved_child(project_root, relative)
        if not path.is_file():
            raise DemoDataError(f"演示清单文件不存在：{relative}")
    return manifest, relative_paths


def verify_demo_bundle(
    project_root: Path = PROJECT_ROOT,
) -> DemoBundleReport:
    """Validate the bundled demo without importing app/model settings."""
    project_root = project_root.resolve()
    manifest, relative_paths = _load_manifest(project_root)

    dataset = _read_json(
        _resolved_child(
            project_root,
            Path("evaluations/demo/evaluation_dataset.json"),
        )
    )
    rubric = _read_json(
        _resolved_child(project_root, Path("evaluations/demo/rubric.json"))
    )
    run = _read_json(
        _resolved_child(project_root, Path("evaluations/demo/agent_run.json"))
    )
    metrics = _read_json(
        _resolved_child(
            project_root,
            Path("evaluations/demo/program_metrics.json"),
        )
    )
    for name, payload in (
        ("evaluation_dataset", dataset),
        ("rubric", rubric),
        ("agent_run", run),
        ("program_metrics", metrics),
    ):
        _require_demo_environment(name, payload)

    dataset_cases = _require_unique_case_ids("dataset", dataset.get("cases"))
    run_cases = _require_unique_case_ids("run", run.get("results"))
    metric_cases = _require_unique_case_ids(
        "program_metrics",
        metrics.get("case_metrics"),
    )
    if dataset_cases != run_cases or dataset_cases != metric_cases:
        raise DemoDataError("数据集、运行和程序指标的 case_id 不一致")
    if run.get("run_id") != metrics.get("run_id"):
        raise DemoDataError("运行与程序指标的 run_id 不一致")
    if metrics.get("source") != "program":
        raise DemoDataError("程序指标必须标记 source=program")
    if metrics.get("human_metrics") is not None:
        raise DemoDataError("程序指标文件不得包含人工指标")
    if run.get("human_reviews") != [] or rubric.get("human_scores") != []:
        raise DemoDataError("演示包不得预填人工评分")
    if metrics.get("summary", {}).get("case_count") != len(dataset_cases):
        raise DemoDataError("程序指标汇总 case_count 不正确")

    known_sources = {
        path.name
        for path in relative_paths
        if path.parts[:3] == ("data", "demo", "knowledge")
    }
    for result in run["results"]:
        for evidence in result.get("evidence", []):
            if evidence.get("source_file") not in known_sources:
                raise DemoDataError(
                    "运行证据引用了清单外文件："
                    f"{evidence.get('source_file')}"
                )

    return DemoBundleReport(
        bundle_id=manifest["bundle_id"],
        environment=manifest["environment"],
        file_count=len(relative_paths),
        case_count=len(dataset_cases),
        metric_case_count=len(metric_cases),
        contains_human_scores=False,
        bundle_sha256=_bundle_sha256(project_root, relative_paths),
    )


def _load_install_marker(target: Path) -> dict[str, Any] | None:
    marker = target / MARKER_NAME
    if not marker.exists():
        return None
    return _read_json(marker)


def _validate_install_target(target: Path) -> Path:
    resolved = target.resolve()
    filesystem_root = Path(resolved.anchor).resolve()
    if resolved in {filesystem_root, PROJECT_ROOT.resolve()}:
        raise DemoDataError(
            "拒绝使用文件系统根目录或项目根目录作为demo命名空间"
        )
    return resolved


def _marker_is_current(target: Path, marker: dict[str, Any]) -> bool:
    managed_files = marker.get("managed_files")
    if not isinstance(managed_files, dict):
        return False
    for raw_relative, expected_hash in managed_files.items():
        relative = _safe_relative_path(raw_relative)
        path = _resolved_child(target, relative)
        if not path.is_file() or _file_sha256(path) != expected_hash:
            return False
    return True


def install_demo_bundle(
    target: Path = DEFAULT_INSTALL_ROOT,
    project_root: Path = PROJECT_ROOT,
) -> DemoInstallResult:
    """Install the verified fixture into one explicitly marked namespace."""
    project_root = project_root.resolve()
    target = _validate_install_target(target)
    report = verify_demo_bundle(project_root)
    manifest, relative_paths = _load_manifest(project_root)
    old_marker = _load_install_marker(target)
    if (
        old_marker
        and old_marker.get("bundle_id") == report.bundle_id
        and old_marker.get("bundle_sha256") == report.bundle_sha256
        and _marker_is_current(target, old_marker)
    ):
        return DemoInstallResult(
            status="unchanged",
            target=str(target),
            managed_file_count=len(relative_paths),
            bundle_sha256=report.bundle_sha256,
        )

    target.mkdir(parents=True, exist_ok=True)
    new_relative_names = {path.as_posix() for path in relative_paths}
    if old_marker:
        for raw_relative in old_marker.get("managed_files", {}):
            if raw_relative not in new_relative_names:
                obsolete = _resolved_child(
                    target,
                    _safe_relative_path(raw_relative),
                )
                if obsolete.is_file():
                    obsolete.unlink()

    managed_files: dict[str, str] = {}
    for relative in relative_paths:
        source = _resolved_child(project_root, relative)
        destination = _resolved_child(target, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        managed_files[relative.as_posix()] = _file_sha256(destination)

    marker_payload = {
        "schema_version": "1.0",
        "bundle_id": manifest["bundle_id"],
        "environment": "demo",
        "bundle_sha256": report.bundle_sha256,
        "managed_files": managed_files,
    }
    (target / MARKER_NAME).write_text(
        json.dumps(marker_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return DemoInstallResult(
        status="updated" if old_marker else "installed",
        target=str(target),
        managed_file_count=len(relative_paths),
        bundle_sha256=report.bundle_sha256,
    )


def reset_demo_bundle(
    target: Path = DEFAULT_INSTALL_ROOT,
) -> DemoInstallResult:
    """Delete only files named by a valid ResearchFlow demo marker."""
    target = _validate_install_target(target)
    marker = _load_install_marker(target)
    if marker is None:
        return DemoInstallResult(
            status="not_installed",
            target=str(target),
            managed_file_count=0,
            bundle_sha256=None,
        )
    if marker.get("environment") != "demo" or not str(
        marker.get("bundle_id", "")
    ).startswith("researchflow-"):
        raise DemoDataError("拒绝重置：目标缺少有效ResearchFlow demo标记")
    managed_files = marker.get("managed_files")
    if not isinstance(managed_files, dict):
        raise DemoDataError("拒绝重置：安装标记缺少 managed_files")

    removed = 0
    parents: set[Path] = set()
    for raw_relative in managed_files:
        relative = _safe_relative_path(raw_relative)
        path = _resolved_child(target, relative)
        if path.is_file():
            path.unlink()
            removed += 1
        parent = path.parent
        while parent != target and parent.is_relative_to(target):
            parents.add(parent)
            parent = parent.parent
    (target / MARKER_NAME).unlink()
    for parent in sorted(parents, key=lambda path: len(path.parts), reverse=True):
        try:
            parent.rmdir()
        except OSError:
            pass
    try:
        target.rmdir()
    except OSError:
        pass
    return DemoInstallResult(
        status="reset",
        target=str(target),
        managed_file_count=removed,
        bundle_sha256=marker.get("bundle_sha256"),
    )
