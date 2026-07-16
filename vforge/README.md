# vforge — VideoForge AI Agent 客户端

让 AI Agent 接管 video-forge 视频生产链路的统一入口。

## 两种使用方式

### 方式 A：CLI（推荐，已完整可用）

```bash
cd D:/A-Project/video-forge
python -m vforge --help
```

所有命令输出 JSON，Agent 可直接解析。

**完整命令清单**（22 个子命令）：

| 命令 | 用途 |
|------|------|
| `health` | 后端健康检查 |
| `list` | 列出所有项目 |
| `create --name X --ratio 9:16` | 创建项目 |
| `get --pid X` | 获取项目完整数据 |
| `update --pid X --data @file.json` | 更新项目（深合并） |
| `delete --pid X` | 删除项目 |
| `upload --pid X --file PATH` | 上传素材（图片/视频/音频） |
| `voiceover --pid X --text "..." --engine edge` | AI 配音 + 自动字幕 |
| `import_srt --pid X --file PATH` | 导入 SRT 字幕 |
| `render --pid X --output OUT.mp4` | 渲染 MP4 预览 |
| `export_zip --pid X --output OUT.zip` | 导出剪映 ZIP |
| `export_direct --pid X` | 导出到剪映草稿目录 |
| `jianying_status` | 剪映目录检测 |
| `templates_list` / `template_save` / `template_delete` | 模板管理 |
| `tts_get` / `tts_set` | TTS 配置 |
| `run workflow.json` | 批量执行多步工作流 |
| `mcp` | 启动 MCP server (stdio) |
| `mcp-http --port 8765` | 启动 MCP server (HTTP) |

### 方式 B：MCP server（Codex/Claude Code 直连）

在 Claude Code 的 `~/.claude/mcp.json` 中加入：

```json
{
  "mcpServers": {
    "videoforge": {
      "command": "python",
      "args": ["-m", "vforge", "mcp"],
      "cwd": "D:/A-Project/video-forge"
    }
  }
}
```

或者用 HTTP transport（远程 Agent）：

```json
{
  "mcpServers": {
    "videoforge": {
      "url": "http://localhost:8765/mcp"
    }
  }
}
```

启动方式：
```bash
# stdio（本地）
python -m vforge mcp

# HTTP（远程）
python -m vforge mcp-http --port 8765
```

暴露的 16 个 MCP tools 与 CLI 一一对应。

> **兼容性注意**：mcp 库在当前 Python 3.11 + anyio 环境下 stdio transport 有
> `'function' object is not subscriptable` 错误。HTTP transport 也返回 500。
> 这是 mcp 库版本问题，与本项目代码无关。
>
> 解决路径：
> 1. 升级 anyio: `pip install --upgrade anyio mcp`
> 2. 用 CLI 替代：所有 MCP tool 都有 CLI 等价命令
> 3. 直接用 HTTP REST API（FastAPI 自动 `/docs`）

### 方式 C：工作流（多步批量）

```json
// vforge/examples/workflow.json
{
  "steps": [
    {"cmd": "create", "args": {"name": "auto-demo"}},
    {"cmd": "upload", "args": {"pid": "$prev.id", "file_path": "D:/img.jpg"}},
    {"cmd": "voiceover", "args": {"pid": "$prev.id", "text": "Hello", "engine": "edge"}},
    {"cmd": "render", "args": {"pid": "$prev.id"}},
    {"cmd": "export_direct", "args": {"pid": "$prev.id"}}
  ]
}
```

```bash
python -m vforge run vforge/examples/workflow.json
```

`$prev.xxx` 引用上一步返回的字段，自动链式串联。

## 给 AI Agent 的最佳实践

1. **不要假设项目结构** — 先 `get_project` 拿真实状态再 `update`
2. **配音默认 `edge`（免费）** — 用户明确说"曼波"才切
3. **路径必须绝对** — vforge 不解析 `~` 和相对路径
4. **错误显式** — `VForgeError` 携带 status 和 detail，0 = 网络不通
5. **状态可恢复** — 刷新页面后 `generated/duration/subtitleCount` 从 project.json 自动恢复

## 文件结构

```
vforge/
├── __init__.py         # 版本
├── __main__.py         # python -m vforge 入口
├── client.py           # HTTP 客户端（stdlib only）
├── cli.py              # argparse CLI
├── mcp_server.py       # FastMCP server
├── examples/
│   └── workflow.json   # 工作流示例
└── skill/
    └── SKILL.md        # Skill 打包说明（供 Claude/Codex 直接加载）
```

## 设计原则

- **stdlib only**（CLI 部分）：urllib + json + argparse，零额外依赖
- **后端是唯一真相源**：vforge 是薄包装，所有数据走 FastAPI HTTP API
- **JSON in / JSON out**：Agent 友好
- **不做实时预览**：V0 跑完看效果；V1 再说
- **不锁后端**：你可以同时跑 Web UI + CLI + MCP，共享 project.json
