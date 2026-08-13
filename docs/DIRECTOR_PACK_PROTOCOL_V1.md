# Director Pack Protocol v1

状态：`IMPLEMENTED_ON_BRANCH`。实现分支为 `codex/director-pack-protocol-v1`；合并前不应描述为 `main` 已发布能力。

## 它解决什么问题

Director Pack 是一份可分发、可版本化、纯数据的“导演策略”。它告诉 VideoForge：不同语义的 Scene 应优先使用哪个 Provider、参考什么构图和配色、生成多少候选，以及采用 AUTO 还是 REVIEW。它不渲染素材，也不拥有 Project、VisualPlan、Scene timing 或 Timeline。

```text
Director Pack Manifest
  → Resolved Director Policy（固定 digest、Provider 版本和授权）
  → 现有 Factory / Provider Registry
  → SceneRequest → ProviderResult → Candidate → Approval → Bind
  → canonical timeline → Preview / JianYing
```

首个内置包 `kvxw/knowledge-cinematic@1.0.0` 会在首次访问时安装，组合 `code_visual` 与 `stickman`，适合知识、机制、因果、流程、数据和人物关系内容。

## 文件格式

扩展名为 `.vfdirector`，本质是受限 ZIP：

```text
director-pack.yaml                 # 唯一入口与规范真相
references/composition-guide.svg  # 构图参考
references/examples/*.svg         # 正例 / 反例
presets/palette.yaml              # 结构化参数
```

公开 Schema 位于 [`schemas/director-pack-v1.schema.json`](schemas/director-pack-v1.schema.json)。参考资产用于人和 Agent 理解风格；preset 用于机器读取固定参数；`templates` 只引用 Provider Registry 已登记的模板 ID。archive 内不允许 Python、JavaScript、Shell、安装脚本、远程资源或凭据。

## 运行时不变量

- 同一 `id + version` 必须对应同一 manifest/archive digest；修改产生新版本。
- 每次 Resolve 生成 `policyDigest`。该 digest 排除观测时间 `resolvedAt`，所以网页、HTTP、CLI 和 MCP 对同一输入得到相同策略标识。
- Run 会冻结 `manifestDigest`、`archiveDigest`、`policyDigest`、Provider 实际版本、信任等级和授权；恢复时使用保存的快照，不重新解释已运行任务。
- Production Profile 与 Director Pack 互斥。前者是快捷预设，后者是可分发策略。
- REVIEW 不能被降级为 AUTO；缺少必需 Provider 或没有可用路由时状态为 `blocked`。
- Provider 不能修改 Scene timing。静态素材沿用 Scene 时长；动态素材必须遵守 `exact/crop/loop/speed_adjust/reject`。

## 产品入口

- 网页：`/director-packs` 管理安装、详情、参考模板、Resolved Policy、启停、导出、派生和卸载。
- Factory：`/factory/new` 在 Production Profile 与 Director Pack 之间二选一，随后走 AUTO 或 REVIEW。
- HTTP：`/api/director-packs` 下提供 list/import/show/resolve/export/derive/enable/disable/uninstall 与安全资产读取。
- CLI：`python -m vforge.cli director-pack-*`。
- MCP：`list_director_packs`、`import_director_pack`、`get_director_pack`、`resolve_director_pack`、`export_director_pack`、`derive_director_pack`。
- Agent Skill：[`../vforge/skill/SKILL.md`](../vforge/skill/SKILL.md)。

示例：

```powershell
python -m vforge.cli --base http://127.0.0.1:8000 director-pack-resolve `
  --id kvxw/knowledge-cinematic --version 1.0.0 --mode review
```

## 安全与生命周期

导入会校验 ZIP slip、绝对路径、symlink、重复路径、文件数与大小、后缀白名单、YAML schema 和 SVG 主动内容。标准 SVG namespace 被允许，但其他 `http(s)` 内容仍会被拒绝。安装采用 staging + 原子替换；导出使用确定性排序；派生只允许 manifest 声明的 editable 字段，并安装为新的不可变版本；卸载只删除包，不删除历史 Project、候选、绑定或输出。

第三方签名、沙箱、商店、支付、DRM、Provider/Skill 自动安装和真实 AI Image/Video 付费调用不属于 v1。

## 本分支验收

浏览器脚本 [`../browser_director_pack_e2e.py`](../browser_director_pack_e2e.py) 覆盖：内置包启动、三张参考模板真实解码、导出/重新导入、派生、AUTO 混合 Provider、完整 coverage、Preview、JianYing draft、REVIEW 候选选择与批准。证据目录：

```text
C:\Users\kvxkf\.codex\visualizations\2026\08\13\director-pack-protocol-v1
```

最终一次本地结果：4/4 Scene coverage，`code_visual + stickman`，REVIEW 页面显示 8 张候选；Preview 为 H.264 1080×1920 + AAC、26.75 秒；JianYing 为 `JY_STRUCTURE_VERIFIED`，未自动打开 GUI，因此是 `JY_GUI_NOT_VERIFIED`。测试数量与 CI 状态以当前 PR 检查和执行记录为准。
