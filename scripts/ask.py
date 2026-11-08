import argparse

from app.rag.qa import answer_question


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="基于本地论文知识库回答问题",
    )

    parser.add_argument(
        "question",
        type=str,
        help="需要回答的问题",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="提供给聊天模型的论文片段数量",
    )

    return parser


def main() -> None:
    parser = create_argument_parser()
    arguments = parser.parse_args()

    result = answer_question(
        question=arguments.question,
        top_k=arguments.top_k,
    )

    print("=" * 80)
    print(f"问题：{result.question}")
    print("=" * 80)
    print(result.answer)

    print("=" * 80)
    print("本次检索来源：")

    for index, chunk in enumerate(
        result.retrieved_chunks,
        start=1,
    ):
        print(f"[资料{index}] " f"{chunk.source_file}，" f"第{chunk.page_number}页，" f"相似度={chunk.score:.6f}")


if __name__ == "__main__":
    main()
