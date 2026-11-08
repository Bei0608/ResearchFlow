import argparse
import sys

from app.rag.retriever import (
    DEFAULT_TOP_K,
    retrieve_relevant_chunks,
)


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从Milvus中检索相关论文片段",
    )

    parser.add_argument(
        "query",
        type=str,
        help="需要检索的问题",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="返回的相关文本块数量",
    )

    return parser


def create_preview(
    text: str,
    max_length: int = 500,
) -> str:
    """压缩空白并生成便于终端查看的文本预览。"""
    normalized_text = " ".join(text.split())

    if len(normalized_text) <= max_length:
        return normalized_text

    return f"{normalized_text[:max_length]}..."


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = create_argument_parser()
    arguments = parser.parse_args()

    results = retrieve_relevant_chunks(
        query=arguments.query,
        top_k=arguments.top_k,
    )

    print(f"问题：{arguments.query}")
    print(f"返回结果：{len(results)}")

    for rank, result in enumerate(results, start=1):
        print("=" * 80)
        print(f"排名：{rank}")
        print(f"相似度：{result.score:.6f}")
        print(f"来源：{result.source_file}")
        print(f"页码：{result.page_number}")
        print(f"Chunk ID：{result.chunk_id}")
        print(f"内容：{create_preview(result.content)}")


if __name__ == "__main__":
    main()
