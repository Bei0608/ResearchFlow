from app.storage.milvus import (
    get_milvus_collection_name,
    get_milvus_uri,
    get_milvus_vector_store,
)


def main() -> None:
    vector_store = get_milvus_vector_store()

    print("Milvus向量存储初始化成功")
    print(f"连接地址：{get_milvus_uri()}")
    print(f"集合名称：{get_milvus_collection_name()}")
    print(f"向量存储类型：{type(vector_store).__name__}")


if __name__ == "__main__":
    main()
