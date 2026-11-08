import argparse
import logging
from uuid import uuid4

from app.workflows import (
    DEFAULT_MIN_SCORE,
    DEFAULT_TOP_K,
    run_research_workflow,
)


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="运行ResearchFlow显式论文研究工作流",
    )
    parser.add_argument(
        "question",
        type=str,
        help="需要依据论文证据回答的问题",
    )
    parser.add_argument(
        "--thread-id",
        type=str,
        default=None,
        help="工作流会话ID，不提供时自动生成",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="向量检索返回数量",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=DEFAULT_MIN_SCORE,
        help="证据最低余弦相似度",
    )

    return parser


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format=(
            "%(asctime)s "
            "%(levelname)s "
            "%(name)s "
            "%(message)s"
        ),
    )
    logging.getLogger("researchflow").setLevel(logging.INFO)


def main() -> None:
    configure_logging()
    parser = create_argument_parser()
    arguments = parser.parse_args()
    thread_id = arguments.thread_id or uuid4().hex

    result = run_research_workflow(
        question=arguments.question,
        thread_id=thread_id,
        top_k=arguments.top_k,
        min_score=arguments.min_score,
    )

    print("ResearchFlow LangGraph研究工作流")
    print(f"会话ID：{thread_id}")
    print(
        "执行节点："
        + " -> ".join(result["executed_nodes"])
    )
    print(f"工作流分支：{result['route']}")
    print(f"有效证据数：{len(result['evidence'])}")

    if result.get("error"):
        print(f"内部错误类型：{result['error']}")

    print("\n最终答案：")
    print(result["answer"])

    if result["citations"]:
        print("\n引用来源：")

        for citation in result["citations"]:
            print(f"- {citation}")


if __name__ == "__main__":
    main()
