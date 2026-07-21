# Structured Content 实施顺序

目标是增量引入 Episode/Block/Variant，不破坏现有 Project JSON、FFmpeg 预览或安全剪映导出。每个 PR 都应独立可验证，旧项目必须继续通过原路径。

## PR A：StructuredContent 数据模型与兼容读写

新增可选 `structuredContent` Pydantic 模型（Episode、Block、Variant 的最小字段），挂到 `backend/models/project.py:Project`。在 `backend/services/project_service.py` 保持原子 JSON 保存、备份和旧字段迁移；必要时在 `backend/routers/project.py` 增加 opt-in 读写接口。测试：缺省字段旧项目 round-trip、未知字段、坏结构拒绝、备份恢复。用户价值：可保存链式内容元数据而不迁移旧项目。

## PR B：Variant Compiler 与三个版本

新增纯模块 `backend/shared/variant_compiler.py`（或 `structured_content.py`），将 `publish`、`master`、`chapter` 解析为临时 Project View，随后调用 `backend/shared/timeline_compiler.py:compile_project_timeline`。不持久化派生结果，不复制时间计算。测试：同输入确定性、variant 选择、缺失 block/asset warning、legacy project unchanged。用户价值：同一内容可生成三种可复现时间线。

## PR C：Block 资产绑定与测试素材校验

在 structured content 模型中加入 `BlockAssetBinding` 的最小引用（asset id/path、role、trim/sourceStart），新增 service-level 校验，复用 library/project asset 解析。测试：路径边界、缺失素材、音频/画面绑定、FFmpeg/JianYing parity。用户价值：Block 不再依赖脆弱的文件名启发式。

## PR D：Fish Audio 对齐配音

扩展 `backend/engines/voiceover.py` 周边为 alignment provider/响应解析模块；保存可选 timestamp segments，支持一个 master audio 的多个 source ranges，并映射到已有 `sourceStart`。先用 fixture/contract tests，真实 API 另行开关，不在默认测试调用外部服务。用户价值：字幕、节奏和多版本配音可共享同一音频时间轴。

## PR E：Block GUI 与语义编辑服务

后端新增 block/variant service 后，再在 `frontend/src/pages/Editor.tsx` 和 `frontend/src/lib/api.ts` 增加最小浏览/编辑入口。旧编辑模式保留；没有 `structuredContent` 时 UI 仍显示现有 segments。测试：API contract、前端类型检查、最小交互回归。用户价值：用户能按语义块编辑，而非直接操作低层片段。

## PR F：Agent/MCP Composition 接口

在 `vforge/client.py`、`vforge/mcp_server.py` 增加受限的 block/variant/composition 工具，复用后端服务和 OperationLog（若需要再单独建模），带幂等键和 dry-run。测试：schema、权限边界、幂等和旧 MCP 工具回归。用户价值：自动化生成/审查/导出链式内容。

## 第一刀文件边界与验收

第一刀（PR A+B）预计只改：

- `backend/models/project.py`
- `backend/shared/structured_content.py` 或 `backend/shared/variant_compiler.py`
- `backend/services/project_service.py`（仅在需要兼容保存辅助时）
- `backend/routers/project.py`（仅 opt-in 接口）
- 新增 `backend/tests/test_structured_content.py`、`backend/tests/test_variant_compiler.py`

不得直接改写 `compile_project_timeline`、`backend/engines/renderer.py`、`backend/adapters/jianying.py`、旧前端编辑语义。验收必须包括完整后端测试、legacy JSON round-trip、三种 variant 的确定性输出和 FFmpeg/JianYing 共享 compiler 调用。

## 数据库决定

前六个 PR 不需要数据库。JSON 已满足单 Episode/七 Block/三 Variant 的本地优先场景；只有并发协作、查询规模或审计日志成为真实瓶颈时，才另行评估 SQLite/数据库迁移。
