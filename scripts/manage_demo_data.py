import argparse
import json
from pathlib import Path

from app.demo_data import (
    DEFAULT_INSTALL_ROOT,
    DemoDataError,
    install_demo_bundle,
    reset_demo_bundle,
    verify_demo_bundle,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="验证、安装或安全重置ResearchFlow原创演示数据",
    )
    parser.add_argument(
        "action",
        choices=("verify", "install", "reset"),
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_INSTALL_ROOT,
        help="install/reset命名空间，默认runtime/demo",
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    try:
        if arguments.action == "verify":
            result = verify_demo_bundle().to_dict()
        elif arguments.action == "install":
            result = install_demo_bundle(arguments.target).to_dict()
        else:
            result = reset_demo_bundle(arguments.target).to_dict()
    except DemoDataError as exc:
        raise SystemExit(f"演示数据操作失败：{exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
