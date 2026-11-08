import os
from pathlib import Path

from dotenv import load_dotenv
from pymilvus import MilvusClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"


def main() -> None:
    load_dotenv(ENV_FILE, override=False)

    milvus_uri = os.getenv(
        "MILVUS_URI",
        "http://localhost:19530",
    )

    print(f"正在连接 Milvus：{milvus_uri}")

    client = MilvusClient(uri=milvus_uri)

    try:
        collections = client.list_collections()

        print("Milvus 连接成功")
        print(f"现有集合数量：{len(collections)}")
        print(f"现有集合：{collections}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
