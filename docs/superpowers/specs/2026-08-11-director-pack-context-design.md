# Video Forge Director Pack 与 GitHub AI 上下文设计

日期：2026-08-11

状态：已批准

## 1. 目标

本阶段解决两个相互关联的问题：

1. 让网页端 GPT、Codex 和其他 Agent 只读取 GitHub 就能准确理解 Video Forge 当前能做什么、不能做什么、下一阶段有哪些已存在的实验资产，从而减少用户重复解释和 Token 消耗。
2. 为可 DIY、可分享、未来可付费的“导演包”建立稳定边界，使代码生成的火柴人、矢量动画、白板动画等素材能够接入 Video Forge，而不把任意可执行代码伪装成普通配置文件。

本阶段首先交付权威上下文文档与可复制 Prompt，不在未经独立集成审计的情况下直接把大型实验分支合入 `main`。

## 2. 已观察到的项目事实

### 2.1 `main` 已实现

- 普通文案与结构化内容能够进入 Project、Block、Scene 和 VisualPlan 工作流。
- Scene 时间由配音/字幕决定，图片不能自行决定时长。
- AI 图片支持两条通道：用户配置的 OpenAI-compatible Provider，以及 Codex/其他 Agent 领取任务后回填。
- 候选图片经过审批并绑定 Scene，Preview 与剪映草稿消费同一 canonical timeline。
- Video Forge 已提供 HTTP API、CLI、MCP 和 Skill 接入面。
- 配音、字幕、BGM、Preview 和剪映草稿仍由 Video Forge 负责。

### 2.2 尚未集成到 `main` 的实验资产

仓库存在以下独立分支，不能在对外文档中描述为主产品已上线能力：

- `codex/director-pack-studio-clean`
- `codex/pi-video-director`
- `codex/code-visual-renderer-pack`
- `codex/stickman-visual-provider`
- `codex/mediakit-provider`

这些分支已经探索过 Director Studio、版本化 Skill、Pack 导入导出、Pi Agent、火柴人素材、代码动画与本地媒体处理。它们规模较大且彼此存在继承关系，后续集成必须单独审计、拆分和验证，不能直接整枝合并。

### 2.3 现有 Director Pack V1 的安全边界

实验实现中的 Director Pack 是声明式文件：固定 Recipe、已发布 Skill 版本、风格参数、模板和允许调用的能力。导入时不会加载包内任意 Python 或 JavaScript。这是正确的基础，但它无法单独承载真正的代码渲染器。

## 3. 方案比较

### 方案 A：所有内容放进一个 Director Pack

Director Pack 同时携带导演规则、风格、模板和可执行渲染代码。

优点：安装概念最简单，一个文件看起来包办全部能力。

缺点：配置与代码共享同一信任边界；难以安全导入第三方包；版本、依赖、权限和付费授权都容易失控。

结论：不采用。

### 方案 B：Director Pack 与 Visual Provider Pack 两层模型

Director Pack 只描述“拍什么、怎么组织、选择哪些能力”；Visual Provider Pack 负责真正生成 SVG、PNG、透明视频或普通视频素材。

优点：声明式方案可以安全分享；可执行扩展拥有独立权限、签名和兼容性边界；一个 Director Pack 可以组合多种 Provider；AI 图片、代码动画和未来 AI 视频可以共存。

缺点：需要维护两个清晰概念，安装器和 UI 必须解释依赖关系。

结论：采用。

### 方案 C：导演包只保留声明式规则，不开放代码扩展

优点：实现和安全模型最简单。

缺点：火柴人、矢量动画等能力只能内置在 Video Forge，无法形成可 DIY、可分发的生态。

结论：可作为近期运行限制，但不是长期产品模型。

## 4. 两层架构

### 4.1 Director Pack

Director Pack 是可移植的制作方案，负责：

- 内容与镜头组织规则；
- Scene 粒度和字幕边界规则；
- 视觉风格、色彩、构图和素材策略；
- Recipe 与模板选择；
- Visual Provider 的选择与降级顺序；
- 需要人工审批的动作；
- 固定依赖的 Skill 和 Pack 版本。

Director Pack 不执行任意代码，也不包含密钥。它的输出是对现有 Project、VisualPlan 和 canonical timeline 的受控提案，不创建第二套项目或时间轴。

### 4.2 Visual Provider Pack

Visual Provider Pack 是素材生成能力包，负责将标准 Scene 请求转换为标准素材结果。可能的 Provider 包括：

- `stickman`：火柴人 SVG/PNG/动画；
- `vector-motion`：矢量图形和代码动画；
- `white-sketch`：白板/手绘风格；
- `code-diagram`：机制图、信息图、像素规则图；
- `ai-image`：外部生图 API 或 Agent 回填；
- 未来的 `ai-video`：AI 视频片段。

标准输入至少包含 `sceneId`、文本、起止时间、宽高比、风格参数和不可变 `inputHash`。标准输出至少包含素材文件、类型、尺寸、时长能力、内容哈希、Provider 身份和生成元数据。

Provider 生成素材，但不能改写 Scene 的权威时间。静态图片沿用 Scene 时长；视频素材需要经过 Video Forge 的裁剪、循环、变速或拒绝策略后才能进入时间轴。

### 4.3 调用关系

