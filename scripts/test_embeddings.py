from math import isfinite

from app.rag.embeddings import (
    EMBEDDING_DIMENSIONS,
    get_embedding_model,
)

DOCUMENT_TEXTS = [
    "RT-1是一种用于真实世界机器人控制的Transformer模型。",
    "PaLM-E将连续的传感器信息接入大型语言模型。",
]

QUERY_TEXT = "视觉语言模型如何控制机器人？"


def validate_vector(vector: list[float]) -> None:
    """检查向量维度和数值是否合法。"""
    assert len(vector) == EMBEDDING_DIMENSIONS
    assert all(isfinite(value) for value in vector)


def main() -> None:
    embedding_model = get_embedding_model()

    print("正在测试文档Embedding……")
    document_vectors = embedding_model.embed_documents(DOCUMENT_TEXTS)

    print("正在测试查询Embedding……")
    query_vector = embedding_model.embed_query(QUERY_TEXT)

    assert len(document_vectors) == len(DOCUMENT_TEXTS)

    for vector in document_vectors:
        validate_vector(vector)

    validate_vector(query_vector)

    print("Embedding测试成功")
    print(f"文档向量数量：{len(document_vectors)}")
    print(f"向量维度：{len(query_vector)}")
    print(f"查询向量前5维：{query_vector[:5]}")


if __name__ == "__main__":
    main()
