# Structured Content 当前差距审计

审计基线：`main` / `d186b3c3de4c9ee8ad3b5c4f93824a30476c4495`。本文件只记录代码证据，不改变运行行为。

## 主线能力地图

| 能力 | 实现文件与入口 | 当前成熟度 | 测试/真实验证 | 明显缺口 |
|---|---|---|---|---|
| 安全剪映导出 | `backend/adapters/jianying.py`：`generate_jianying_draft`、`create_new`/`replace_explicit` 发布路径 | 稳定的非破坏写入链路 | `backend/tests/test_jianying_export_safety.py` 等；真实桌面仍标记 `REAL_JIANYING_VALIDATION_REQUIRED` | 版本兼容和真实客户端覆盖不足 |
| Canonical Timeline | `backend/shared/timeline_compiler.py`：`compile_project_timeline`、`CompiledTimeline` | 已作为 FFmpeg/JianYing 共同时间源 | timeline、adapter parity 测试 | 仍消费 legacy `segments`/`timeline.blocks`，无 Episode/Variant 语义 |
| FFmpeg/JianYing 一致性 | `backend/engines/renderer.py`、`backend/adapters/jianying.py` 均调用共享 compiler | 已实现并有边界测试 | renderer/JianYing parity 测试 | 真实剪映视觉验收未完成 |
| 视觉关键帧 | compiler `CompiledKeyframe`；`backend/adapters/jianying_keyframes.py` lowering | 已吸收 provider-neutral 关键帧 | keyframe 编译/草稿结构测试 | 真实桌面验证、更多属性仍有限 |
| 多配音版本 | `backend/models/project.py` 的 `voiceovers`/`Audio`；`backend/engines/voiceover.py` | 可生成和编译多个配音输入 | voiceover 与 timeline 测试 | 没有 master audio 多片段引用/对齐模型 |
| 字幕模型 | `Subtitle`、`backend/engines/subtitle.py`、`routers/subtitles.py` | 可导入/生成并进入预览与导出 | subtitle/API 测试 | 缺少 Block 级语义字幕绑定 |
| 项目 JSON 保存 | `backend/services/project_service.py`：`create_project`、`update_project`；`projects/<id>/project.json` | 生产使用中的 Pydantic JSON 持久化 | project service/migration 测试 | 尚无 `structuredContent` 可选字段 |
| 模板系统 | `backend/services/template_service.py`、`backend/models/template.py`、`backend/routers/template.py` | 可保存/应用 partial project 模板 | template 测试 | 模板不是 Episode/Variant/Composition |
| MCP | `vforge/mcp_server.py`、`vforge/client.py` | MCP 工具桥接现有 HTTP API | MCP 导入/工具测试 | 无结构化内容、Composition、操作日志工具 |
| Windows portable | `portable_entry.py`、`backend/launcher.py`、`backend/frontend_host.py` | 已发布 alpha，单进程托管前端 | packaging/启动检查 | 仍需更多用户环境验证 |
| System readiness | `backend/routers/system_readiness.py`、`backend/services/system_readiness.py` | 稳定 JSON 检查契约 | readiness 测试 | 尚无与链式内容/素材绑定联动 |

## VectCutAPI 吸收矩阵

证据来自锁定上游 `61391d06c6e5a3a472f2f82c1e679ae0dace09c4` 的源码调用链，以及 `docs/research/vectcut/`。A-E 含义见用户要求。

