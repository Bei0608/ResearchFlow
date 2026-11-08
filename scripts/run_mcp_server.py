import argparse
import os

from dotenv import load_dotenv

from app.mcp_server import mcp_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="运行ResearchFlow MCP Server"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="本地客户端用stdio，服务化部署用streamable-http",
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    load_dotenv(override=False)
    args = parse_args()
    options = {}
    if args.transport == "streamable-http":
        options = {
            "host": args.host
            or os.getenv("MCP_HOST", "127.0.0.1"),
            "port": args.port
            or int(os.getenv("MCP_PORT", "8001")),
        }
    mcp_server.run(transport=args.transport, **options)


if __name__ == "__main__":
    main()
