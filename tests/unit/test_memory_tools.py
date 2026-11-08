import json

import pytest
from langchain.tools import ToolRuntime
from langgraph.store.memory import InMemoryStore

from app.models import ResearchContext
from app.tools.memory_tools import (
    build_memory_namespace,
    delete_user_memory,
    list_user_memories,
    save_user_memory,
    update_user_memory,
)


def create_tool_runtime(
    store: InMemoryStore,
    user_id: str,
) -> ToolRuntime[ResearchContext]:
    """创建供记忆工具单元测试使用的运行环境。"""
    return ToolRuntime(
        state={
            "messages": [],
        },
        context=ResearchContext(
            user_id=user_id,
        ),
        config={},
        stream_writer=lambda chunk: None,
        tool_call_id="test-tool-call",
        store=store,
        tools=[],
    )


def call_save_memory(
    runtime: ToolRuntime[ResearchContext],
    category: str,
    content: str,
) -> dict:
    """调用被@tool包装前的保存函数。"""
    result = save_user_memory.func(
        category=category,
        content=content,
        runtime=runtime,
    )

    return json.loads(result)


def call_list_memories(
    runtime: ToolRuntime[ResearchContext],
):
    """调用被@tool包装前的查询函数。"""
    return list_user_memories.func(
        runtime=runtime,
    )


def call_update_memory(
    runtime: ToolRuntime[ResearchContext],
    memory_id: str,
    category: str,
    content: str,
) -> dict:
    """调用被@tool包装前的更新函数。"""
    result = update_user_memory.func(
        memory_id=memory_id,
        category=category,
        content=content,
        runtime=runtime,
    )

    return json.loads(result)


def call_delete_memory(
    runtime: ToolRuntime[ResearchContext],
    memory_id: str,
) -> dict:
    """调用被@tool包装前的删除函数。"""
    result = delete_user_memory.func(
        memory_id=memory_id,
        runtime=runtime,
    )

    return json.loads(result)


def test_memory_namespace_is_stable() -> None:
    """相同用户应始终得到相同的命名空间。"""
    first_namespace = build_memory_namespace(
        "bei",
    )
    second_namespace = build_memory_namespace(
        "bei",
    )

    assert first_namespace == second_namespace


def test_different_users_have_different_namespaces() -> None:
    """不同用户不能共享长期记忆命名空间。"""
    bei_namespace = build_memory_namespace(
        "bei",
    )
    alice_namespace = build_memory_namespace(
        "alice",
    )

    assert bei_namespace != alice_namespace


def test_raw_user_id_is_not_stored_in_namespace() -> None:
    """命名空间中不应直接包含原始用户ID。"""
    namespace = build_memory_namespace(
        "bei@example.com",
    )

    assert "bei@example.com" not in namespace
    assert namespace[:2] == (
        "researchflow",
        "users",
    )
    assert namespace[-1] == "memories"


def test_save_user_memory_stores_normalized_value() -> None:
    """保存工具应清理输入并写入当前用户空间。"""
    store = InMemoryStore()
    runtime = create_tool_runtime(
        store=store,
        user_id="bei",
    )

    result = call_save_memory(
        runtime=runtime,
        category="  Response_Preference  ",
        content="  先理解原理，再看代码。  ",
    )

    assert result["status"] == "saved"
    assert result["category"] == "response_preference"
    assert result["content"] == "先理解原理，再看代码。"

    namespace = build_memory_namespace("bei")

    stored_item = store.get(
        namespace=namespace,
        key=result["memory_id"],
    )

    assert stored_item is not None
    assert stored_item.value == {
        "category": "response_preference",
        "content": "先理解原理，再看代码。",
    }


def test_list_user_memories_isolates_users() -> None:
    """查询工具只能返回当前用户自己的记忆。"""
    store = InMemoryStore()

    bei_runtime = create_tool_runtime(
        store=store,
        user_id="bei",
    )
    alice_runtime = create_tool_runtime(
        store=store,
        user_id="alice",
    )

    call_save_memory(
        runtime=bei_runtime,
        category="research_interest",
        content="关注VLA模型",
    )
    call_save_memory(
        runtime=alice_runtime,
        category="research_interest",
        content="关注多模态检索",
    )

    bei_result = json.loads(call_list_memories(bei_runtime))
    alice_result = json.loads(call_list_memories(alice_runtime))

    assert len(bei_result) == 1
    assert bei_result[0]["content"] == "关注VLA模型"

    assert len(alice_result) == 1
    assert alice_result[0]["content"] == "关注多模态检索"


def test_delete_user_memory_removes_existing_memory() -> None:
    """删除工具应删除当前用户指定的记忆。"""
    store = InMemoryStore()
    runtime = create_tool_runtime(
        store=store,
        user_id="bei",
    )

    saved_memory = call_save_memory(
        runtime=runtime,
        category="goal",
        content="完成ResearchFlow项目",
    )

    delete_result = call_delete_memory(
        runtime=runtime,
        memory_id=saved_memory["memory_id"],
    )

    assert delete_result == {
        "status": "deleted",
        "memory_id": saved_memory["memory_id"],
    }

    list_result = call_list_memories(runtime)

    assert list_result == "当前用户还没有保存任何长期记忆。"


