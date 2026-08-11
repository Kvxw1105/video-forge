# Autonomous Video Factory V3

> 本文记录 `codex/autonomous-video-factory-v3` 的实现边界。它不是 `main` 已上线能力；合并前请以当前分支测试和 CI 结果为准。

## 产品结果

V3 将“写完文案后还要手工串接配音、字幕、视觉和导出”收口为一条用户路径：

```text
文案 + Production Profile + AUTO/REVIEW
  → Generate Video
  → planning_visuals
  → generating_visuals
  → (REVIEW: awaiting_visual_approval)
  → binding_visuals
  → rendering_preview
  → exporting_jianying
  → succeeded
```

Quick Start 入口为 `/factory/new`，视觉审核入口为 `/factory/batches/:batchId/items/:itemId/visuals`。

## 不新增第二套时间线

Factory 只编排既有生命周期：`SceneRequest → ProviderResult → candidate → approval → asset import → Scene bind → canonical timeline`。它不直接改写 Scene timing；Scene 起止时间仍由配音/字幕决定。Preview 与 JianYing 均从同一个 structured variant / canonical timeline 编译。

## Production Profile

Profile 是薄策略对象，不是新的 Provider Kernel。当前内置：

| id | 用途 | 默认路由 | 审批策略 |
| --- | --- | --- | --- |
| `knowledge_explainer` | 概念、因果、流程、数据结构 | `code_visual` | 本地自动 |
| `psychology_cognition` | 认知、行为、心理叙事 | `stickman` | 本地自动 |
| `balanced_auto` | 混合内容默认值 | `auto` | 本地自动 |

策略字段包括 `candidateCount`、`fallbackOrder`、`autoApprovalPolicy`、`externalPolicy`、`durationPolicy`、`visualDensity`、`styleAnchor` 和 `continuityAnchor`。它们只影响路由和生成政策，不拥有修改 Scene timing 的权限。

## AUTO 与 REVIEW

- `AUTO`：本地 deterministic provider 生成后按 Profile 自动选择首个 candidate，并写入 `approvalAudit`；生成失败才进入 batch error。
- `REVIEW`：生成候选后暂停在 `awaiting_visual_approval`。Review All Visuals 支持逐 Scene 选择 candidate、Provider override、重新生成和批量 `Approve & Continue`。
- 无配音模式仍可继续 Preview/JianYing：后端生成确定性的静音 WAV，字幕时间仍是用户可见的 timing 来源，不消耗 TTS 额度。

## 增量重跑与恢复

配对台提供“保存文本并增量重跑当前 Scene”：

1. 只更新目标 Scene 的字幕文本，保留原有 start/end。
2. 清除目标 Scene 的旧视觉绑定，保留其他 Scene 的资产和绑定。
3. 通过同一 local provider lifecycle 生成新 candidate、审批并重新绑定。
4. `visualSourceHash`、Scene `inputHash` 和 Factory output hash 变化后，Preview/JianYing 仅重建过期输出。

历史视觉批次保留用于审计，但旧 source hash 批次不能再被批准到新 VisualPlan。

## 关键 API

```text
GET  /api/agent-factory/production-profiles
POST /api/batches/template-production
GET  /api/agent-factory/batches/:batch/items/:item/visuals
POST /api/agent-factory/batches/:batch/items/:item/approve-and-continue
POST /api/agent-factory/batches/:batch/items/:item/regenerate-visual
POST /api/agent-factory/batches/:batch/items/:item/scenes/:scene/edit-and-rerun
POST /api/agent-factory/batches/:batch/items/:item/resume
```

外部 Agent 仍可使用原有 Image Generation API；V3 没有另造 generation lifecycle。

## 证据与验收

浏览器验收脚本：`browser_v3_e2e.py`。它实际启动后的浏览器路径覆盖：

- AUTO Quick Start → 真实 candidates/绑定 → Preview/JianYing 状态成功。
- REVIEW Quick Start → Review All Visuals → Approve & Continue → succeeded。
- REVIEW 项目修改一个 Scene 文本 → 保存并增量重跑 → timing 保持不变 → 再次审批成功。

本地证据目录（运行脚本后生成）：

```text
C:\Users\kvxkf\.codex\visualizations\2026\08\12\autonomous-video-factory-v3
```

其中应包含 `01-auto-start.png`、`02-auto-finished.png`、`03-review-candidates.png`、`04-review-succeeded.png`、`05-incremental-rerun.png`、`06-incremental-succeeded.png` 和 `v3-browser-trace.zip`。

本轮本地真实成片验收（`engine=none`，所以不消耗 TTS 额度）已覆盖三条中文脚本，每条 10 个 Scene：

| 脚本 | 模式 / Profile | 结果 | Preview 时长 | ffprobe |
| --- | --- | --- | ---: | --- |
| 知识因果 | AUTO / `knowledge_explainer` | succeeded | 38.00s | H.264 1080×1920 + AAC |
| 心理认知 | REVIEW / `psychology_cognition` | succeeded | 38.25s | H.264 1080×1920 + AAC |
| 流程数据 | AUTO / `balanced_auto` | succeeded | 39.75s | H.264 1080×1920 + AAC |

三条都生成了 `draft_content.json` / `draft_meta_info.json` 和 JianYing draft media。JianYing 本轮验证级别为 `JY_STRUCTURE_VERIFIED`；未自动打开 GUI，因此不是 `JY_GUI_VERIFIED`。

截至本轮本地验证：`354 passed`，`npm run build` 成功；CI 结果应以推送后的 Draft PR 检查为准。

## 当前边界

- AI Image Provider 仍只有在用户配置凭据后才可声称真实外部调用；本 V3 验收使用 local deterministic providers。
- JianYing 已验证结构化 draft 的生成、发布和路径安全；没有在本轮自动操作 JianYing GUI，因此报告级别应写 `JY_STRUCTURE_VERIFIED` 与 `JY_GUI_NOT_VERIFIED`。
- 不包含 Pi runtime、Director Pack marketplace/payment、完整 AE 级动画系统或新的 Project/Timeline 模型。
