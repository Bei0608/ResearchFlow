import json
from pathlib import Path

import pytest

from app.demo_data import (
    PROJECT_ROOT,
    DemoDataError,
    install_demo_bundle,
    reset_demo_bundle,
    verify_demo_bundle,
)


def test_bundled_demo_data_is_consistent_and_has_no_human_scores() -> None:
    report = verify_demo_bundle()

    assert report.environment == "demo"
    assert report.file_count == 8
    assert report.case_count == 4
    assert report.metric_case_count == 4
    assert report.contains_human_scores is False
    assert len(report.bundle_sha256) == 64


def test_demo_install_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "demo-runtime"

    first = install_demo_bundle(target)
    second = install_demo_bundle(target)

    assert first.status == "installed"
    assert second.status == "unchanged"
    assert first.bundle_sha256 == second.bundle_sha256
    assert first.managed_file_count == second.managed_file_count == 8


def test_demo_reset_preserves_unmanaged_files(tmp_path: Path) -> None:
    target = tmp_path / "demo-runtime"
    install_demo_bundle(target)
    unmanaged = target / "keep-me.txt"
    unmanaged.write_text("user-owned", encoding="utf-8")

    result = reset_demo_bundle(target)

    assert result.status == "reset"
    assert result.managed_file_count == 8
    assert unmanaged.read_text(encoding="utf-8") == "user-owned"
    assert reset_demo_bundle(target).status == "not_installed"


def test_demo_verification_rejects_program_metrics_labeled_human(
    tmp_path: Path,
) -> None:
    target = tmp_path / "bundle"
    install_demo_bundle(target)
    metrics_path = target / "evaluations/demo/program_metrics.json"
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    payload["source"] = "human"
    metrics_path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(DemoDataError, match="source=program"):
        verify_demo_bundle(target)


def test_demo_install_rejects_filesystem_root() -> None:
    filesystem_root = Path(Path.cwd().anchor)

    with pytest.raises(DemoDataError, match="文件系统根目录"):
        install_demo_bundle(filesystem_root)


def test_v1_compatibility_baseline_distinguishes_program_and_human() -> None:
    baseline_path = (
        PROJECT_ROOT / "evaluations/baselines/v1_compatibility.json"
    )
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))

    assert payload["environment"] == "local_integration"
    assert payload["program_verification"]["source"] == "program"
    assert payload["program_verification"]["test_suite"]["passed"] == 85
    assert payload["human_evaluation"] is None
