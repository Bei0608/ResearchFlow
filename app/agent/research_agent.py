from functools import lru_cache
from typing import Any

from langchain.agents import create_agent
from app.middleware import AGENT_MIDDLEWARE
from app.models import ResearchContext

from app.llm.chat import get_chat_model
from app.tools import AGENT_TOOLS

from app.memory import (
    get_postgres_checkpointer,
    get_postgres_store,
)

SYSTEM_PROMPT = """
你是一名严谨的具身智能论文研究助手。

你拥有以下能力：
1. 查看论文知识库目录。
2. 检索论文原文内容。
3. 保存、读取和删除当前用户的长期记忆。

论文工具规则：
1. 用户询问知识库有哪些论文、资料或研究范围时，
   使用list_available_papers。
2. 用户询问RT-1、RT-2、PaLM-E、机器人控制
   或论文具体内容时，使用search_research_papers。
3. 论文事实问题必须先检索证据，
   不能只依赖模型自身知识。
4. 只能依据工具返回的论文资料回答论文事实问题。
5. 关键结论后必须标注[资料1]这样的引用编号。
6. 回答末尾列出使用的论文文件和PDF物理页码。
7. 如果检索资料没有明确包含答案，应回答：
   “根据当前论文资料无法确定。”
8. 如果问题与论文知识库无关，也不涉及用户记忆，
   不要调用论文工具，直接说明不属于当前知识库范围。

长期记忆规则：
1. 只有当用户明确表达“请记住”“保存这个偏好”
   “以后要记得”或相同含义时，
   才能调用save_user_memory。
2. 不得自行推测并保存用户偏好、身份或隐私信息。
3. 保存前应把内容整理成简洁、独立、可复用的事实，
   但不能改变用户原意。
4. 用户询问过去保存的偏好、研究兴趣、目标
   或个人信息时，调用list_user_memories。
5. 用户明确要求修改、替换或纠正已有记忆时，
   先调用list_user_memories找到准确的memory_id，
   再调用update_user_memory。
6. 用户要求删除或忘记长期记忆时，
   先调用list_user_memories找到准确的memory_id，
   再调用delete_user_memory。
7. 不得仅因为两条记忆类别相同就擅自覆盖；
   同一类别可能包含多条不同信息。
8. 不得声称读取或修改了其他用户的长期记忆。
9. 工具返回失败时，不得声称操作成功。
""".strip()


@lru_cache(maxsize=1)
def get_research_agent():
    """创建并缓存带持久化会话记忆的论文研究Agent。"""
    return create_agent(
        model=get_chat_model(),
        tools=AGENT_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        middleware=AGENT_MIDDLEWARE,
        checkpointer=get_postgres_checkpointer(),
        store=get_postgres_store(),
        context_schema=ResearchContext,
        name="researchflow_agent",
    )


def run_research_agent(
    question: str,
    thread_id: str = "default",
    user_id: str = "local-user",
) -> dict[str, Any]:
    """在指定会话中运行一次Agent问答。"""
    normalized_question = question.strip()
    normalized_thread_id = thread_id.strip()
    normalized_user_id = user_id.strip()

    if not normalized_question:
        raise ValueError("问题不能为空")

    if not normalized_thread_id:
        raise ValueError("thread_id不能为空")

    if not normalized_user_id:
        raise ValueError("user_id不能为空")

    agent = get_research_agent()

    return agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": normalized_question,
                }
            ]
        },
        config={
            "configurable": {
                "thread_id": normalized_thread_id,
            }
        },
        context=ResearchContext(
            user_id=normalized_user_id,
        ),
    )
