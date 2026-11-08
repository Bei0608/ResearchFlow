import argparse
from uuid import uuid4

from app.agent.research_agent import run_research_agent
import logging


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="与ResearchFlow Agent进行多轮对话",
    )

    parser.add_argument(
        "--thread-id",
        type=str,
        default=None,
        help="会话ID，不提供时自动生成",
    )

    parser.add_argument(
        "--user-id",
        type=str,
        default="local-user",
        help="用户ID，用于隔离跨会话长期记忆",
    )

    return parser


def configure_logging() -> None:
    """启用ResearchFlow运行日志。"""
    logging.basicConfig(
        level=logging.WARNING,
        format=("%(asctime)s " "%(levelname)s " "%(name)s " "%(message)s"),
    )

    logging.getLogger("researchflow").setLevel(logging.INFO)


def main() -> None:
    configure_logging()
    parser = create_argument_parser()
    arguments = parser.parse_args()

    thread_id = arguments.thread_id or uuid4().hex
    user_id = arguments.user_id

    print("ResearchFlow Agent")
    print(f"当前用户ID：{user_id}")
    print(f"当前会话ID：{thread_id}")
    print("输入 /exit 结束对话")
    print("=" * 80)

    while True:
        question = input("\n你：").strip()

        if question.lower() == "/exit":
            print("对话已结束")
            break

        if not question:
            continue

        result = run_research_agent(
            question=question,
            thread_id=thread_id,
            user_id=user_id,
        )

        final_message = result["messages"][-1]

        print("\nAgent：")
        print(final_message.content)


if __name__ == "__main__":
    main()
