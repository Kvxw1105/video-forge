"""vforge 入口。`python -m vforge <cli-args>` 调用 CLI；`python -m vforge mcp` 启动 MCP server。"""
from .cli import main

if __name__ == "__main__":
    main()