```text
User / Web GPT / Codex / Local Agent
                 │
                 ▼
            Director Pack
      镜头规则 · 风格 · Recipe · 策略
                 │
                 ▼
        Visual Provider Registry
     stickman · vector · AI image · future video
                 │
                 ▼
        Scene Candidates / Approval
                 │
                 ▼
     Video Forge canonical timeline
  字幕 · 配音 · BGM · Preview · JianYing
```

Pi Agent、Codex 和其他本地 Agent 均通过同一能力协议调用 Director Pack 与 Provider，不获得绕过审批或直接篡改项目文件的特殊通道。

## 5. 安全、版本与分发

### 5.1 Director Pack

- JSON/YAML 声明式格式；
- 固定 Skill 与 Provider 依赖版本；
- 导入前进行 schema 和 capability 校验；
- 不包含 API Key、Token 或用户项目数据；
- 已发布版本不可原地修改，更新产生新版本；
- 可导出、导入、禁用、回滚和卸载。

### 5.2 Visual Provider Pack

- 可执行代码与声明式 Pack 分离安装；
- V1 只允许内置或用户明确批准的本地 Provider；
- 需要声明文件读写、网络、子进程、GPU 和付费调用权限；
- 默认禁止读取项目范围外文件和密钥；
- 输出必须经过格式、大小、哈希和路径校验；
- 第三方付费分发、签名、许可证和沙箱属于后续独立阶段。

## 6. GitHub AI 上下文包

### 6.1 `docs/START_HERE_FOR_AI.md`

面向网页端 GPT 和新 Agent 的唯一入口，保持短而权威：

- 一句话产品定位；
- `main` 当前已实现能力；
- 明确的未实现边界；
- 最短核心数据流；
- 关键文件导航；
- 主线与实验分支状态表；
- 继续分析前必须读取的文档；
- 如何验证而不沿用旧测试数字。

README 首页只放醒目链接，避免复制整份内容造成漂移。

### 6.2 `docs/DIRECTOR_PACK_VISION.md`

解释两层模型、典型用例、包之间的依赖关系、安全边界和阶段路线。该文件是产品愿景，不宣称实验分支已经上线。

### 6.3 `.agent/web-gpt-product-review-prompt.md`

提供可直接复制给网页端 GPT 的 Prompt。Prompt 要求网页端 GPT：

1. 读取仓库 `main`，优先读取 `START_HERE_FOR_AI.md`；
2. 区分事实、推断、建议和实验分支；
3. 不把未合并分支描述成已上线能力；
4. 输出当前能力、关键缺口、下一阶段优先级和最小可验证切片；
5. 给出建议前引用具体文件或分支；
6. 不要求用户再次粘贴已经存在于 GitHub 的上下文。

Prompt 不硬编码容易过期的 commit SHA 或测试数量，只要求 GPT 读取当前 `main` 与最新命令证据。

## 7. 文档状态语言

所有能力必须使用下列标签之一：

- `AVAILABLE_ON_MAIN`：已在 `main`，且有可复核实现；
- `EXPERIMENTAL_BRANCH`：只存在于明确列出的分支；
- `DESIGNED`：有批准规格，但尚未实现；
- `FUTURE`：产品方向，没有实现承诺。

禁止使用“已支持”“已经完成”描述 `EXPERIMENTAL_BRANCH`、`DESIGNED` 或 `FUTURE` 内容。

## 8. 本阶段交付范围

### 包含

- 新增三份 GitHub AI 上下文文档；
- README 增加 AI 阅读入口，并修正明显过时的能力描述；
- 列出导演包和代码视觉素材实验分支；
- 提供一份节省重复上下文 Token 的网页端 GPT Prompt；
- 对文档执行链接、占位符、敏感信息和状态一致性检查；
- 提交并推送 GitHub。

### 不包含

- 合并 `director-pack-studio-clean` 或其他大型实验分支；
- 制作 Pack 安装器、商店、支付、授权或签名服务；
- 运行第三方任意代码；
- 新增 AI 视频 Provider；
- 重构现有 Project、VisualPlan 或 canonical timeline；
- 声称真实付费 Provider 已通过测试。

## 9. 验收标准

1. 网页端 GPT 只读取 GitHub 即可回答：Video Forge 当前能做什么、导演包是什么、哪些能力尚在实验分支。
2. `main`、实验分支、设计和未来方向不会在文档中混淆。
3. Prompt 可直接复制，不需要用户再次讲述完整产品历史。
4. Director Pack 与 Visual Provider Pack 的职责、输入输出和安全边界明确。
5. README 能在首屏附近引导 AI/Agent 进入权威上下文。
6. 文档不包含密钥、私人 Skill 配置或其他不应公开的个人内容。
7. 所有改动通过 `git diff --check`、占位符扫描、链接路径检查和敏感信息扫描。

## 10. 后续阶段建议

完成上下文包后，下一阶段应先做“实验分支能力清点与可移植提交图”，而不是直接整枝合并。推荐顺序：

1. 提取 Visual Provider 的稳定 contracts 与 registry；
2. 选择一个 `stickman` Provider 做最小集成；
3. 让 Director Pack 只引用已注册的 Provider；
4. 验证 Scene → 代码素材 → 审批 → canonical timeline → Preview/JianYing；
5. 再评估 Pi Agent、更多代码动画风格和第三方包分发。
