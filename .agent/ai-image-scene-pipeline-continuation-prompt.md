# Video Forge AI 生图链路接力 Prompt

将下面内容完整提供给下一位 Codex、Claude Code 或其他代码 Agent：

---

你正在继续开发 Video Forge。

仓库与状态：

- GitHub：`https://github.com/Kvxw1105/video-forge.git`
- Windows 主目录：`D:\A-Project\video-forge`
- 本功能 worktree：`D:\A-Project\video-forge\.worktrees\ai-image-scene-pipeline`
- 功能分支：`codex/ai-image-scene-pipeline`
- 权威最新版本：先执行 `git fetch origin`，然后以 `origin/codex/ai-image-scene-pipeline` 的 HEAD 为准。
- 进入任何修改前必须运行：

```powershell
git status --short --branch
git log --oneline -12
git rev-parse HEAD
git rev-parse origin/codex/ai-image-scene-pipeline
```

产品目标：

Video Forge 是主产品，同时通过 API、CLI、MCP 和 Skill 向外部 Agent 提供视频生产能力。AI 生图阶段需要把结构化文案切成语义 Scene，以配音/字幕时间为权威，为每个 Scene 生成或回填图片，再由 Video Forge 完成精确时间轴、字幕、配音、BGM 支持、Preview 和剪映草稿。

不可改变的规则：

1. 不另建第二套 Project、VisualPlan 或 Timeline。
2. Scene 的时间来自字幕/配音；图片不能自行决定时长。
3. Preview 和 JianYing 必须消费同一个 canonical timeline。
4. Codex 生图额度通过 Agent 拉取/回填协议使用，Video Forge 后端不能伪装成能直接读取 Codex 额度。
5. 外接 API Key 仅存本地配置，不能写入项目、日志、文档或 Git。
6. `visualSourceHash` 或 `inputHash` 不匹配时必须拒绝绑定。
7. 保留手动上传替换路径。
8. 遵守 `AGENTS.md` 的 progressive contrast、浅色对比度和低饱和电影风格规则。
9. 不扩展到 AI 视频、自动选 BGM、多轨/PIP、转场、滤镜或新 Director runtime。

先阅读：

- `AGENTS.md`
- `docs/superpowers/specs/2026-08-11-ai-image-scene-pipeline-design.md`
- `docs/superpowers/plans/2026-08-11-ai-image-scene-pipeline.md`
- `docs/AI_IMAGE_SCENE_PIPELINE.md`

当前实现边界：

- `backend/models/image_generation.py`：批次、Item、候选和 Provider 严格模型。
- `backend/services/image_generation_service.py`：持久化、哈希、Agent 回填、Provider 调用、批准、重试。
- `backend/routers/image_generation.py`：设置与 Project-scoped Batch API。
- `frontend/src/components/factory/AIImageGenerationPanel.tsx`：Factory 内双通道操作面板。
- `vforge/client.py`、`vforge/cli.py`、`vforge/mcp_server.py`：Agent 接口。
- `vforge/skill/SKILL.md`：Codex 生图回填方法。
- `backend/shared/visual_scene.py`：修复 duration-only Block 的字幕源时间原点。

继续前必须验证：

```powershell
python -m pytest backend/tests tests vforge/tests -q -p no:cacheprovider
Set-Location frontend
npm run build
```

重点测试：

```powershell
python -m pytest `
  backend/tests/test_image_generation_service.py `
  backend/tests/test_image_generation_api.py `
  backend/tests/test_ai_image_scene_e2e.py `
  tests/test_vforge_image_generation_cli.py `
  tests/test_vforge_image_generation_mcp.py `
  -q -p no:cacheprovider
```

验证证据必须以当前命令输出为准，不要沿用旧的通过数字。没有真实 Provider 凭据时，不得声称真实付费生图已验证；mock Provider、Agent 回填和 no-paid-call smoke 可以验证协议与产品链路。

若发现主目录仍有未提交的 TTS 改动，不要覆盖或丢弃。先比较 feature branch、主目录和远端，再决定如何同步。完成任何新改动后，提交并推送 `codex/ai-image-scene-pipeline`，并清楚报告是否已集成和推送 `main`。

---

