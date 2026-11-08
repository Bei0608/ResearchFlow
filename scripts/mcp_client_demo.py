import argparse
import asyncio
import json
import os
import sys

from mcp import Client, StdioServerParameters
from mcp.client.session_group import (
    ClientSessionGroup,
    StreamableHttpParameters,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ResearchFlow MCP Client演示"
    )
    parser.add_argument(
        "--url",
        help="Streamable HTTP地址，例如http://127.0.0.1:8001/mcp",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("MCP_ACCESS_TOKEN"),
        help="受保护HTTP MCP使用的Bearer Token",
    )
    parser.add_argument(
        "--query",
        default="RT-2如何表示机器人动作？",
    )
    return parser.parse_args()


async def print_demo(client, query: str) -> None:
    tools_result = await client.list_tools()
    print("可用MCP工具：")
    for tool in tools_result.tools:
        print(f"- {tool.name}: {tool.description}")

    result = await client.call_tool(
        "researchflow_search_papers",
        {"query": query, "top_k": 3},
    )
    print("\n检索结果：")
    print(
        json.dumps(
            result.structured_content,
            ensure_ascii=False,
            indent=2,
        )
    )


async def run_client(
    url: str | None,
    query: str,
    token: str | None,
) -> None:
    if url and token:
        parameters = StreamableHttpParameters(
            url=url,
            headers={"Authorization": f"Bearer {token}"},
        )
        async with ClientSessionGroup() as group:
            session = await group.connect_to_server(parameters)
            await print_demo(session, query)
        return

    transport = url or StdioServerParameters(
        command=sys.executable,
        args=["-m", "scripts.run_mcp_server"],
    )
    async with Client(transport) as client:
        await print_demo(client, query)


def main() -> None:
    # Windows的默认控制台编码可能是GBK，而论文原文中常包含
    # GBK无法表示的符号（例如项目符号）。统一为UTF-8，避免演示中断。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    asyncio.run(run_client(args.url, args.query, args.token))


if __name__ == "__main__":
    main()
