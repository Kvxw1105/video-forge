# VideoForge V0 设计规格说明书

> 文档状态：已确认 / 待实施
> 产品方向：本地优先的自媒体视频自动化工作台
> 当前阶段：V0 — 单图贯穿旁白模板验证
> 基于：`自媒体视频自动化工作台_PRD_v0.1.md` + 需求讨论整合

---

## 1. 产品定义

**VideoForge** 是一个面向自媒体短视频生产的本地优先视频自动化工作台。

V0 阶段只做一件事：**用户上传一张图 + 输入文案 → 系统生成配音字幕 → 输出剪映草稿**。

本产品不是剪辑软件，也不是 AI 视频生成器，而是：

> 剪映草稿生成器 + 视频模板编排器 + 本地素材时间轴工作台。

---

## 2. V0 核心决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 输出优先级 | 剪映草稿第一，MP4 预览辅助 | 保留人工精修空间，降低开发复杂度 |
| 产品形态 | 轻量 Web（FastAPI + React），浏览器打开使用 | 最快验证核心链路，后续可套 Electron 壳 |
| V0 模板数量 | 1 个（单图贯穿旁白） | 先跑通一条完整链路 |
| 配音方案 | 曼波 VIP API（已验证可用） | 299字/次限制，0.005元/次 |
| 素材策略 | 默认复制到项目目录 | 项目自包含，源文件删除不影响 |
| 剪映草稿生成 | pyJianYingDraft | 成熟开源方案，避免自研逆向工程 |
| 预览 | 静态布局预览 + 生成后低清 MP4 | 不做实时视频编辑器 |

---

## 3. V0 非目标

以下明确不做：

- 不做完整替代剪映的专业剪辑软件
- 不做实时视频时间轴编辑器
- 不做多图轮播、高潮换图、画中画模板
- 不做 AI 一键爆款生成
- 不做账号系统、云端同步、模板市场
- 不做批量生成
- 不做桌面壳打包（Electron/Tauri）
- 不做全自动剪映导出（需 GUI 自动化，不稳定）

---

## 4. 架构设计

### 4.1 整体架构

```
浏览器 Web UI (React + Tailwind + Framer Motion)
       │ HTTP
FastAPI 后端 (Python 3.11)
       │
       ├── 项目模型引擎 (project.json CRUD)
       ├── 模板引擎 (template.json → 参数面板)
       ├── 配音引擎 (曼波 VIP API 封装)
       ├── 字幕引擎 (文本分句 → SRT 生成)
       └── 时间轴编排
              │
              ├── 剪映草稿适配器 (pyJianYingDraft)
              │       └── jianying_draft/ 文件夹
              │
              └── MP4 预览适配器 (FFmpeg)
                      └── preview.mp4
```

### 4.2 核心原则

1. **项目模型是唯一真相源** — project.json 定义一切，输出适配器从它派生
2. **输出适配器可替换** — 新增输出格式不改核心逻辑
3. **不做实时渲染** — 只做静态布局预览 + 生成后验收
4. **配音 API 可替换** — 曼波换任何 TTS，只改一个适配器文件
5. **Agent-ready 从第一天开始** — project.json schema 设计为可被 AI/Agent 读写

### 4.3 V0 数据流（单图贯穿旁白）

```
用户打开浏览器 → 新建项目(9:16)
→ 上传一张图 → 输入文案
→ 点"生成配音"(调曼波API)
→ 字幕自动生成(SRT)
→ 设置图片位置/大小 → 添加BGM → 设置标题/水印
→ 点"导出剪映草稿"
→ 后端生成 jianying_draft/ 文件夹
→ 用户复制到剪映草稿目录 → 打开剪映 → 精修 → 导出MP4
```

---

## 5. 技术选型

