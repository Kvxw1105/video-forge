# Multi-Provider Automatic Visual Production v2

状态：`codex/code-visual-provider-v1`，独立于 PR #32。

## 目标链路

```text
script -> subtitles/alignment -> VisualPlan Scenes
       -> deterministic router -> Stickman / Code Visual
       -> candidates -> approval -> Scene binding
       -> canonical structured timeline -> Preview -> JianYing
```

项目仍只有一个 Project、一个 VisualPlan 和一个 canonical timeline。Provider 只能读取 `SceneRequest`，不能改写 Scene 的 `start/end/duration`。

## Provider contract

`backend/visual_providers/contracts.py` 定义：

- `SceneRequest`：项目、VisualPlan、Scene、字幕、时间窗、尺寸和只读语义选项。
- `ProviderResult`：provider/version/inputHash、媒体类型、静态/动态 asset kind、duration policy、sidecar 和 metadata。
- 动态输出支持 `exact`、`crop`、`loop`、`speed_adjust`、`reject`；`exact/reject` 在本地 runner 中校验输出时长，不允许 Provider 私自改变 Scene timing。

## Router 与混合批次

`backend/visual_providers/router.py` 是轻量、可审计的 Auto Router：

- 人物、关系、情绪、冲突等语义路由到 `stickman`。
- 关键词、因果、流程、对比、排名/数据、拓扑、机制等结构化语义路由到 `code_visual`。
- 批次支持 `routingMode=auto|stickman|code_visual`，单 Scene 可用 `sceneOverrides[sceneId].providerId` 覆盖。

一个 Image Generation Batch 可以混合多个 Provider；每个 item 保存 `providerId`、`providerVersion`、`routingReason`、`routingConfidence`、`inputHash` 和 duration metadata，仍走同一个 candidate/approval/bind lifecycle。

Agent 可通过 `GET /api/settings/ai-image/providers` 发现当前本地 Provider registry 与支持的 routing modes。

## Code Visual Provider v1

`backend/visual_providers/code_visual.py` 将旧 `code-visual-renderer-pack` 的 renderer/template/motion 方向适配到当前 Provider contract：

- keyword/core concept
- causal relationship
- process/progression
- comparison
- ranking/simple data
- topology/node-link
- mechanism diagram

PNG 是 canonical 静态资产；设置 `outputMode=video` 时，Provider 用确定性 FFmpeg `zoompan` 生成与 Scene duration 对齐的 MP4，并保留 SVG sidecar。FFmpeg 不可用时安全回退 PNG，并把 `renderMode=static_fallback` 写入 metadata。

旧分支的 renderer 家族、主题、motion plan 和视频验证原则被压缩为当前 `CodeVisualProvider` 的结构化模板、seed、sidecar、duration validation；没有引入第二套 generation lifecycle、Project 或 Timeline。

## Candidate 与重新生成

- local candidateCount 支持 `1/2/4`。
- candidate seed = `sha256(inputHash + provider + candidateIndex)`；同一 Scene 的 inputHash 不变，candidate contentHash/candidateId 不同。
- approval 可以选择任意 candidate。
- Scene 重新绑定时只保留当前 `visualAssetIds=[assetId]`，避免重复生成累积陈旧绑定。
- JianYing output 只有在 `draft_content.json` 存在时才视为可复用；空目录会被重新生成。

## UI

Factory Visual Pairing 的 Visual Production 面板支持：

- Auto、Stickman、Code Visual 三种本地路由；本地不消耗外部额度。
- 每个 Scene 的 Auto/Stickman/Code Visual override。
- 自动生成缺失视觉、单 Scene 重新生成、统一候选选择和批准绑定。
- Code Visual 动态 MP4 开关；候选卡片按 MIME 类型使用 `<img>` 或 `<video>`。
- 批准后 coverage 刷新，随后从同一个 Factory item 生成 Preview 与 JianYing draft。

## 验证记录

- Backend pytest：`337 passed`。
- Frontend build：`npm run build` 通过；Vite 仅报告既有 chunk size warning。
- Browser E2E：Playwright 独立 Chromium，6 个中文 Scene；Scene 01 显式 Code Visual override，Scene 02 显式 Stickman override，其余由 Auto Router 选择；实际生成动态 Code Visual MP4 与 Stickman PNG，选择/批准/coverage/单 Scene regenerate 均完成。
- Browser console：无 console/page error；本轮 API 新增 4xx/5xx：无。
- Preview：`ffprobe` 实测 `12.5s`。
- JianYing：生成 draft，`draft_content.json` 实际存在（约 30 KB）。
- Playwright 证据目录：`C:\Users\kvxkf\.codex\visualizations\2026\08\12\code-visual-provider-v1`，包含 initial、mixed candidates、coverage、preview/JianYing screenshots 与 `v2-browser-trace.zip`。
- PR #32：未修改。

## 下一步

建议后续分支名：`codex/code-visual-renderer-pack-v2`。下一阶段再把旧 renderer 的 SVG layer/motion profile 逐个提升为可配置 Director Pack，不改变本轮已经验证的 Provider Kernel。

## Verification matrix (English summary)

- Local backend: `python -m pytest backend/tests -q` -> `337 passed` with the optional FFmpeg toolchain installed.
- GitHub CI run `31518123652`: backend `336 passed, 1 skipped`; the only skip is the Preview/ffprobe integration test when the runner has no `ffmpeg`/`ffprobe`. Compileall, frontend `npm run build`, diff check, and credential scan all passed.
- Browser E2E evidence is retained at `C:\Users\kvxkf\.codex\visualizations\2026\08\12\code-visual-provider-v1`, including screenshots and `v2-browser-trace.zip`.
