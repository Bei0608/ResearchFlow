import json

from app.tools import MEMORY_TOOLS


def main() -> None:
    """查看模型实际能够看到的记忆工具定义。"""
    for memory_tool in MEMORY_TOOLS:
        print("=" * 80)
        print(f"工具名称：{memory_tool.name}")
        print(f"工具说明：{memory_tool.description}")
        print("模型可见参数：")

        schema = memory_tool.tool_call_schema.model_json_schema()

        print(
            json.dumps(
                schema,
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
