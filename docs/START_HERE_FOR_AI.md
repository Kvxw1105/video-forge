# Video Forge：给 AI / Agent 的项目入口

如果你是网页端 GPT、Codex、Claude Code 或其他 Agent，请先读本页，再决定还需要打开哪些文件。不要要求用户重新粘贴已经存在于仓库中的项目历史。

## 一句话定位

Video Forge 是一个 local-first 视频生产工作台：把文案、配音、字幕和视觉素材组织到同一个 Project 与 canonical timeline 中，输出可预览 MP4 和剪映草稿；同时通过 HTTP API、CLI、MCP 和 Skill 向外部 Agent 提供能力。

## 状态标签

- `AVAILABLE_ON_MAIN`：已经位于 `main`，可从代码和测试中复核。
- `EXPERIMENTAL_BRANCH`：仓库已有实验实现，但尚未集成到 `main`。
- `IMPLEMENTED_ON_BRANCH`：功能、测试和真实用户路径已在指定分支实现，等待 PR 合并。
- `DESIGNED`：已有批准设计，尚未成为主产品能力。
- `FUTURE`：方向性设想，没有实现承诺。

## AVAILABLE_ON_MAIN：现在能做什么

| 能力 | 当前结果 | 入口 |
|---|---|---|
| 文案与项目编辑 | 创建 Project，编辑文案、素材、字幕、音频和导出设置 | `frontend/src/pages/Editor.tsx`、`backend/models/project.py` |
| 结构化内容 | 将内容组织为 Block、Variant、Binding 和 VisualPlan | `docs/structured-content/`、`backend/shared/` |
| 配音与字幕 | 支持 Edge TTS、Fish Audio、Volcengine、Manbo、自定义 API 与纯字幕模式 | `backend/engines/voiceover.py`、`frontend/src/components/panels/ScriptPanel.tsx` |
| Scene 时间对齐 | Scene 的起止时间由配音/字幕决定，视觉素材不能自行改写时长 | `backend/shared/visual_scene.py` |
| AI 图片 | 外接 OpenAI-compatible Provider，或由 Codex/其他 Agent 领取 Scene 请求后生成并回填 | [AI 生图 Scene Pipeline](AI_IMAGE_SCENE_PIPELINE.md) |
| 素材审批与绑定 | 用 `visualSourceHash` 和 `inputHash` 防止过期图片绑定到错误 Scene | `backend/services/image_generation_service.py` |
| 成片输出 | 同一 canonical timeline 驱动字幕、配音、BGM、MP4 Preview 和剪映草稿 | `backend/engines/renderer.py`、`backend/adapters/jianying.py` |
| Agent 接入 | HTTP API、CLI、MCP、Skill | `vforge/`、`vforge/skill/SKILL.md` |

## 当前标准工作流

```text
文案 / 想法
  → Project 与结构化 Block
  → 配音和字幕时间
  → VisualPlan Scenes
  → 手动素材 / AI 图片 / Agent 回填
  → 候选审批与 Scene 绑定
  → canonical timeline
  → Preview / 剪映草稿
```

图片只提供画面，不决定播放时长。Codex 生图额度的正确接入方式是：Agent 拉取待生成 Scene，使用自身可用的生图工具，再携带原始 `inputHash` 回填；Video Forge 后端不能直接读取或冒充 Codex 客户端额度。

## 明确边界

- 没有真实 Provider 名称、凭据和调用结果时，不得声称真实付费生图已经验证。
- `main` 目前没有可安装的 Director Pack；`codex/director-pack-protocol-v1` 已实现本地 data-only 协议和管理入口，但没有商店、第三方签名、沙箱和付费授权系统。
- 火柴人、矢量代码动画、Director Studio、Pi Director 和 MediaKit 仍属于实验分支能力。
- AI 视频 Provider 属于 `FUTURE`，尚未进入当前交付范围。
- 不允许另建第二套 Project、VisualPlan 或 Timeline；所有视觉能力最终必须回到现有 canonical timeline。

## EXPERIMENTAL_BRANCH：已有实验但尚未上线

| 分支 | 已观察到的探索 | 阅读时的限制 |
|---|---|---|
| `codex/director-pack-studio-clean` | Director Studio、版本化 Skill、Pack 导入导出、Director 到 Factory 交付 | 规模很大，不能整枝合并或描述成 `main` 已上线 |
| `codex/pi-video-director` | Pi Agent Director、脚本整理、Scene 提案和能力调用 | 需要重新基于当前 `main` 做兼容审计 |
| `codex/code-visual-renderer-pack` | 白描、轮廓、机制图、像素规则等代码视觉和 motion export | Provider contracts 有价值，但未集成到当前主线 |
| `codex/stickman-visual-provider` | 火柴人 SVG/PNG、模板、批处理、联系表和 Preview/剪映验证 | 适合作为首个最小 Visual Provider 集成候选 |
| `codex/mediakit-provider` | 本地媒体处理 Provider 与素材检查 UI | 与视觉 Provider 有继承关系，但不是导演包本身 |

