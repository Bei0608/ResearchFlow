import argparse

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)

from app.agent.research_agent import run_research_agent


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="运行ResearchFlow论文研究Agent",
    )

    parser.add_argument(
        "question",
        type=str,
        help="需要Agent处理的问题",
    )

    parser.add_argument(
        "--thread-id",
        type=str,
        default="default",
        help="用于保存和恢复会话状态的ID",
    )

    parser.add_argument(
        "--user-id",
        type=str,
        default="local-user",
        help="用于隔离长期记忆的用户ID",
    )

    return parser


def print_agent_trajectory(messages: list) -> None:
    """展示Agent本次运行的消息轨迹。"""
    print("\nAgent执行轨迹：")

    for index, message in enumerate(messages, start=1):
        print("-" * 80)
        print(f"步骤：{index}")
        print(f"消息类型：{type(message).__name__}")

        if isinstance(message, HumanMessage):
            print(f"用户输入：{message.content}")

        elif isinstance(message, AIMessage):
            if message.tool_calls:
                print("模型决定调用工具：")

                for tool_call in message.tool_calls:
                    print(f"工具名称：{tool_call['name']}")
                    print(f"工具参数：{tool_call['args']}")
            elif message.content:
                print(f"模型输出：{message.content}")

        elif isinstance(message, ToolMessage):
            tool_result = str(message.content)
            preview = tool_result[:800]

            print(f"工具名称：{message.name}")
            print(f"工具结果预览：{preview}")

            if len(tool_result) > len(preview):
                print("……工具结果已截断")


def main() -> None:
    parser = create_argument_parser()
    arguments = parser.parse_args()

    result = run_research_agent(
        question=arguments.question,
        thread_id=arguments.thread_id,
        user_id=arguments.user_id,
    )

    messages = result["messages"]

    print_agent_trajectory(messages)

    print("\n" + "=" * 80)
    print("最终答案：")
    print(messages[-1].content)


if __name__ == "__main__":
    main()
