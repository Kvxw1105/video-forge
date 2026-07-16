# VideoForge — 自媒体视频自动化工作台

本地运行的视频生产工具，输入文案 + 素材 → 输出剪映草稿 / MP4 预览视频。

## 快速启动

```bash
# 后端
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --port 8000

# 前端（新终端）
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173

`requirements.txt` 包含运行 MCP Server 和音频分析所需的依赖。开发及测试环境使用：

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests -q -p no:cacheprovider
```

## 核心功能

| 功能 | 说明 |
|------|------|
| **文案 → AI 配音** | 支持 Edge TTS（免费）、曼波 VIP、自定义 API |
| **自动字幕** | 配音生成同步字幕，9 个位置可调 |
| **多图/视频轮播** | 上传文件夹，随机或顺序排列，每张设时长 |
| **音频智能卡点** | librosa 分析 BPM/能量/重音，4 种卡点模式 |
| **多 BGM 轨道** | 支持多首背景音乐，可裁剪/淡入淡出 |
| **FFmpeg 预览渲染** | 一键生成 MP4 预览，含字幕和音频同步 |
| **剪映草稿导出** | 自动检测剪映目录，一键导入 |
| **全局素材库** | 一次上传反复使用，按文件夹分组管理 |
| **深色/浅色主题** | 电影感中世纪美学，一键切换 |
| **AI Agent 接口** | CLI + MCP server，支持 Codex/Claude Code 自动化调用 |

## 项目结构

```
video-forge/
├── backend/           FastAPI 后端
│   ├── models/        数据模型（Project, TTS, Template）
│   ├── routers/       API 路由（15+ 端点）
│   ├── engines/       核心引擎（配音/字幕/渲染/音频分析）
│   ├── adapters/      剪映草稿适配器
│   └── services/      项目/模板 CRUD
├── frontend/          React + Tailwind 前端
│   └── src/
│       ├── pages/     Home, Editor, Library
│       ├── components/ Canvas, Panels, Toolbar
│       └── lib/       API client
├── vforge/            AI Agent CLI + MCP server
├── templates/         内置模板 JSON
└── projects/          项目数据（gitignore）
```

## AI Agent 接入

```bash
# CLI 方式
python -m vforge create --name "测试" --ratio 16:9
python -m vforge voiceover proj_xxx --text "你好世界"
python -m vforge render proj_xxx --output preview.mp4

# MCP server（Claude Code / Codex）
python -m vforge mcp
```

## 技术栈

- **后端**: Python 3.11 / FastAPI / pydantic / pyJianYingDraft / FFmpeg / librosa / edge-tts
- **前端**: React 18 / TypeScript / Vite / Tailwind CSS / Framer Motion / Phosphor Icons
- **AI Agent**: CLI (argparse) + MCP server (FastMCP) + HTTP client (stdlib)