| 模块 | 选型 | 版本 | 说明 |
|------|------|------|------|
| 后端框架 | FastAPI | latest | Python 原生异步，适合本地服务 |
| Python | 3.11 | 3.11.9 | 匹配 pyJianYingDraft 推荐版本 |
| 前端框架 | React + TypeScript | 18 | 组件化，生态成熟 |
| 构建工具 | Vite | latest | 快 |
| 样式 | Tailwind CSS | v3 | 禁止 v4（兼容性） |
| 动画 | Framer Motion | latest | spring 物理动画 |
| 图标 | @phosphor-icons/react | latest | 统一 strokeWidth: 1.5 |
| 视频合成 | FFmpeg | system | MP4 预览生成 |
| 剪映草稿 | pyJianYingDraft | latest | `pip install pyjianyingdraft` |
| 配音 | 曼波 VIP API | — | 已有 key，已验证可用 |

### 5.1 明确不引入

- 不引入 shadcn/ui（V0 一个页面，Tailwind 直接写更快）
- 不引入状态管理库（useState/useReducer 足够）
- 不引入数据库（JSON 文件即存储）
- 不引入 Docker
- 不引入 Nginx

---

## 6. 项目目录结构

```
video-forge/
├── backend/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 配置管理（API key、路径等）
│   ├── models/
│   │   ├── project.py          # project.json 数据模型(Pydantic)
│   │   └── template.py         # template.json 数据模型
│   ├── engines/
│   │   ├── voiceover.py        # 曼波配音引擎
│   │   ├── subtitle.py         # 字幕生成引擎（分句+SRT）
│   │   └── timeline.py         # 时间轴编排
│   ├── adapters/
│   │   ├── jianying.py         # 剪映草稿适配器(pyJianYingDraft)
│   │   └── mp4_preview.py      # MP4 预览适配器(FFmpeg)
│   ├── routers/
│   │   ├── project.py          # 项目 CRUD API
│   │   ├── voiceover.py        # 配音相关 API
│   │   ├── export.py           # 导出 API
│   │   └── assets.py           # 素材上传 API
│   └── services/
│       ├── project_service.py  # 项目业务逻辑
│       └── export_service.py   # 导出业务逻辑
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # 路由入口
│   │   ├── pages/
│   │   │   ├── Home.tsx        # 首页
│   │   │   └── Editor.tsx      # 项目编辑页（核心）
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── TopBar.tsx        # 顶栏
│   │   │   │   └── BottomBar.tsx     # 底栏
│   │   │   ├── panels/
│   │   │   │   ├── AssetPanel.tsx    # 素材上传面板
│   │   │   │   ├── ScriptPanel.tsx   # 文案输入面板
│   │   │   │   ├── AudioPanel.tsx    # 配音+BGM面板
│   │   │   │   └── OverlayPanel.tsx  # 标题水印面板
│   │   │   ├── canvas/
│   │   │   │   └── CanvasPreview.tsx # 画布静态预览
│   │   │   └── ui/
│   │   │       ├── FileUpload.tsx    # 拖拽上传组件
│   │   │       ├── Slider.tsx        # 滑块组件
│   │   │       ├── Toggle.tsx        # 开关组件
│   │   │       ├── ProgressBar.tsx   # 进度条
│   │   │       └── Skeleton.tsx      # 骨架屏
│   │   ├── hooks/
│   │   │   ├── useProject.ts   # 项目状态管理
│   │   │   └── useVoiceover.ts # 配音状态管理
│   │   ├── lib/
│   │   │   └── api.ts          # API 调用封装
│   │   └── styles/
│   │       └── globals.css     # Tailwind + 自定义变量
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── package.json
│
├── projects/                    # 用户项目存储目录
│   └── {project_name}_{date}/
│       ├── project.json
│       ├── assets/
│       │   ├── cover.png
│       │   └── bgm.mp3
│       ├── voiceover.mp3
│       ├── subtitles.srt
│       ├── jianying_draft/
│       │   ├── draft_content.json
│       │   └── draft_meta_info.json
│       └── preview.mp4
│
├── templates/                   # 内置 + 用户模板
│   └── single_image_voiceover.json
│
├── manbo_tts.py                 # 曼波配音工具脚本（已有）
├── manbo-tts-config.md          # 曼波配置文档（已有）
└── requirements.txt
```

---

## 7. 数据模型

### 7.1 Project（project.json）

