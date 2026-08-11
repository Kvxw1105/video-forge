# Video Forge Director Pack 愿景

状态：`DESIGNED`。仓库中存在相关 `EXPERIMENTAL_BRANCH`，但本页不表示这些能力已经进入 `main`。

## 为什么需要导演包

Video Forge 已经能管理文案、配音、字幕、素材和时间轴，但不同内容需要不同的镜头语言。知识视频可能需要机制图和信息卡，情绪故事可能需要火柴人或剪影，品牌视频可能需要固定色彩、构图和节奏。

导演包的价值不是再造一个剪辑器，而是把一套可复用的“怎么拍”交给 Pi Agent、Codex 或任意本地 Agent，并让 Video Forge 继续负责可靠的时间轴与输出。

## 两层模型

```text
文案、想法、Project
        │
        ▼
   Director Pack
镜头规则 · 风格 · Recipe · Provider 策略
        │
        ▼
Visual Provider Registry
stickman · vector-motion · ai-image · future ai-video
        │
        ▼
候选素材 → 审批 → Scene 绑定
        │
        ▼
Video Forge canonical timeline
字幕 · 配音 · BGM · Preview · JianYing
```

Director Pack 决定拍什么、如何组织以及应调用哪种能力；Visual Provider Pack 负责真正生成素材。二者不能共享同一个不受控的执行边界。

## Director Pack

Director Pack 是声明式、可移植、可版本化的制作方案，包含：

- 内容与镜头组织规则；
- Scene 粒度和字幕边界；
- 视觉风格、色彩、构图和节奏；
- Recipe、模板与素材策略；
- Provider 选择和降级顺序；
- 人工审批规则；
- 固定版本的 Skill 与 Provider 依赖。

**Director Pack 不执行任意代码**，也不携带 API Key、Token 或用户项目数据。它只能通过 Video Forge 已注册的 capability 提出 Scene Plan 或素材请求，不能直接修改项目文件。

## Visual Provider Pack

Visual Provider Pack 是受控的素材生成能力，可以是：

- `stickman`：火柴人 SVG、PNG 或动画；
- `vector-motion`：矢量图形与代码动画；
- `white-sketch`：白板、手绘或线稿；
- `code-diagram`：机制图、信息图和像素规则图；
- `ai-image`：外接图片 API 或 Agent 生图回填；
- `ai-video`：未来的 AI 视频片段。

Provider 可以生成 SVG、PNG、透明动画或普通视频，但**不能改写 Scene 的权威时间**。静态素材使用 Scene 时长；动态素材必须由 Video Forge 按明确策略裁剪、循环、变速或拒绝。

## 标准 Scene 请求与素材结果

最小 Scene 请求：

```json
{
  "sceneId": "scene_story_001",
  "start": 0.0,
  "end": 4.2,
  "text": "一个人推着越来越重的石头前进。",
  "aspectRatio": "16:9",
  "style": { "name": "warm-stickman", "palette": "parchment" },
  "inputHash": "scene-input-sha256"
}
```

最小素材结果：

```json
{
  "sceneId": "scene_story_001",
  "providerId": "stickman",
  "assetType": "image/svg+xml",
  "path": "generated/scene_story_001.svg",
  "contentHash": "asset-sha256",
  "inputHash": "scene-input-sha256",
  "metadata": { "template": "burden-boulder", "version": "1.0.0" }
}
```

Video Forge 必须拒绝 `inputHash` 不匹配、越界路径、格式不合法或超出大小限制的结果。Provider 结果先成为候选，审批后才能绑定 VisualPlan Scene。

## 典型组合

### 火柴人知识解释包

- Director Pack：一条字幕一个 Scene，优先使用隐喻型火柴人模板。
- Provider：`stickman` + `code-diagram`。
- 输出：低成本、风格统一、主要消耗 Agent Token 和本地渲染资源。

### 电影感图文包

- Director Pack：按语义段落切镜，统一色调和人物连续性。
- Provider：`ai-image`，失败时回退到用户素材库。
- 输出：AI 图片与字幕、配音精确对应。

### 混合品牌包

- Director Pack：品牌色、标题安全区、镜头密度和审批规则固定。
- Provider：`vector-motion` + 用户素材 + 可选 `ai-image`。
- 输出：代码动画、实拍素材和 AI 图片共用一个时间轴。

## 安全与版本边界

Director Pack：

- JSON/YAML 声明式格式；
- 已发布版本不可原地修改；
- 固定 Skill 和 Provider 版本；
- 导入时校验 schema、依赖和 capability；
- 可导入、导出、禁用、回滚和卸载。

Visual Provider Pack：

- 与声明式 Pack 分开安装；
- 声明文件、网络、子进程、GPU 和付费调用权限；
- V1 仅允许内置或用户明确批准的 Provider；
- 不得读取项目范围外文件或未授权密钥；
- 输出经过路径、格式、大小和哈希校验。

第三方签名、沙箱、许可证、付费商店和授权服务器属于 `FUTURE`，不能因为已有导入导出实验就宣称已经具备。

## 与 Pi Agent、Codex 和本地 Agent 的关系

Agent 是使用者和编排者，不是另一套视频工程格式：

1. Agent 读取 Project、字幕和可用 Pack。
2. Director Pack 生成受控 Scene Plan 与 Provider 请求。
3. Agent 调用已注册 Provider，或使用自身生图能力完成请求。
4. 结果作为候选回到 Video Forge。
5. Video Forge 校验、审批、绑定并生成 Preview/剪映草稿。

Pi Agent、Codex 和其他本地 Agent 使用同一个协议，不获得绕过审批、哈希校验或 canonical timeline 的特殊权限。

## 当前状态

| 状态 | 内容 |
|---|---|
| `AVAILABLE_ON_MAIN` | Project、结构化 Scene、AI 图片双通道、素材审批绑定、canonical timeline、Preview/剪映、API/CLI/MCP/Skill |
| `EXPERIMENTAL_BRANCH` | Director Studio、Pack registry、Pi Director、stickman、code-visual、MediaKit |
| `DESIGNED` | Director Pack / Visual Provider Pack 两层产品模型 |
| `FUTURE` | 第三方包签名与沙箱、商店与付费授权、AI 视频 Provider |

实验分支包括 `codex/director-pack-studio-clean`、`codex/pi-video-director`、`codex/code-visual-renderer-pack`、`codex/stickman-visual-provider` 和 `codex/mediakit-provider`。它们不能整枝合入当前 `main`，也不能当作已发布产品能力。

## 推荐集成顺序

1. 从实验分支提取稳定的 Visual Provider contracts 与 registry。
2. 以 `stickman` 做第一个只生成安全本地素材的最小 Provider。
3. 让声明式 Director Pack 只能引用已注册 Provider。
4. 验证 Scene → 代码素材 → 候选审批 → canonical timeline → Preview/JianYing。
5. 再接入更多矢量动画风格、Pi Agent 编排和第三方 Pack 分发。

完整设计约束见 [Director Pack 与 GitHub AI 上下文设计](superpowers/specs/2026-08-11-director-pack-context-design.md)。当前产品事实从 [AI / Agent 项目入口](START_HERE_FOR_AI.md) 开始阅读。
