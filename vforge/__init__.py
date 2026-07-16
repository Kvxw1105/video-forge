"""vforge — AI Agent 友好的 VideoForge 客户端。

提供两种入口：
  - CLI: `vforge <command> [--args]`  →  适合脚本和 Agent 工具调用
  - MCP: `vforge mcp`                 →  适合 Codex/Claude Code 直接接管

所有能力都通过 VideoForge 后端 HTTP API 实现，CLI/MCP 只是薄包装。
"""

__version__ = "0.1.0"
