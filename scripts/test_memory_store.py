from uuid import uuid4
import sys

from app.memory import get_postgres_store


def main() -> None:
    """验证PostgreSQL长期记忆的增删改查能力。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    store = get_postgres_store()

    namespace = (
        "researchflow",
        "users",
        "test-user",
        "memories",
    )

    memory_id = uuid4().hex

    memory_value = {
        "category": "response_preference",
        "content": "回答时先给结论，再解释实现细节",
    }

    print("1. 写入测试记忆")

    store.put(
        namespace=namespace,
        key=memory_id,
        value=memory_value,
    )

    print(f"memory_id：{memory_id}")

    print("\n2. 根据memory_id读取记忆")

    item = store.get(
        namespace=namespace,
        key=memory_id,
    )

    if item is None:
        raise RuntimeError("没有读取到刚刚写入的记忆")

    print(f"namespace：{item.namespace}")
    print(f"key：{item.key}")
    print(f"value：{item.value}")

    print("\n3. 查询当前命名空间中的记忆")

    search_results = store.search(
        namespace,
        limit=10,
    )

    print(f"查询结果数量：{len(search_results)}")

    for result in search_results:
        print(
            {
                "memory_id": result.key,
                "value": result.value,
            }
        )

    print("\n4. 删除测试记忆")

    store.delete(
        namespace=namespace,
        key=memory_id,
    )

    deleted_item = store.get(
        namespace=namespace,
        key=memory_id,
    )

    if deleted_item is not None:
        raise RuntimeError("测试记忆删除失败")

    print("测试记忆已删除")
    print("\nPostgreSQL Store测试成功")


if __name__ == "__main__":
    main()