def test_user_cannot_delete_another_users_memory() -> None:
    """一个用户不能通过memory_id删除其他用户的记忆。"""
    store = InMemoryStore()

    bei_runtime = create_tool_runtime(
        store=store,
        user_id="bei",
    )
    alice_runtime = create_tool_runtime(
        store=store,
        user_id="alice",
    )

    saved_memory = call_save_memory(
        runtime=bei_runtime,
        category="goal",
        content="学习Agent开发",
    )

    delete_result = call_delete_memory(
        runtime=alice_runtime,
        memory_id=saved_memory["memory_id"],
    )

    assert delete_result == {
        "status": "not_found",
        "memory_id": saved_memory["memory_id"],
    }

    bei_memories = json.loads(call_list_memories(bei_runtime))

    assert len(bei_memories) == 1
    assert bei_memories[0]["content"] == "学习Agent开发"


@pytest.mark.parametrize(
    ("category", "content", "expected_message"),
    [
        (
            "",
            "有效内容",
            "保存失败：记忆类别不能为空。",
        ),
        (
            "goal",
            "",
            "保存失败：记忆内容不能为空。",
        ),
        (
            "   ",
            "有效内容",
            "保存失败：记忆类别不能为空。",
        ),
        (
            "goal",
            "   ",
            "保存失败：记忆内容不能为空。",
        ),
    ],
)
def test_save_user_memory_rejects_empty_fields(
    category: str,
    content: str,
    expected_message: str,
) -> None:
    """保存工具应拒绝空类别和空内容。"""
    store = InMemoryStore()
    runtime = create_tool_runtime(
        store=store,
        user_id="bei",
    )

    result = save_user_memory.func(
        category=category,
        content=content,
        runtime=runtime,
    )

    assert result == expected_message

    namespace = build_memory_namespace("bei")

    assert store.search(namespace) == []


@pytest.mark.parametrize(
    "memory_tool",
    [
        save_user_memory,
        list_user_memories,
        delete_user_memory,
        update_user_memory,
    ],
)
def test_runtime_is_hidden_from_model_schema(
    memory_tool,
) -> None:
    """ToolRuntime不能成为模型需要填写的工具参数。"""
    schema = memory_tool.tool_call_schema.model_json_schema()

    properties = schema.get(
        "properties",
        {},
    )

    assert "runtime" not in properties


def test_save_exact_duplicate_returns_existing_memory() -> None:
    """完全相同的记忆不应重复保存。"""
    store = InMemoryStore()
    runtime = create_tool_runtime(
        store=store,
        user_id="bei",
    )

    first_result = call_save_memory(
        runtime=runtime,
        category="response_preference",
        content="回答时先给结论",
    )

    second_result = call_save_memory(
        runtime=runtime,
        category="  RESPONSE_PREFERENCE  ",
        content="  回答时先给结论  ",
    )

    namespace = build_memory_namespace("bei")
    stored_items = store.search(namespace)

    assert first_result["status"] == "saved"
    assert second_result["status"] == "already_exists"
    assert second_result["memory_id"] == first_result["memory_id"]
    assert len(stored_items) == 1


def test_update_user_memory_keeps_memory_id() -> None:
    """更新记忆时应保留原来的memory_id。"""
    store = InMemoryStore()
    runtime = create_tool_runtime(
        store=store,
        user_id="bei",
    )

    saved_memory = call_save_memory(
        runtime=runtime,
        category="response_preference",
        content="回答尽量简短",
    )

    update_result = call_update_memory(
        runtime=runtime,
        memory_id=saved_memory["memory_id"],
        category="response_preference",
        content="先给结论，再解释实现细节",
    )

    assert update_result == {
        "status": "updated",
        "memory_id": saved_memory["memory_id"],
        "category": "response_preference",
        "content": "先给结论，再解释实现细节",
    }

    memories = json.loads(call_list_memories(runtime))

    assert len(memories) == 1
    assert memories[0]["memory_id"] == saved_memory["memory_id"]
    assert memories[0]["content"] == "先给结论，再解释实现细节"


def test_user_cannot_update_another_users_memory() -> None:
    """一个用户不能更新其他用户的长期记忆。"""
    store = InMemoryStore()

    bei_runtime = create_tool_runtime(
        store=store,
        user_id="bei",
    )
    alice_runtime = create_tool_runtime(
        store=store,
        user_id="alice",
    )

    saved_memory = call_save_memory(
        runtime=bei_runtime,
        category="goal",
        content="完成ResearchFlow项目",
    )

    update_result = call_update_memory(
        runtime=alice_runtime,
        memory_id=saved_memory["memory_id"],
        category="goal",
        content="修改其他用户的目标",
    )

    assert update_result == {
        "status": "not_found",
        "memory_id": saved_memory["memory_id"],
    }

    bei_memories = json.loads(call_list_memories(bei_runtime))

    assert bei_memories[0]["content"] == "完成ResearchFlow项目"
