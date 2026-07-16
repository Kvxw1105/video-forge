# VideoForge 项目记忆存档 — video-use 调研与项目决策

> 创建日期：2026-07-05
> 用途：新会话快速恢复上下文，避免重复调研和决策反转

---

## 一、用户画像

- **称呼**：kv
- **工具链**：NewMax（桌面 AI 工作助手）+ 本地开发环境
- **开发机**：Windows（Git Bash），有 Python 3.11.9 + ffmpeg + uv
- **支付限制**：无外国信用卡，无法直接充值 ElevenLabs 等境外 API
- **视频需求**：自媒体短视频生产（图文/旁白/口播类），追求模板化、批量化、可复用

---

## 二、VideoForge 项目当前状态

### 2.1 定位

本地优先的自媒体视频模板编排工作台。核心产出是**剪映草稿**，用户拿到草稿后去剪映精修导出 MP4。

不是剪辑软件，不是 AI 视频生成器，而是：
> 剪映草稿生成器 + 视频模板编排器 + 本地素材时间轴工作台

### 2.2 当前阶段：V0

只做一条链路：**单图贯穿旁白**。

```
用户上传图片 + 输入文案 → 曼波配音 → SRT字幕 → pyJianYingDraft生成剪映草稿 → FFmpeg MP4预览
```

### 2.3 技术栈

| 模块 | 选型 |
|------|------|
| 后端 | FastAPI (Python 3.11) |
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS v3 + Framer Motion |
| 配音 | 曼波 VIP API（0.005元/次，单次≤299字） |
| 字幕 | 自研文本分句 + SRT 生成 |
| 剪映草稿 | pyJianYingDraft |
| MP4 预览 | FFmpeg |
| 存储 | JSON 文件（无数据库） |
| 数据模型 | project.json（核心资产） |

### 2.4 已实现文件

```
backend/     — FastAPI 后端（路由、模型、服务、引擎、适配器）
frontend/    — React 前端（首页、编辑器、各面板）
templates/   — 内置模板 JSON
```

---

## 三、video-use 调研结果

### 3.1 项目概况

- **项目名**：video-use（GitHub: browser-use/video-use）
- **Star 数**：14.6k
- **定位**：AI 驱动的自动粗剪工具，把原始素材扔进文件夹 + 自然语言指令 → 直接拿 final.mp4
- **协议**：MIT
- **项目年龄**：约 18 次提交，无正式 Release，37 个开放 PR（截至 2026-07）

### 3.2 核心架构

**最聪明的设计：LLM 不"看"视频，而是"读"视频。**

```
Layer 1（始终加载）：音频转录 → 12KB takes_packed.md（词级时间戳+说话人分离+事件标记）
Layer 2（按需加载）：胶片条+波形+词标签的 PNG（仅在决策点调用）

流水线：
Transcribe → Pack → LLM推理 → EDL(编辑决策表) → Render → Self-Eval(最多3轮修复)
```

### 3.3 功能特性

- 自动去口癖/填充词/空白
- 自动调色（暖色电影感/中性/自定义 ffmpeg 链）
- 30ms 音频淡入淡出（每个剪切点自动处理）
- 烧录字幕（2词大写块，可自定义）
- 动画叠加（HyperFrames / Remotion / Manim / PIL）
- 自评估循环（视觉跳变/音频爆音/字幕遮挡检查）
- 会话记忆（project.md 持久化）

### 3.4 依赖与收费

| 依赖 | 费用 | 替代方案 |
|------|------|---------|
| ElevenLabs Scribe | $0.22/小时（需外国卡） | ❌ 无外国卡不可用 |
| LLM 推理（Claude Code） | token 费用 | — |
| ffmpeg | 免费 | — |

### 3.5 中文创作版 Fork

- **项目**：jaschiang/video-use-cht（GitHub）
- **改动**：将 ElevenLabs Scribe 替换为 Breeze-ASR 25/26（基于 WhisperX 的本地 ASR 模型）
- **优势**：不需要任何外部 API、中/英/台语专门优化
- **代价**：需要本地 GPU 跑 ASR 模型推理

