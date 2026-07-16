---
name: videoforge
description: >
  VideoForge — 自媒体视频自动化工作台。让 AI Agent 可以批量创建短视频项目、
  上传素材、生成 AI 配音（Edge TTS/曼波 VIP/自定义）、合成 MP4 预览、
  导出剪映草稿。支持 CLI (单命令) 和 MCP server (Codex/Claude Code 直接接管)
  两种接入方式。
triggers:
  - "做个视频"
  - "剪个短视频"
  - "导出剪映草稿"
  - "AI 配音"
  - "video-forge"
  - "vforge"
  - "自动生成视频"
license: MIT
version: 0.1.0
metadata:
  author: kv
  category: video-automation
  layer: agent-tool
  compatibility:
    - claude-code
    - codex
    - cursor
    - any-mcp-client
  pairs_with:
    - ponytail
    - kv-clarity-mirror
---

# VideoForge — Skill 入口

> 既是工具，也是 Skill。安装后 AI Agent 可以直接接管整个视频生产链路。

---

## 两种接入方式

### 方式 A：MCP server（推荐给 Codex/Claude Code）

```json
// ~/.claude/mcp.json 或 .mcp.json
{
  "mcpServers": {
    "videoforge": {
      "command": "python",
      "args": ["-m", "vforge", "mcp"],
      "cwd": "D:/A-Project/video-forge",
      "env": {
        "VFORGE_BASE": "http://localhost:8000"
      }
    }
  }
}
```

启动后 AI Agent 看到这些 tools：

| Tool | 用途 |
|------|------|
| `health` | 后端健康检查 |
| `list_projects` | 列出项目 |
| `create_project(name, ratio)` | 创建项目 |
| `get_project(pid)` | 获取完整数据 |
| `update_project(pid, data)` | 字段更新（深合并） |
| `delete_project(pid)` | 删除 |
| `upload_asset(pid, file_path)` | 上传本地素材 |
| `generate_voiceover(pid, text, engine, speed)` | AI 配音 + 自动字幕 |
| `import_srt(pid, file_path)` | 导入外部字幕 |
| `render_preview(pid)` | FFmpeg 合成 MP4 |
| `export_jianying_zip(pid, output_path)` | 导出剪映 ZIP |
| `export_jianying_direct(pid)` | 导出到剪映草稿目录 |
| `jianying_status` | 剪映目录检测 |
| `list_templates` / `save_template` | 模板管理 |
| `get_tts_settings` / `update_tts_settings` | TTS 配置 |

### 方式 B：CLI（适合 shell 脚本和一次性调用）

```bash
# 在 video-forge/ 目录下
python -m vforge list
python -m vforge create --name "demo" --ratio "9:16"
python -m vforge upload --pid proj_xxx --file "D:/photos/img1.jpg"
python -m vforge voiceover --pid proj_xxx --text "这是文案" --engine "edge"
python -m vforge render --pid proj_xxx --output "out.mp4"
python -m vforge export_direct --pid proj_xxx
```

所有命令输出 JSON，Agent 可直接解析。

### 方式 C：Workflow（多步串联）

`workflow.json`:
```json
{
  "steps": [
    {"cmd": "create", "args": {"name": "auto-demo"}},
    {"cmd": "upload", "args": {"pid": "$prev.id", "file_path": "D:/img.jpg"}},
    {"cmd": "voiceover", "args": {"pid": "$prev.id", "text": "Hello world", "engine": "edge"}},
    {"cmd": "render", "args": {"pid": "$prev.id"}},
    {"cmd": "export_direct", "args": {"pid": "$prev.id"}}
  ]
}
```

```bash
python -m vforge run workflow.json
```

---

## 核心能力矩阵

| 能力 | 实现 | 限制 |
|------|------|------|
| 横/竖/方/4:5 画布 | ✅ | — |
| 多图/视频/混剪轮播 | ✅ | 视频用自然时长，不被压缩 |
| 随机/顺序排列 | ✅ | — |
| 每张素材时长可调 | ✅ | 默认 1.0s |
| 配音驱动时长 | ✅ | 配音+图片循环=视频总时长 |
| AI 配音：Edge TTS | ✅ | 免费，免注册 |
| AI 配音：曼波 VIP | ✅ | 0.005 元/次，299 字/次 |
| AI 配音：自定义 API | ✅ | 任何兼容的 HTTP API |
| BGM 音轨 | ✅ | 截断到视频时长 |
| 字幕（SRT 同步） | ✅ | 字号/颜色可调 |
| 标题/水印叠加 | ✅ | 位置预设 |
| 字幕开关 | ✅ | — |
| 背景颜色（黑/白/任意色） | ✅ | 修复后 |
| 剪映草稿（ZIP/直接写入） | ✅ | 需要 pyjianyingdraft |
| MP4 预览渲染 | ✅ | FFmpeg + libx264 |
| **未做**：实时播放预览 | ❌ | 需 V1 |
| **未做**：高级转场/关键帧 | ❌ | 剪映侧补 |

---

## 给 AI Agent 的最佳实践

1. **不要一次性塞满 50 张图** — 先上传 5-10 张，测试效果
2. **配音用 `--engine edge` 默认免费**，只有用户明确要求"曼波"才切换
3. **render 之后必须把 previewUrl 反馈给用户**，让 ta 验证效果
4. **export_direct 之前先调 jianying_status**，确认剪映已装
5. **所有路径用绝对路径**，vforge 不解析 `~` 和相对路径
6. **错误以 VForgeError 抛出**，status 0 = 网络不通，status 4xx/5xx = 后端业务错误
7. **不要假设项目结构** — 先 get_project 拿到真实状态再 update

---

## 设计哲学

- **后端是唯一真相源**（JSON 文件），CLI/MCP 都是薄包装
- **资源按需付费**（Edge TTS 免费；曼波按次；本地 F5-TTS 需 GPU）
- **Agent 友好**（JSON in/out，状态可恢复，错误显式）
- **不做实时预览**（V0 跑完看效果；V1 再说）

---

## 安装到其他项目

```bash
# 方式 1：作为 Python 包安装
cd D:/A-Project/video-forge
pip install -e .

# 方式 2：复制 vforge/ 目录
cp -r vforge/ /path/to/your-project/
python -m vforge --help
```

后端独立运行：
```bash
cd D:/A-Project/video-forge/backend
python -m uvicorn main:app --port 8000
```