```json
{
  "id": "proj_20260704_001",
  "name": "高考志愿单图旁白",
  "version": "0.1",
  "canvas": {
    "ratio": "9:16",
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "background": {
      "type": "color",
      "value": "#000000"
    }
  },
  "templateId": "single_image_voiceover",
  "assets": [],
  "segments": [],
  "audio": {
    "voiceover": {
      "api": "manbo_vip",
      "voice": "manbo",
      "speed": 0,
      "file": "voiceover.mp3"
    },
    "bgm": {
      "file": "bgm.mp3",
      "volume": 0.3,
      "loop": true,
      "fadeIn": 0,
      "fadeOut": 2.0
    }
  },
  "subtitles": [],
  "overlays": {
    "title": {
      "text": "",
      "position": "top_center",
      "fontSize": 48,
      "color": "#ffffff",
      "enabled": false
    },
    "watermark": {
      "text": "",
      "position": "top_right",
      "fontSize": 24,
      "color": "#ffffff80",
      "enabled": false
    }
  },
  "exportSettings": {
    "targets": ["jianying_draft"],
    "outputDir": "projects/proj_20260704_001/"
  }
}
```

### 7.2 Segment（素材片段）

```json
{
  "id": "seg_001",
  "assetPath": "assets/cover.png",
  "type": "image",
  "start": 0.0,
  "end": 28.5,
  "transform": {
    "x": 0.5,
    "y": 0.5,
    "scale": 0.85,
    "rotation": 0,
    "fit": "contain"
  },
  "animation": null
}
```

### 7.3 Subtitle

```json
{
  "id": "sub_001",
  "text": "很多家长第一步就错了",
  "start": 0.2,
  "end": 2.1,
  "style": {
    "fontSize": 36,
    "color": "#ffffff",
    "strokeColor": "#000000",
    "strokeWidth": 2,
    "position": "bottom"
  }
}
```

### 7.4 Template（template.json）

```json
{
  "id": "single_image_voiceover",
  "name": "单图贯穿旁白模板",
  "type": "workflow",
  "version": "0.1",
  "canvas": {
    "ratio": "9:16",
    "background": "#000000"
  },
  "segments": [
    {
      "type": "main_image",
      "durationRule": "full_video",
      "defaultTransform": {
        "x": 0.5,
        "y": 0.5,
        "scale": 0.85,
        "fit": "contain"
      }
    }
  ],
  "audio": {
    "voiceover": { "api": "manbo_vip", "speed": 0 },
    "bgm": { "volume": 0.3 }
  },
  "overlays": {
    "subtitle": { "position": "bottom" },
    "title": { "position": "top_center", "enabled": false },
    "watermark": { "position": "top_right", "enabled": false }
  }
}
```

---

## 8. 剪映草稿适配器详设

### 8.1 选用方案