| `codex/code-visual-provider-v1` | Multi-Provider Automatic Visual Production v2：Auto Router、Stickman + Code Visual 混合批次、动态 MP4、candidate approval、Preview/JianYing 浏览器验收 | 新 Draft PR，尚未合并 main；以 [`MULTI_PROVIDER_AUTOMATIC_VISUAL_PRODUCTION_V2.md`](MULTI_PROVIDER_AUTOMATIC_VISUAL_PRODUCTION_V2.md) 为准 |
| `codex/autonomous-video-factory-v3` | Autonomous Video Factory v3：Quick Start、Production Profile、AUTO/REVIEW、真实本地视觉生成、批量审核、增量 Scene 重跑、Preview/JianYing 编排 | 当前开发分支，尚未合并 main；以 [`AUTONOMOUS_VIDEO_FACTORY_V3.md`](AUTONOMOUS_VIDEO_FACTORY_V3.md) 和该分支测试为准 |
| `codex/director-pack-protocol-v1` | `IMPLEMENTED_ON_BRANCH`：安全 `.vfdirector`、安装/导出/派生、参考模板、Resolved Policy digest、Factory AUTO/REVIEW、HTTP/CLI/MCP/Skill、Preview/JianYing 浏览器验收 | 等待 Draft PR 合并；以 [`DIRECTOR_PACK_PROTOCOL_V1.md`](DIRECTOR_PACK_PROTOCOL_V1.md) 和当前 PR 检查为准 |

重要说法必须引用具体分支或文件。仅仅在 GitHub 中看到代码，不等于用户当前运行的 `main` 已拥有该功能。

## DESIGNED / FUTURE：已设计与未来方向

- `IMPLEMENTED_ON_BRANCH`：[Director Pack Protocol v1](DIRECTOR_PACK_PROTOCOL_V1.md)：声明式 Director Pack、参考模板、Resolved Policy 与 Agent 接口。
- `DESIGNED`：[Director Pack 与 GitHub AI 上下文设计](superpowers/specs/2026-08-11-director-pack-context-design.md) 中超出 v1 的 Studio/商业化部分。
- `DESIGNED`：[Director Pack 愿景](DIRECTOR_PACK_VISION.md) 中可执行 Visual Provider Pack 的第三方分发层。
- `FUTURE`：第三方 Pack 签名、沙箱、商店、支付和授权。
- `FUTURE`：AI 视频 Provider 与代码动画、AI 图片的混合镜头策略。

## 关键文件导航

- 产品入口：[README](../README.md)
- AI 图片链路：[AI_IMAGE_SCENE_PIPELINE.md](AI_IMAGE_SCENE_PIPELINE.md)
- Agent Video Factory：[agent-video-factory.md](structured-content/agent-video-factory.md)
- Fish 对齐工作流：[fish-aligned-workflow.md](structured-content/fish-aligned-workflow.md)
- Director Pack 愿景：[DIRECTOR_PACK_VISION.md](DIRECTOR_PACK_VISION.md)
- Director Pack v1 协议与真实能力：[DIRECTOR_PACK_PROTOCOL_V1.md](DIRECTOR_PACK_PROTOCOL_V1.md)
- 已批准设计：[2026-08-11-director-pack-context-design.md](superpowers/specs/2026-08-11-director-pack-context-design.md)
- 网页端 GPT Prompt：[web-gpt-product-review-prompt.md](../.agent/web-gpt-product-review-prompt.md)

## 给新 Agent 的工作规则

1. 先运行 `git status --short --branch`、`git log --oneline -12` 并确认当前分支。
2. 重要结论分成：观察到的事实、推断、建议、未验证项。
3. 不把 `EXPERIMENTAL_BRANCH`、`DESIGNED` 或 `FUTURE` 写成已上线能力。
4. 不覆盖未提交修改，不将 API Key、Token、本地用户数据或项目素材写入 Git。
5. 修改视觉链路前，确认 Preview 与剪映仍消费同一个 canonical timeline。
6. 修改 Scene 或素材绑定前，保留 `visualSourceHash` / `inputHash` 的过期保护。
7. 优先提取可验证的最小切片，不直接合并大型历史分支。

## 如何取得新鲜验证证据

不要沿用本页或旧对话中的测试数量。每次接手都重新执行：

```powershell
python -m pytest backend/tests tests vforge/tests -q -p no:cacheprovider
Set-Location frontend
npm run build
```

Windows 上如果 pytest 临时路径过长或被系统文件锁影响，应使用一个全新的短 `--basetemp` 路径，并保留最终退出码和完整汇总。外部付费 Provider 只能在用户明确授权并提供凭据时测试。
