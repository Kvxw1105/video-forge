# Director Pack Protocol v1 — 实施执行记录

> 本文件是实施计划的执行留痕,记录每个任务的产出、测试证据、提交与回退点。
> 计划原文:`docs/superpowers/plans/2026-08-13-director-pack-protocol-v1.md`
> 实现分支:`codex/director-pack-protocol-v1`(自 PR #34 head `ce5251261` 创建)

## 执行方式

- 波次执行 + 每波汇报;子 agent 只产代码,由主 agent 验证后按任务独立 commit
- 每个 Task 一个 commit,可单独 `git revert` 回退
- 验收证据统一记录于本节,供高级 agent 复核

## 波 1(完成)

### Task 1 — 严格协议模型 + 公开 Schema ✅

- 产出:
  - `backend/shared/director_intents.py` — 唯一 Scene intent 枚举(10 个)
  - `backend/models/director_pack.py` — 严格 Manifest 模型(`extra="forbid"`,PACK_ID/SEMVER 正则,intent key 校验,Skill 仅 advisory)
  - `docs/schemas/director-pack-v1.schema.json` — 公开 JSON Schema(含 `additionalProperties: false`)
  - `backend/tests/test_director_pack_models.py` — 23 个测试
- 证据:`pytest tests/test_director_pack_models.py` → **23 passed**
- 提交:`31b8def feat: define director pack protocol v1`

### Task 2 — Provider 版本/信任/模板目录 ✅

- 产出:
  - `backend/visual_providers/contracts.py` — `VisualProvider` 协议增加 `trust` / `template_ids`
  - `backend/visual_providers/registry.py` — `list_providers()` 返回 trust/templateIds
  - `backend/visual_providers/stickman.py` / `code_visual.py` — 声明模板目录
  - `backend/visual_providers/router.py` — 规则 key 锁定 SCENE_INTENTS,fallback 返回 `generic`
- 证据:`pytest tests/test_multi_provider_visual_production.py` → **6 passed**
- 提交:`28c435f feat: expose provider template catalogs`

### Task 3 — 安全 archive + install/derive/export/uninstall ✅

- 产出:
  - `backend/services/director_pack_archive.py` — 安全解包(ZIP slip/symlink/危险后缀/重复路径/超限拒绝),`yaml.safe_load`
  - `backend/services/director_pack_store.py` — 原子安装 + `installation.json`;同 id/version 不同 digest 冲突;导出确定排序;派生限 editable 路径;卸载只删包目录
  - `backend/config.py` — `DIRECTOR_PACKS_DIR`
- 证据:`pytest tests/test_director_pack_archive.py` → **14 passed**(含真实攻击载荷)
- 提交:`dfe8981 feat: add safe director pack lifecycle`

### Task 4 — 编译唯一 Resolved Director Policy ✅

- 产出:
  - `backend/models/director_pack.py` — 新增 `ResolvedDirectorPolicy` 等只读快照模型
  - `backend/services/director_policy_resolver.py` — `resolve()` / `resolve_installed()` / `policy_digest()`
- 关键语义:可选 Provider 缺失→删 route 不发明替代;`review` 永不降级 `auto`;模板 ID 校验;reference 存在性校验;preset YAML 纯数据;required 缺失/无 route→`blocked`;digest 固定
- 证据:`pytest tests/test_director_policy_resolver.py tests/test_director_pack_builtin_resolve.py` → **11 passed**
- 提交:`265aa02 feat: resolve immutable director policies`
- 备注:蜂群 agent-0 被终止零产出,由主 agent 接手完成

### Task 5 — 内置 Knowledge Cinematic Pack ✅

- 产出:
  - `director_packs/builtin/kvxw/knowledge-cinematic/1.0.0/` — manifest + 3 个静态 SVG 参考 + palette preset
  - `backend/services/director_pack_archive.py` — `validate_svg_content()`(拒绝 script/foreignObject/URL/事件属性,大小写不敏感)
  - `backend/services/director_pack_store.py` — `install_builtin()`(固定 zip 时间戳,digest 稳定、幂等)
- 证据:archive 套件 **31 passed**(原 21 + 新增 10)
- 提交:`819a65f feat: ship knowledge cinematic director pack`
- 备注:蜂群 agent-1 完成,交付质量高未返工

### 波 1 全量回归

`pytest backend/tests -q` → **407 passed**(原 330 + 新增 77),无回归。

## 波 2(进行中)

### Task 6 — 接入 Factory 生命周期(不建第二套生命周期)

- 状态:完成
- 产出:
  - `backend/models/template_batch.py` — `DirectorPackSelection` + `TemplateBatchSpec.directorPack`,与 `productionProfile` 互斥(validator 拒绝同传)
  - `backend/services/factory_visual_orchestrator.py` — 统一 `EffectiveVisualPolicy`;`resolved_policy_from_profile()` 适配 V3 行为;`effective_policy_from_director()` 适配 Resolved Policy;Director Pack 按 Scene intent 路由(复用 Router 的 `rules_hit`),fallback 只走 Manifest 声明链,approval audit 前缀 `director_pack:<id>`
  - `backend/services/agent_factory_service.py` — Resolve Director Pack、item manifest 持久化 `directorPack` + `resolvedDirectorPolicy` 快照;恢复时直接读快照不重新 Resolve
  - `backend/services/template_batch_service.py` — batch/item manifest 增加 `directorPack`、`resolvedDirectorPolicy` 字段
  - `backend/models/director_pack.py` — `ResolvedDirectorPolicy` 增加运行策略事实(candidateCount/motionPreference/durationPolicyVideo/continuityAnchor)
  - `backend/tests/test_director_pack_factory_e2e.py` — 6 个 e2e(互斥、AUTO 固定快照、混合 Provider、REVIEW 暂停/继续、manifest 持久化、resume 冻结快照)
- 证据:Task 6 e2e **6 passed**;相关回归 **83 passed**(含 V3 Profile 路径无退化)
- 提交:`41b16de feat: run director packs through factory lifecycle`

### Task 7 — HTTP + CLI + MCP 同一协议能力(蜂群 3 agent 并行)

- 状态:完成
- 产出:
  - `backend/routers/director_packs.py` — 9 个固定端点;import 流式写入+50MB cap+临时清理;export 用 FileResponse+BackgroundTask 延迟清理;错误映射 404/409/422 + 路径脱敏(不泄露绝对路径)
  - `backend/main.py` — 注册 router
  - `backend/tests/test_director_pack_api.py` — 7 个测试(全链 + 冲突 + 404 + 可执行载荷拒绝)
  - `vforge/client.py` — 9 个 Director Pack 函数(纯追加)
  - `vforge/cli.py` — 9 个命令(list/import/show/resolve/export/derive/enable/disable/uninstall)
  - `vforge/mcp_server.py` — 6 个 tools,run_mode/changes 校验,docstring 中文
  - `vforge/skill/SKILL.md` — Resolved Policy 只读边界章节
  - `vforge/tests/test_director_pack_cli.py` — 14 个单元测试(monkeypatch client,不依赖后端)
- 证据:API+CLI **21 passed**;vforge 全量 **18 passed**;真实 HTTP 端到端(import→resolve→export→derive→conflict 409→delete→404)全绿;MCP import OK
- 提交:`a8daee4 feat: expose director packs to agents`

### Task 8 — 产品入口与内置包启动

- 状态:完成
- 产出:
  - `/director-packs` 管理页：导入、详情、参考模板、preset、Resolved Policy、导出、派生、启停与卸载
  - `/factory/new`：Production Profile / Director Pack 互斥选择，继续使用 AUTO/REVIEW 与既有生命周期
  - 内置 `knowledge-cinematic` 首次使用自动安装；派生包生成完整不可变 archive 并立即安装
  - 安装资产安全读取 API；列表补齐名称、描述、参考数量和 Provider 依赖
- 证据:`npm run build` 成功
- 提交:`46d6937 feat: add director pack product entry`

### Task 9 — 浏览器主链与缺陷收口

- 状态:完成
- 浏览器发现并修复:
  - 内置 SVG 缺少 namespace，HTTP 200 但 Chromium 无法解码；现在仅放行标准 SVG namespace，其他远程 URL 仍拒绝
  - Director Pack 完成视觉绑定后未进入 structured output 路径，导致 JianYing 路由返回类型错误；现与 Production Profile 使用相同 output hash / canonical variant 路径
  - 安装列表把 preset 误计入参考模板数量；现只统计真实 reference
- 浏览器证据:
  - 3 张参考模板真实解码；导出/导入/派生成功
  - AUTO：4/4 coverage，混合 `code_visual + stickman`，Preview/JianYing 成功
  - REVIEW：页面显示 8 张候选，选择后 Approve & Continue，最终 `succeeded`
  - Console error / page error / 新增 5xx 均为 0
  - Preview：H.264 1080×1920 + AAC，26.75 秒；JianYing `JY_STRUCTURE_VERIFIED` / `JY_GUI_NOT_VERIFIED`
- 证据目录:`C:\Users\kvxkf\.codex\visualizations\2026\08\13\director-pack-protocol-v1`

## 验收清单(最终交付时核对)

- [x] 后端全量测试 PASS：`423 passed in 199.83s`
- [x] 前端 `npm run build` PASS
- [x] HTTP / CLI / MCP 返回同一 Resolved Policy digest：`sha256:06f67967fa349e1d0743bff52e2f8d0f7100ade2db3ecc1e1d1bf74db8fa1bb9`
- [x] 浏览器 E2E（内置启动→参考模板→导出/导入→派生→AUTO→REVIEW）
- [x] Preview 经 ffprobe 验证；JianYing 结构验证
- [x] `docs/START_HERE_FOR_AI.md` 状态标签更新（IMPLEMENTED_ON_BRANCH/DESIGNED/FUTURE）
