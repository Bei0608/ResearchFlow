import json

from app.tools.paper_search import search_research_papers


def main() -> None:
    print("工具名称：")
    print(search_research_papers.name)

    print("\n工具描述：")
    print(search_research_papers.description)

    print("\n工具参数结构：")
    print(
        json.dumps(
            search_research_papers.args_schema.model_json_schema(),
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n工具执行结果：")
    result = search_research_papers.invoke(
        {
            "query": "RT-1模型的核心网络结构是什么？",
            "top_k": 3,
        }
    )

    print(result)


if __name__ == "__main__":
    main()
