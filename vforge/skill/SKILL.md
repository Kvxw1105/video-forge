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
| `create_scene_image_batch` | 从当前 VisualPlan 创建 Agent 生图批次 |
| `get_pending_scene_image_requests` | 读取带精确时间与 Prompt 的待生图 Scene |
| `upload_scene_image_candidate` | 按 `sceneId + inputHash` 回填图片 |
| `approve_scene_image_candidates` | 批准候选并绑定到时间轴 Scene |
| `list_director_packs` | 列出已安装 Director Pack |
| `import_director_pack(file_path)` | 从本地 `.vfdirector` 归档安装 Pack |
| `get_director_pack(pack_id, version)` | 读取 Pack 安装 record 与 manifest |
| `resolve_director_pack(pack_id, version, run_mode)` | 编译只读 Resolved Policy 运行快照 |
| `export_director_pack(pack_id, version, output_path)` | 导出 `.vfdirector` 归档 |
| `derive_director_pack(pack_id, version, changes)` | 从现有 Pack 派生新 Pack（仅 editable 字段） |

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

### 使用 Codex/Agent 自身生图额度

当用户选择 AI 生图模式时，Video Forge 后端无法直接读取 Codex 客户端的额度。Agent 应作为生图 Provider，严格执行：

1. 调用 `create_scene_image_batch(pid, {"channel":"agent","providerId":"codex-imagegen"})`。
2. 调用 `get_pending_scene_image_requests(pid, batch_id)`。
3. 对每个 Item 使用其完整 `finalPrompt` 调用当前 Agent 的生图工具；不要合并多个 Scene，也不要改变 `sceneId` 或 `inputHash`。
4. 将输出保存为本地 PNG、JPEG 或 WebP。
5. 调用 `upload_scene_image_candidate(pid, batch_id, scene_id, input_hash, file_path)`。
6. 上传全部结果后调用 `approve_scene_image_candidates`，显式传入每个 `{sceneId, candidateId}`。
7. 回到 Factory 验证素材覆盖，再生成 Preview 与剪映草稿。

如果返回 `input_stale` 或 `visual_plan_stale`，停止上传并重新创建 Batch。不要直接修改 `project.json`，不要把一个 Scene 的图片绑定到另一个 Scene。

---

## Director Pack 协议（V1）

Director Pack 是一套可移植、声明式、可版本化的"怎么拍"方案（镜头规则、风格、Recipe 与 Provider 策略），由 VideoForge 后端校验、安装与解析。Agent 是编排者，不获得绕过审批或直接篡改项目文件的特殊通道。

### 读取策略：只读的 Resolved Policy

Agent 用以下两个 tool 读取已安装 Pack 与其运行策略：

- `list_director_packs` — 列出全部已安装 Pack（含内置 `kvxw/knowledge-cinematic`）。
- `resolve_director_pack(pack_id, version, run_mode)` — 编译 Resolved Policy 运行快照，`run_mode` 只能是 `auto` 或 `review`。

Resolved Policy 是**只读运行快照**，关键字段：

| 字段 | 含义 |
|------|------|
| `pack.manifestDigest` | 安装时冻结的 manifest 摘要，用于审计与恢复 |
| `effectiveRouting` | 实际可用的 intent → Provider 路由（缺失的 Provider 已被移除，不会凭空补路由） |
| `effectiveApproval` | 生效的审批模式（`auto` / `review`），review 永远不能被降级为 auto |
| `effectiveReferences` | 安装目录内已校验存在的引用/预设资产 |
| `status` | `enabled` / `enabled_with_degradation` / `blocked` |
| `providers[]` | 只暴露 `ready` / `trust` / `version` / `templateIds`，**绝不返回 credential value** |

### 必须遵守的边界

1. **Resolved Policy 已冻结**：routing / approval / authorization 在解析时已冻结。Agent 不得绕过审批或权限直接修改绑定；不得把 `review` 模式的结果当作 `auto` 使用。
2. **Provider 只读**：`resolve` 结果中的 Provider 是执行期能力视图，不是可编辑的配置。
3. **外部 / 付费 Provider 默认禁用**：V1 只执行本地 Provider 策略。`effectiveApproval.allowExternal` / `authorization.externalAllowed` 默认为 `false`，Agent 不得声称可调用外部付费能力。
4. **derive 只允许 editable 字段**：`derive_director_pack` 的 `changes` 必须包含新的 `id` 与 `version`，且只允许源 manifest `editable` 列表内的字段，其他字段会被后端拒绝。派生包不建立运行时继承。
5. **import / export 是本地操作**：`import_director_pack` 校验 schema、依赖与 capability；`export_director_pack` 输出 `.vfdirector` 归档。两者都不执行包内任意代码。

完整协议文档见 `docs/DIRECTOR_PACK_PROTOCOL_V1.md`。

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
