# VideoForge — 自媒体视频自动化工作台

本地运行的视频生产工具，输入文案 + 素材 → 输出剪映草稿 / MP4 预览视频。

> **给网页端 GPT / Codex / 其他 Agent：**先阅读 [AI 项目入口](docs/START_HERE_FOR_AI.md)。它区分 `main` 已实现能力、实验分支、已设计方向和未来设想，并提供继续分析所需的最短上下文。

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

## 本地生产运行模式

构建前端后，只需启动一个后端进程即可运行完整应用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-frontend.ps1
python backend\launcher.py
```

默认监听 `127.0.0.1:8765`；如果端口被占用，启动器会继续尝试后续本地端口，并自动打开浏览器。使用 `--no-browser` 可关闭自动打开，使用 `--port 9000` 可指定端口。前端构建缺失时，启动器会停止并提示运行构建命令。

开发模式仍保持原方式：前端运行 `npm run dev`，后端运行 `python -m uvicorn main:app --port 8000`。生产运行模式是本地运行壳，不是 EXE 或安装程序。

`requirements.txt` 包含运行 MCP Server 和音频分析所需的依赖。开发及测试环境使用：

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests -q -p no:cacheprovider
```

## 核心功能

| 功能 | 说明 |
|------|------|
| **文案 → AI 配音** | 支持 Edge TTS、Fish Audio、Volcengine、曼波、自定义 API 与纯字幕模式 |
| **自动字幕** | 配音生成同步字幕，9 个位置可调 |
| **多图/视频轮播** | 上传文件夹，随机或顺序排列，每张设时长 |
| **音频智能卡点** | librosa 分析 BPM/能量/重音，4 种卡点模式 |
| **多 BGM 轨道** | 支持多首背景音乐，可裁剪/淡入淡出 |
| **FFmpeg 预览渲染** | 一键生成 MP4 预览，含字幕和音频同步 |
| **剪映草稿导出** | 自动检测剪映目录，一键导入 |
| **全局素材库** | 一次上传反复使用，按文件夹分组管理 |
| **深色/浅色主题** | 电影感中世纪美学，一键切换 |
| **AI Agent 接口** | HTTP API + CLI + MCP + Skill，支持 Codex/Claude Code/本地 Agent 调用 |
| **AI 生图 Scene Pipeline** | 文案按配音时间切 Scene，支持外接 API 或 Codex/Agent 生图回填，再生成 Preview 与剪映草稿 |

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

### AI 生图与精确画面对齐

Factory 素材配对台支持两种 AI 生图方式：Video Forge 直接调用用户配置的 OpenAI-compatible 图片接口，或让 Codex/其他 Agent 使用自身生图能力逐 Scene 回填。每个 Scene 都携带精确字幕时间与防过期 `inputHash`，批准后的图片由 canonical timeline 同步用于 Preview 和剪映草稿。

```bash
python -m vforge image-batch-create --pid proj_xxx --data '{"channel":"agent","providerId":"codex-imagegen"}'
python -m vforge image-batch-pending --pid proj_xxx --batch image_batch_xxx
python -m vforge image-batch-upload --pid proj_xxx --batch image_batch_xxx --scene scene_xxx --input-hash HASH --file image.png
```

完整说明见 [AI 生图 Scene Pipeline](docs/AI_IMAGE_SCENE_PIPELINE.md)。

导演包、火柴人和矢量代码动画属于“已设计方向 + 实验分支资产”，尚未作为 `main` 的正式功能发布。产品分层与后续集成顺序见 [Director Pack 愿景](docs/DIRECTOR_PACK_VISION.md)。

## 技术栈

- **后端**: Python 3.11 / FastAPI / pydantic / pyJianYingDraft / FFmpeg / librosa / edge-tts
- **前端**: React 18 / TypeScript / Vite / Tailwind CSS / Framer Motion / Phosphor Icons
- **AI Agent**: CLI (argparse) + MCP server (FastMCP) + HTTP client (stdlib)

## Portable Windows Alpha

Build a self-contained onedir bundle with `powershell -ExecutionPolicy Bypass -File scripts\build-portable.ps1`.
The output is `release\VideoForge-Windows-Portable.zip`. Users only need to unzip it and start
`VideoForge.exe`; npm and a manual Python command are not required.

FFmpeg is optional at startup but required for MP4 preview rendering. JianYing is optional at startup;
ZIP draft export remains available when direct JianYing export is unavailable. Runtime data is stored
under `%LOCALAPPDATA%\VideoForge`, and `scripts\backup-data.ps1` creates a backup without logs or temp files.
See `docs\PORTABLE-USER-GUIDE.md` for first-run checks, optional dependencies, and restore instructions.