| 能力 | 级别 | 证据与判断 |
|---|---|---|
| 草稿创建/读取/保存 | B | VectCut `create_draft.py`、`save_draft_impl.py`、`pyJianYingDraft/script_file.py`；VideoForge 能创建并写 `draft_content.json`，但没有通用读取编辑 API |
| 视频轨/音频轨/文本轨/字幕 | B | VectCut `add_video_track.py`、`add_audio_track.py`、`add_text_impl.py`、`add_subtitle_impl.py`；VideoForge 有对应媒体、字幕模型，但轨道抽象更窄 |
| 多轨与画中画 | C | VectCut 通过命名 Track/相对 index 支持；VideoForge Project/Timeline 没有任意视觉轨模型，是高价值缺口 |
| 转场 | C | VectCut `add_video_track.py`、`add_image_impl.py` 暴露 transition；VideoForge 无同等导出语义 |
| 遮罩 | C | VectCut 视频/图片 API 与 pyJianYingDraft mask 类型；VideoForge 只有 overlay/变换，没有 mask lowering |
| 滤镜/特效 | C | VectCut `add_effect_impl.py` 和 pyJianYingDraft 枚举；VideoForge 仅有限 renderer 调整，不具备资源化 effect 模型 |
| 贴纸 | D | VectCut `add_sticker_impl.py` 使用资源 ID/贴纸轨；对当前 local-first 核心价值低于轨道和素材绑定 |
| 通用关键帧 | A | VectCut `add_video_keyframe_impl.py` -> `Track.process_pending_keyframes` -> `Visual_segment.add_keyframe` -> `Keyframe_list.export_json`；VideoForge 已有 `CompiledKeyframe` 与 JianYing lowering，六类 KFType 已覆盖 |
| 媒体导入 | B | VectCut `local_materials.py` 支持导入；VideoForge library/upload 已有本地路径流程，但没有 VectCut 的远程下载缓存任务模型 |
| 草稿复制/兼容/Profile | C | VectCut `draft_profiles.py` 有 profile/版本兼容逻辑；VideoForge 无 profile 抽象，当前固定生成器更易维护 |
| HTTP/MCP | B | VectCut `capcut_server.py`、`mcp_server.py` 直接进入草稿操作；VideoForge 有 MCP->HTTP bridge，但工具面聚焦项目/导出，不含 Composition |
| 远程 URL、任务缓存、外部服务 | E | VectCut 相关能力依赖其服务/下载链；与 VideoForge 本地优先和安全导出边界冲突，不建议复制 |

## 许可证与来源

上游为 Apache-2.0，锁定记录见 `docs/research/vectcut/upstream-lock.md`。VideoForge 当前没有复制 VectCut 源文件；`docs/THIRD_PARTY_NOTICES.md` 已说明仅作行为/数据格式参考。因此本轮无需新增 LICENSE/NOTICE。若未来复制或修改上游代码，需保留版权、许可证、修改声明及 Apache NOTICE 义务；机制借鉴不触发源代码复制义务。pyJianYingDraft 仍作为独立包依赖治理。

## 链式内容第一刀

推荐在现有 `Project` JSON 内增加可选 `structuredContent`（包含 `episode`、`blocks`、`variants`），而不是新建独立文件或数据库。理由是 `Project.model_validate`、`project_service.update_project` 和现有备份/恢复已经以单个 JSON 为边界；旧项目缺少该字段时继续走 `segments`/`timeline.blocks`，可做到零迁移。

Variant 应在调用 `compile_project_timeline` 之前由纯函数 Variant Compiler 解析为临时 legacy-compatible Project View，再复用现有 FFmpeg/JianYing adapter。不要改写 compiler、renderer、JianYing 安全发布事务或前端旧编辑器语义。第一刀是一个 Episode、七个 Block、三个 Variant（publish/master/chapter）的数据读写与确定性编译，不需要数据库。

## Fish Audio 接口缺口

`backend/engines/voiceover.py:synthesize_fish` 当前只 POST 普通 `https://api.fish.audio/v1/tts` JSON，接收二进制音频；不保存 word/segment timestamps，无 SSE，无 master audio 被多个片段引用的模型。Canonical audio clip 已有 `sourceStart`，但没有 Fish 对齐数据接入。后续需新增 alignment 响应解析/持久化模型、master 音频引用与切片策略，并在 voiceover/timeline tests 中验证；本轮不调用真实 API。

## 当前不应吸收

不复制 VectCut 的远程服务、下载 URL、缓存任务和其对剪映版本的隐含耦合；也不为贴纸、复杂特效、完整 Draft Profile 建立超出当前用户价值的架构。优先保持本地、安全、可测试的现有导出链。