---

## 四、核心判断：video-use vs VideoForge

### 4.1 定位差异

| 维度 | VideoForge | video-use |
|------|-----------|-----------|
| **核心产出** | 剪映草稿（去剪映精修） | final.mp4（成品即终稿） |
| **谁做剪辑决策** | 人（通过模板+参数面板） | AI（LLM 推理 EDL） |
| **素材类型** | 图文/封面/轮播 | 口播/播客/访谈原始素材 |
| **转录需求** | ❌ 不需要（文案手动输入） | ✅ 核心依赖 |
| **渲染层** | pyJianYingDraft（剪映结构） | ffmpeg（直接渲染） |
| **AI 角色** | 未来才规划（V1.5+） | 核心，现在是全部 |

**结论：两个项目解决的问题域根本不同，不是竞品关系。**

### 4.2 不可直接集成的理由

1. video-use 没有设计为可被调用的库
2. 输出目标是 final.mp4，不是剪映草稿（与现有工作流冲突）
3. 强依赖 ElevenLabs（无外国卡无法使用）
4. 项目不稳定（18 次提交，无 Release）

### 4.3 NewMax 环境说明

- NewMax 是**桌面 AI 工作助手**，不是纯云端聊天平台
- 有内置终端、工作区（本地文件访问）、Skill 管理、MCP 支持
- 运行在 NewMax 中的 AI（如当前会话）有 Bash 权限，可以直接在用户机器上执行命令
- 因此 AI 可以帮用户安装工具、改代码、运行脚本

---

## 五、video-use 可融入 VideoForge 的能力（优先级排序）

| 优先级 | 能力 | 适合版本 | 代码量 | 说明 |
|--------|------|---------|--------|------|
| **P0** | 导出质检（自评估循环） | V0.5 | ~80行 | 导出后自动检查字幕遮挡、配音对齐、图片裁切 |
| **P1** | 口播转录导入 | V1 | ~150行 | 扔录音 → 自动转文案 → 进现有流水线 |
| **P2** | 智能高潮点推荐（LLM EDL） | V1.5 | ~100行 | LLM 分析文案 → 推荐高潮句和换图时机 |
| **P3** | 会话记忆（连载项目） | V1.5 | ~50行 | project.md 持久化剪辑上下文 |
| **P4** | AI 操作 project.json | V2 | 架构设计 | 文本为主策略，AI 不"看"视频只读结构化数据 |

### 导出质检（P0）检查项

1. 字幕区域是否遮挡主图
2. 配音时长 vs 字幕总时长是否对齐
3. 图片缩放/裁切是否超出画布边界
4. 草稿 JSON 结构是否符合 Pydantic schema

---

## 六、关键决策记录

### 6.1 关于 ElevenLabs

- ❌ **不采用**原版 video-use（需要外国信用卡）
- 备选方案：
  - **video-use-cht**（Breeze-ASR 本地模型，需要 GPU）
  - **火山引擎录音文件识别**（~2元/小时，人民币结算，中文准确率更高）
  - **faster-whisper 本地**（免费，无说话人分离）

### 6.2 关于 video-use 的去留

- ❌ 不作为 VideoForge 的依赖集成
- ✅ 作为设计参考，抽离核心设计模式融入 VideoForge
- 从 P0（导出质检）开始逐步吸收

### 6.3 产品路线不动摇

- VideoForge 的核心定位不变：**模板编排 → 剪映草稿**
- 不做全自动 AI 视频生成器
- AI 未来操作 project.json，不是自由调用底层工具

---

## 七、参考资料

- VideoForge PRD: `自媒体视频自动化工作台_PRD_v0.1.md`
- VideoForge V0 设计: `docs/superpowers/specs/2026-07-04-video-forge-v0-design.md`
- VideoForge V0 实施计划: `docs/superpowers/plans/2026-07-04-video-forge-v0.md`
- video-use 原版: https://github.com/browser-use/video-use
- video-use-cht: https://github.com/JasChiang/video-use-cht
- 火山引擎语音识别: 录音文件识别 ~2元/小时（需官网确认最新定价）