使用 `pyJianYingDraft` ([GitHub](https://github.com/GuanYixuan/pyJianYingDraft))：

- 支持剪映 5.x ~ 6.x 草稿生成
- Python 3.11 兼容 ✅
- 支持：图片/音频/文本素材、SRT 字幕导入、样式控制
- 草稿生成全自动；MP4 导出需剪映 GUI（V0 不做）

### 8.2 映射关系

| project.json 元素 | pyJianYingDraft API |
|-------------------|---------------------|
| segment(图片) | `VideoSegment(path, target_timerange=(start, duration))` |
| audio.voiceover | `AudioSegment(voiceover.mp3)` |
| audio.bgm | `AudioSegment(bgm.mp3)` + `volume` 属性 |
| subtitles[] | `ScriptFile.import_srt(subtitles.srt)` |
| overlays.title | `TextSegment(text, target_timerange, style, clip_settings)` |
| overlays.watermark | `TextSegment(text, target_timerange, style, clip_settings)` |

### 8.3 生成流程

```
project.json → JianYingAdapter.generate()
  1. 创建 ScriptFile(resolution=(1080, 1920))
  2. 添加 video track → VideoSegment(主图, 全时长)
  3. 添加 audio track → AudioSegment(配音)
  4. 添加 audio track → AudioSegment(BGM)（如有）
  5. 添加 text track → import_srt(subtitles.srt)（如有）
  6. 添加 text track → TextSegment(标题)（如有）
  7. 添加 text track → TextSegment(水印)（如有）
  8. DraftFolder.create_new(name) → 保存
  → 返回草稿文件夹路径
```

### 8.4 用户操作

生成后用户需手动：

1. 将 `jianying_draft/` 文件夹复制到剪映草稿目录
2. 打开剪映桌面版
3. 草稿出现在项目列表
4. 检查 / 精修
5. 导出 MP4

---

## 9. 前端设计详设

### 9.1 设计 Token

| Token | 值 |
|-------|-----|
| 字体 | Geist (Sans), Geist Mono (mono) |
| 底色 | `bg-zinc-950` |
| 卡片 | `bg-white rounded-[2rem] shadow-[0_20px_40px_-15px_rgba(0,0,0,0.05)]` |
| 强调色 | Emerald-500 (`#10b981`) |
| 文字主色 | `text-zinc-900` |
| 文字副色 | `text-zinc-500` |
| 边框 | `border-zinc-200/50` |
| 动画 | Framer Motion `spring: stiffness:100, damping:20` |
| 图标 | `@phosphor-icons/react` strokeWidth=1.5 |

### 9.2 页面清单

| 页面 | 路由 | 复杂度 | 说明 |
|------|------|--------|------|
| Home（首页） | `/` | 低 | Logo + 新建按钮 + 最近项目列表 |
| Editor（编辑页） | `/editor/:id` | 中 | 核心页面，所有操作在此完成 |
| Settings（设置） | `/settings` | 低 | 配音 API Key 配置 + 默认输出路径 |

### 9.3 Editor 页面布局

```
┌──────────────────────────────────────────────────────┐
│  ◇ VideoForge    {项目名称}                   [导出草稿] │  TopBar
├────────────┬─────────────────────────────────────────┤
│            │                                         │
│  AssetPanel│           CanvasPreview                  │
│  (素材卡片) │         ┌─────────────┐                 │
│  ┌───────┐ │         │             │                 │
│  │ 封面图 │ │         │  9:16 画布   │                 │
│  │ [替换] │ │         │  静态预览    │                 │
│  └───────┘ │         │             │                 │
│            │         │  图片居中    │                 │
│  ScriptPanel│        │  字幕位置    │                 │
│  (文案卡片) │         │             │                 │
│  ┌───────┐ │         └─────────────┘                 │
│  │文案输入│ │         缩放: ──●── 85%                  │
│  │       │ │         位置: [↕] [↔]                    │
│  │[生成] │ │                                         │
│  └───────┘ │                                         │
│            │                                         │
│  AudioPanel│                                         │
│  (音频卡片) │                                         │
│  ┌───────┐ │                                         │
│  │BGM设置 │ │                                         │
│  └───────┘ │                                         │
│            │                                         │
│  Overlay   │                                         │
│  Panel     │                                         │
│  (标题水印) │                                         │
│            │                                         │
├────────────┴─────────────────────────────────────────┤
│  配音已生成 · 时长 28.5s · 字幕 12 条   [导出剪映草稿]    │  BottomBar
└──────────────────────────────────────────────────────┘
```

### 9.4 交互状态覆盖

每个组件必须覆盖以下状态：

| 状态 | 组件示例 |
|------|---------|
| **Empty** | 首次打开无素材 → 拖拽上传引导插画 + "点击或拖拽上传封面图" |
| **Loading** | 配音生成中 → 文案卡片显示脉冲骨架屏 + 底部进度条 |
| **Success** | 配音完成 → 绿勾 + 时长显示 |
| **Error** | API 失败 → 红色内联提示 + "重试"按钮 |
| **Active** | 图片拖拽上传 → 边框变 Emerald-500 + spring 放大 1.02x |
| **Disabled** | 未上传图片时 → 导出按钮灰色不可点击 |

### 9.5 禁止项

- ❌ 禁止 Inter 字体
- ❌ 禁止紫色/霓虹渐变
- ❌ 禁止纯黑 `#000000`
- ❌ 禁止 Emoji 用于图标
- ❌ 禁止 `h-screen`（移动端使用 `min-h-[100dvh]`）
- ❌ 禁止复杂 flexbox 计算（用 CSS Grid）
- ❌ 禁止 3 列等宽卡片布局
- ❌ 禁止无意义的 "Elevate", "Seamless" 等 AI 文案

---

## 10. API 设计

### 10.1 项目 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects` | 创建新项目 |
| GET | `/api/projects/{id}` | 获取项目详情 |
| PUT | `/api/projects/{id}` | 更新项目配置 |
| GET | `/api/projects` | 列出所有项目 |
| DELETE | `/api/projects/{id}` | 删除项目 |

### 10.2 素材 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects/{id}/assets` | 上传素材（multipart） |
| DELETE | `/api/projects/{id}/assets/{asset_id}` | 删除素材 |

### 10.3 配音 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects/{id}/voiceover` | 生成配音 |
| GET | `/api/projects/{id}/voiceover/status` | 查询配音状态 |

### 10.4 导出 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/projects/{id}/export/jianying` | 导出剪映草稿 |
| POST | `/api/projects/{id}/export/mp4` | 导出 MP4 预览 |
| GET | `/api/projects/{id}/export/log` | 查询导出日志 |

---

## 11. 配音集成

### 11.1 API 规格（已确认）

```
GET https://api.milorapart.top/apis/mbAIscvip
  Query: text={文本}&key={API_KEY}&speed={语速}&format=mp3
  Header: Authorization: Bearer {API_KEY}

限制: 单次 ≤ 299 字符
费率: 0.005 元/次
```

### 11.2 长文本处理

当文案超过 250 字符时（留 49 字符安全余量），自动分段：

1. 优先按句号、问号、感叹号断句
2. 次优按逗号断句
3. 每段 ≤ 250 字符
4. 多段分别调 API
5. 按顺序拼接为单个 MP3

---

## 12. V0 验收标准

MVP 必须能完成以下完整链路：

1. 用户在浏览器中打开 Web 界面
2. 新建 9:16 项目
3. 上传一张封面图
4. 输入文案（≥100 字）
5. 点击"生成配音"，成功调用曼波 VIP API
6. 字幕自动生成并显示
7. 图片位置和缩放可调节
8. 可添加 BGM 并调节音量
9. 可设置标题文字和水印
10. 点击"导出剪映草稿"，生成完整 `draft_content.json`
11. 导出 `project.json` 和 `template.json`
12. 保存的模板可用于创建新项目

---

## 13. 版本路线图

| 版本 | 范围 |
|------|------|
| **V0** | 单图贯穿旁白：基础 UI + 配音 + 字幕 + 剪映草稿导出 |
| **V0.5** | 多图轮播模板 + 静态布局预览 + 低清 MP4 预览 |
| **V1** | 高潮换图 + 画中画 + 模板库管理 + 设置页 |
| **V1.5** | AI 辅助分句 + 模板推荐 + 批量生成变体 |
| **V2** | Agent 工作台 + MCP Server + 受控 AI 工具调用 |

---

## 14. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| pyJianYingDraft 不兼容新版剪映 | 草稿无法打开 | V0 锁定剪映 5.x/6.x；后续跟进 pyJianYingDraft 更新 |
| 曼波 VIP API 不稳定/涨价 | 配音功能不可用 | 配音引擎模块化，可快速切换其他 TTS API |
| 剪映草稿格式未来加密 | 草稿生成全线失效 | project.json 是核心资产，届时切换 Remotion/FFmpeg 渲染 |
| Windows 路径编码问题 | 中文项目名/文件名出错 | 统一使用 UTF-8，路径规范化处理 |

---

## 15. 参考资源

- PRD 原始文档：`自媒体视频自动化工作台_PRD_v0.1.md`
- 曼波配音配置：`manbo-tts-config.md`
- pyJianYingDraft：https://github.com/GuanYixuan/pyJianYingDraft
- 曼波 VIP API：https://api.milorapart.top/docs/75/mbAIscvip
