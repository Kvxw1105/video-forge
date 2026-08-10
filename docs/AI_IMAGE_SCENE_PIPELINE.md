# AI 生图 Scene Pipeline

Video Forge 可以把结构化文案、带时间戳配音和字幕转换成 `VisualPlan.scenes`，再让内置生图 Provider 或 Codex/其他 Agent 为每个 Scene 生成图片。图片批准后会成为项目素材并绑定到对应 Scene；Preview 和剪映草稿继续使用同一条 canonical timeline。

## 核心规则

- 配音和字幕决定 Scene 的 `start`、`end` 与 `duration`。
- 图片只绑定 Scene，不自行决定播放时长。
- 每个生图 Item 都带 `visualSourceHash` 和 `inputHash`；文案、字幕、时间或 Prompt 变化后，旧图片不能误绑定。
- Provider Key 只保存在本机 `config/ai_image_provider.json`，API 永远返回空 Key 和 `apiKeyConfigured`。
- Video Forge 后端不能直接读取 Codex 客户端的生图额度。Codex 应通过 Agent 通道拉取任务、调用自身生图工具并回填图片。

## 产品内使用

1. 从首页进入“文案到素材配对”，生成带配音时间戳的 Factory 项目。
2. 在素材配对台检查每个 Scene 的文案、时间和 Prompt。
3. 在“按配音时间生成画面”中选择：
   - `Codex / Agent 生图`：创建待回填任务，不产生外部 API 调用；
   - `外接 API 生图`：配置 OpenAI-compatible Base URL、API Key、模型和并发数。
4. 编辑全片视觉风格、连续性锚点和每个 Scene Prompt。
5. 外接 API 模式必须显式确认可能消耗额度。
6. 生成或回填后选择候选图，点击“批准并绑定候选”。
7. Factory 会重新验证 Scene 覆盖率；全部覆盖后可生成 Preview 和剪映草稿。

手动上传素材仍然保留，可以替换任何 AI 候选。

## Codex / Agent 工作流

启动 Video Forge 后端后：

```powershell
python -m vforge image-batch-create --pid proj_xxx --data '{"channel":"agent","providerId":"codex-imagegen"}'
python -m vforge image-batch-pending --pid proj_xxx --batch image_batch_xxx
```

`pending` 返回的每个 Item 包含：

- `sceneId`
- `blockId` 和 `subtitleIds`
- 精确 `start`、`end`、`duration`
- `text`
- `finalPrompt` 和 `negativePrompt`
- `aspectRatio`、`size`、`expectedFilename`
- 必须原样返回的 `inputHash`

Agent 对每个 Item 单独调用自己的生图能力，将结果保存到本地，再回填：

```powershell
python -m vforge image-batch-upload `
  --pid proj_xxx `
  --batch image_batch_xxx `
  --scene scene_story_001 `
  --input-hash 64位原始哈希 `
  --file D:\generated\scene_story_001.png
```

全部上传后选择并批准：

```powershell
python -m vforge image-batch-approve `
  --pid proj_xxx `
  --batch image_batch_xxx `
  --selections '[{"sceneId":"scene_story_001","candidateId":"candidate_scene_story_001_xxx"}]'
```

MCP 对应工具：

- `create_scene_image_batch`
- `get_scene_image_batch`
- `get_pending_scene_image_requests`
- `upload_scene_image_candidate`
- `approve_scene_image_candidates`
- `retry_scene_image_batch`

## 外接 API

设置接口：

```text
GET  /api/settings/ai-image
PUT  /api/settings/ai-image
POST /api/settings/ai-image/test
```

Provider 需要兼容：

```text
GET  {baseUrl}/models
POST {baseUrl}/images/generations
```

生成接口支持 `b64_json` 和远程 `url` 响应。远程结果仅允许 HTTP/HTTPS 图片；本地、私有、loopback 地址会被拒绝。下载受 Content-Type、格式和最大字节数限制。

Batch API：

```text
POST /api/projects/{projectId}/image-generation/batches
GET  /api/projects/{projectId}/image-generation/batches/{batchId}
GET  /api/projects/{projectId}/image-generation/batches/{batchId}/pending
POST /api/projects/{projectId}/image-generation/batches/{batchId}/run
POST /api/projects/{projectId}/image-generation/batches/{batchId}/upload
POST /api/projects/{projectId}/image-generation/batches/{batchId}/approve
POST /api/projects/{projectId}/image-generation/batches/{batchId}/retry
```

## 错误与恢复

- `visual_plan_missing`：先生成带字幕时间的 VisualPlan。
- `visual_plan_stale`：文案、字幕或 Block 已变化，重新生成 VisualPlan 和 Batch。
- `input_stale`：Agent 回填的 `inputHash` 不属于当前 Scene 请求。
- `provider_not_configured`：缺少启用状态、Base URL、API Key 或模型。
- `provider_image_url_blocked`：Provider 返回了本地或私有地址。
- `image_type_unsupported`：只接受 PNG、JPEG、WebP。

已成功的候选不会因单个 Scene 失败而丢失。“只重试失败项”只重置失败项。

## 验证边界

自动测试使用 mock Provider 和真实文件持久化验证整个状态机，不消耗付费额度。若交付记录没有明确列出真实 Provider 名称、模型和调用结果，就不能声称完成过真实付费生图验证。

