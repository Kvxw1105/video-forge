# Director Pack Protocol v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在 Automatic Video Factory V3 上实现可导入、校验、选择、运行、审计、导出和派生的 data-only Director Pack v1，并让 VideoForge AUTO、REVIEW、CLI、MCP 与外部 Agent 消费同一份只读 Resolved Director Policy。

**Architecture:** `.vfdirector` 是受限 ZIP archive，入口为 `director-pack.yaml`；Manifest 是分发时的规范真相，编译后的 Resolved Director Policy 是单次运行的只读策略快照。Director Pack 只引用已注册的 Provider、模板和 advisory Skill，不执行代码、不持有 Project/VisualPlan/Timeline；所有素材继续经过现有 `SceneRequest → ProviderResult → candidate → approval → Scene binding → canonical timeline` 生命周期。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、PyYAML safe loader、stdlib `zipfile/hashlib/pathlib`、React/TypeScript/Vite、pytest、Playwright、现有 VideoForge CLI/MCP。

---

## 0. 已拍板的产品宪法

实现过程中不得重新讨论或绕开以下约束：

1. Director Pack 永远是 data-only；`director-pack.yaml` 是规范真相。
2. Director Pack 不拥有 Project、VisualPlan、Scene timing、Timeline 或生成资产。
3. Director Pack 只能引用 VideoForge 已注册的 Provider、Provider template 和 advisory Skill。
4. 可执行 renderer 永远属于独立 Provider Pack；商业 Bundle 不改变安装与权限边界。
5. 同一 `id + version` 永远对应同一 manifest/archive digest；修改必须产生新版本。
6. 每次 Run 固定 Pack digest、Provider 实际版本、Skill 实际版本、协议编译器版本和用户授权。
7. AUTO、REVIEW、Pi、Codex、Local Agent 消费相同的 Resolved Director Policy。
8. Pack 可以声明 Scene segmentation proposal 能力，但 v1 运行时只消费已经存在的 VisualPlan Scene，不改分镜和时间轴。
9. Skill v1 默认且仅支持 `advisory`；缺少 Skill 不得改变 Manifest 的确定性基础行为。
10. 外部/付费 Provider 默认禁用；本阶段只保存和执行本地 Provider 策略，不实现真实扣费。
11. ProductionProfile 保留为无 Director Pack 时的快捷预设；一次运行只能选择二者之一。
12. 参考模板属于 Director Pack 的重要内容，但必须分为：参考资产、结构化 preset、已注册 Provider template 引用。任何渲染代码都不能进入 archive。

## 1. v1 明确不做

- Marketplace、支付、DRM、在线许可证、第三方密码学签名。
- 自动下载或安装 Provider/Skill。
- Python、JavaScript、Shell、Jinja、安装脚本、远程代码。
- 任意 `when:` 表达式、通用 DSL、DAG、多重 Pack inheritance。
- AI Image/AI Video 的真实 Provider 接入；Manifest 可以识别其依赖，但只有 registry 中存在且获授权时才能 Resolve。
- Director Studio 的完整可视化编辑器；v1 只提供选择、导入、详情、导出、派生和有限字段编辑。
- 运行时自动重切 Scene；只保留 `segmentationProposal: supported` 的协议扩展位。

## 2. 文件结构与职责

实现分支从 PR #34 当前 head `ce52512616642a368a6b0ea2631cec92a81d89` 创建，建议分支名 `codex/director-pack-protocol-v1`。不要修改或 force-push PR #34。

### 新建文件

- `backend/models/director_pack.py`：Manifest、依赖、参考模板、安装记录、Resolved Policy 的严格 Pydantic 模型。
- `backend/shared/director_intents.py`：唯一 Scene intent 枚举以及从现有 Router 规则得到 intent 的入口。
- `backend/services/director_pack_archive.py`：安全解包、文件白名单、路径校验、digest、大小限制。
- `backend/services/director_pack_store.py`：安装、列表、读取、启用、禁用、导出、派生、卸载。
- `backend/services/director_policy_resolver.py`：依赖解析、模板校验、降级、AUTO/REVIEW 交集以及只读快照生成。
- `backend/routers/director_packs.py`：Director Pack HTTP API。
- `backend/tests/test_director_pack_models.py`：协议字段、枚举和不可执行边界测试。
- `backend/tests/test_director_pack_archive.py`：ZIP slip、symlink、危险扩展名、digest、immutable 测试。
- `backend/tests/test_director_policy_resolver.py`：依赖、降级、权限、审批和模板引用测试。
- `backend/tests/test_director_pack_api.py`：导入、列表、详情、导出、派生、禁用/卸载 API 测试。
- `backend/tests/test_director_pack_factory_e2e.py`：Director Pack 到 Preview/JianYing 的服务级主链测试。
- `frontend/src/types/directorPack.ts`：前端稳定 DTO 类型。
- `frontend/src/components/factory/DirectorPackPicker.tsx`：导演包/快捷 Profile 互斥选择器。
- `frontend/src/pages/DirectorPacks.tsx`：安装包列表、导入、详情、依赖与降级状态、导出/派生入口。
- `director_packs/builtin/knowledge-cinematic/1.0.0/director-pack.yaml`：首个内置导演包。
- `director_packs/builtin/knowledge-cinematic/1.0.0/references/composition-guide.svg`：安全构图参考。
- `director_packs/builtin/knowledge-cinematic/1.0.0/references/examples/good-structured.svg`：正例。
- `director_packs/builtin/knowledge-cinematic/1.0.0/references/examples/bad-random.svg`：反例。
- `director_packs/builtin/knowledge-cinematic/1.0.0/presets/palette.yaml`：机器可读配色 preset。
- `docs/schemas/director-pack-v1.schema.json`：公开 JSON Schema。
- `docs/DIRECTOR_PACK_PROTOCOL_V1.md`：协议、目录、生命周期、安全边界与示例。
- `browser_director_pack_e2e.py`：浏览器真实用户路径与 trace/screenshot 保留脚本。

### 修改文件

- `backend/requirements.txt`：加入 PyYAML。
- `backend/config.py`：增加 `DIRECTOR_PACKS_DIR = CONFIG_DIR / "director-packs"`。
- `backend/main.py`：注册 `director_packs.router`。
- `backend/visual_providers/contracts.py`：为 Provider contract 增加只读 template catalog。
- `backend/visual_providers/stickman.py`、`backend/visual_providers/code_visual.py`：声明受支持模板 ID。
- `backend/visual_providers/registry.py`：公开 Provider 版本、信任级别和 template IDs。
- `backend/visual_providers/router.py`：复用统一 intent 枚举，不创建第二套路由语义。
- `backend/models/template_batch.py`：增加互斥的 `directorPack` 运行选择。
- `backend/services/factory_visual_orchestrator.py`：从统一 Effective Policy 驱动 Provider、candidate、fallback 和 approval。
- `backend/services/agent_factory_service.py`：Resolve Director Pack、保存运行快照并继续现有 Factory 生命周期。
- `backend/services/template_batch_service.py`：批次 Manifest 持久化 `directorPack` 和 `resolvedDirectorPolicy`。
- `frontend/src/lib/api.ts`：Director Pack API client。
- `frontend/src/App.tsx`：注册 `/director-packs` 页面。
- `frontend/src/pages/Home.tsx`：增加导演包入口。
- `frontend/src/pages/FactoryQuickStart.tsx`：使用互斥选择器并提交 `directorPack`。
- `vforge/client.py`、`vforge/cli.py`、`vforge/mcp_server.py`：向 Agent 暴露安装、列表、Resolve、导出和派生能力。
- `vforge/skill/SKILL.md`：解释 Agent 如何读取 Resolved Policy，且不能绕过审批/权限。
- `docs/START_HERE_FOR_AI.md`、`docs/AUTONOMOUS_VIDEO_FACTORY_V3.md`、`docs/DIRECTOR_PACK_VISION.md`：更新准确状态与入口。

## 3. 两份协议视图

### 3.1 Director Pack Manifest

Manifest 必须采用严格字段并拒绝未知字段。核心结构如下：

```yaml
format: videoforge.director-pack
formatVersion: 1
id: kvxw/knowledge-cinematic
version: 1.0.0
name: Knowledge Cinematic
description: 面向知识、认知、机制和人物关系内容的混合导演方法。
publisher:
  id: kvxw
  name: KV
compatibility:
  directorProtocol: 1.x
scenePolicy:
  strategy: semantic
  visualDensity: balanced
  segmentationProposal: supported
routing:
  default: [code_visual, stickman]
  intents:
    keyword: [code_visual, stickman]
    mechanism: [code_visual, stickman]
    process: [code_visual, stickman]
    causal: [code_visual, stickman]
    comparison: [code_visual, stickman]
    data: [code_visual]
    topology: [code_visual]
    human_action: [stickman, code_visual]
    relationship: [stickman, code_visual]
    generic: [stickman, code_visual]
style:
  anchor: cinematic editorial visual, restrained contrast, warm low-saturation palette
  avoid: [random style shifts, excessive text, unrelated decorative elements]
rhythm:
  visualDensity: balanced
  motionPreference: static
continuity:
  scope: project
  anchor: maintain palette, recurring character identity, hierarchy and composition language
candidates:
  count: 2
approval:
  defaultMode: auto
  auto:
    allowTrustedLocal: true
    allowExternal: false
    reviewOnFallback: true
    reviewOnWarnings: true
  review:
    requireCandidateSelection: true
durationPolicy:
  image: hold_to_scene
  video: crop
templates:
  - id: code_visual/causal
    provider: code_visual
    useFor: [causal, mechanism]
  - id: code_visual/process
    provider: code_visual
    useFor: [process]
  - id: stickman/inner_conflict
    provider: stickman
    useFor: [human_action, relationship]
references:
  - path: references/composition-guide.svg
    role: composition
  - path: references/examples/good-structured.svg
    role: positive_example
  - path: references/examples/bad-random.svg
    role: negative_example
presets:
  - path: presets/palette.yaml
    role: palette
dependencies:
  providers:
    - {id: code_visual, version: 1.x, required: false}
    - {id: stickman, version: 1.x, required: false}
  skills: []
fallback:
  missingOptionalProvider: continue
  missingRequiredProvider: block
  providerFailure: next_declared
  exhaustedProviders: review
editable: [style.anchor, rhythm.visualDensity, candidates.count, approval.defaultMode]
```

说明：两个本地 Provider 都是 optional；只要每个实际 intent 仍有可用白名单 route，Pack 可以降级启用。如果 Resolve 后所有 route 都为空，则必须 block。这避免把两个 Provider 都标为 required 后与“可降级”自相矛盾。

### 3.2 Resolved Director Policy

运行快照只读、无业务状态，必须至少包含：

```json
{
  "schemaVersion": 1,
  "compilerVersion": "1.0.0",
  "pack": {
    "id": "kvxw/knowledge-cinematic",
    "version": "1.0.0",
    "manifestDigest": "sha256:<64 hex>",
    "archiveDigest": "sha256:<64 hex>",
    "sourceTrust": "TRUSTED_BUILTIN"
  },
  "providers": [
    {"id": "code_visual", "version": "1.0.0", "trust": "TRUSTED_BUILTIN", "ready": true},
    {"id": "stickman", "version": "1.0.0", "trust": "TRUSTED_BUILTIN", "ready": true}
  ],
  "skills": [],
  "effectiveRouting": {},
  "effectiveApproval": {},
  "effectiveStyle": {},
  "effectiveReferences": [],
  "authorization": {
    "externalAllowed": false,
    "paidAllowed": false,
    "maxCostPerRun": 0
  },
  "degradations": [],
  "resolvedAt": "ISO-8601 UTC"
}
```

它可以附着在 batch/item manifest 中用于恢复与审计，但不能包含 Scene、candidate、binding 或 timeline 数据。

## 4. 实施任务

### Task 1: 建立严格协议模型和公开 Schema

**Files:**
- Create: `backend/models/director_pack.py`
- Create: `backend/shared/director_intents.py`
- Create: `backend/tests/test_director_pack_models.py`
- Create: `docs/schemas/director-pack-v1.schema.json`
- Modify: `backend/requirements.txt`

- [x] **Step 1: 写失败测试，锁定 Manifest 真相、intent 枚举和未知字段拒绝**

```python
from pydantic import ValidationError
from models.director_pack import DirectorPackManifest


def minimal_manifest() -> dict:
    return {
        "format": "videoforge.director-pack",
        "formatVersion": 1,
        "id": "kvxw/knowledge-cinematic",
        "version": "1.0.0",
        "name": "Knowledge Cinematic",
        "publisher": {"id": "kvxw", "name": "KV"},
        "compatibility": {"directorProtocol": "1.x"},
        "routing": {"default": ["code_visual"], "intents": {"causal": ["code_visual"]}},
        "style": {"anchor": "warm low-saturation", "avoid": []},
        "rhythm": {"visualDensity": "balanced", "motionPreference": "static"},
        "continuity": {"scope": "project", "anchor": "stable palette"},
        "candidates": {"count": 2},
        "approval": {"defaultMode": "auto"},
        "durationPolicy": {"image": "hold_to_scene", "video": "crop"},
        "dependencies": {"providers": [], "skills": []},
        "fallback": {
            "missingOptionalProvider": "continue",
            "missingRequiredProvider": "block",
            "providerFailure": "next_declared",
            "exhaustedProviders": "review",
        },
    }


def test_manifest_is_strict_and_data_only():
    manifest = DirectorPackManifest.model_validate(minimal_manifest())
    assert manifest.format == "videoforge.director-pack"
    assert manifest.routing.intents["causal"] == ["code_visual"]
    invalid = minimal_manifest() | {"installScript": "python setup.py"}
    try:
        DirectorPackManifest.model_validate(invalid)
    except ValidationError as exc:
        assert "installScript" in str(exc)
    else:
        raise AssertionError("unknown executable field must be rejected")
```

- [x] **Step 2: 运行失败测试**

Run: `cd backend && pytest tests/test_director_pack_models.py -q`

Expected: FAIL，提示 `models.director_pack` 不存在。

- [x] **Step 3: 实现 Pydantic 模型和固定 intent 类型**

`backend/shared/director_intents.py` 定义唯一枚举：

```python
from typing import Literal

SceneIntent = Literal[
    "keyword", "mechanism", "process", "causal", "comparison",
    "data", "topology", "human_action", "relationship", "generic",
]
SCENE_INTENTS: tuple[str, ...] = (
    "keyword", "mechanism", "process", "causal", "comparison",
    "data", "topology", "human_action", "relationship", "generic",
)
```

`backend/models/director_pack.py` 使用 `ConfigDict(extra="forbid")` 定义全部 v1 字段；关键约束为：

```python
PACK_ID = r"^[a-z0-9][a-z0-9_-]{0,63}/[a-z0-9][a-z0-9_-]{0,63}$"
SEMVER = r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$"

class CandidatePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: Literal[1, 2, 4] = 1

class DurationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image: Literal["hold_to_scene"] = "hold_to_scene"
    video: Literal["exact", "crop", "loop", "speed_adjust", "reject"] = "reject"

class SkillDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: str
    required: Literal[False] = False
    role: Literal["advisory"] = "advisory"

class DirectorPackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["videoforge.director-pack"]
    formatVersion: Literal[1]
    id: str = Field(pattern=PACK_ID)
    version: str = Field(pattern=SEMVER)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    publisher: Publisher
    compatibility: Compatibility
    scenePolicy: ScenePolicy = Field(default_factory=ScenePolicy)
    routing: RoutingPolicy
    style: StylePolicy
    rhythm: RhythmPolicy
    continuity: ContinuityPolicy
    candidates: CandidatePolicy
    approval: ApprovalPolicy
    durationPolicy: DurationPolicy
    templates: list[TemplateReference] = Field(default_factory=list, max_length=100)
    references: list[ReferenceAsset] = Field(default_factory=list, max_length=100)
    presets: list[PresetAsset] = Field(default_factory=list, max_length=50)
    dependencies: Dependencies
    fallback: FallbackPolicy
    editable: list[str] = Field(default_factory=list, max_length=32)
    derivedFrom: PackIdentity | None = None
```

- [x] **Step 4: 生成并提交公开 JSON Schema**

Run:

```powershell
cd backend
python -c "import json; from pathlib import Path; from models.director_pack import DirectorPackManifest; Path('../docs/schemas').mkdir(parents=True, exist_ok=True); Path('../docs/schemas/director-pack-v1.schema.json').write_text(json.dumps(DirectorPackManifest.model_json_schema(), ensure_ascii=False, indent=2), encoding='utf-8')"
```

Expected: `docs/schemas/director-pack-v1.schema.json` 存在，并包含 `additionalProperties: false`。

- [x] **Step 5: 运行模型测试并提交**

Run: `cd backend && pytest tests/test_director_pack_models.py -q`

Expected: PASS。

```bash
git add backend/models/director_pack.py backend/shared/director_intents.py backend/tests/test_director_pack_models.py backend/requirements.txt docs/schemas/director-pack-v1.schema.json
git commit -m "feat: define director pack protocol v1"
```

### Task 2: 让 Provider 正式公开版本、信任和模板目录

**Files:**
- Modify: `backend/visual_providers/contracts.py`
- Modify: `backend/visual_providers/registry.py`
- Modify: `backend/visual_providers/stickman.py`
- Modify: `backend/visual_providers/code_visual.py`
- Modify: `backend/visual_providers/router.py`
- Modify: `backend/tests/test_multi_provider_visual_production.py`

- [x] **Step 1: 写失败测试，证明模板引用可以被 registry 校验**

```python
def test_provider_registry_exposes_trust_and_template_catalog():
    providers = {item["providerId"]: item for item in list_providers()}
    assert providers["code_visual"]["trust"] == "TRUSTED_BUILTIN"
    assert "code_visual/causal" in providers["code_visual"]["templateIds"]
    assert "stickman/inner_conflict" in providers["stickman"]["templateIds"]
```

- [x] **Step 2: 运行失败测试**

Run: `cd backend && pytest tests/test_multi_provider_visual_production.py::test_provider_registry_exposes_trust_and_template_catalog -q`

Expected: FAIL，缺少 `trust` 或 `templateIds`。

- [x] **Step 3: 扩展 contract，但不改变 generate 生命周期**

```python
class VisualProvider(Protocol):
    provider_id: str
    provider_version: str
    trust: Literal["LOCAL", "UNVERIFIED", "TRUSTED_BUILTIN"]
    template_ids: tuple[str, ...]

    def generate(self, request: SceneRequest) -> ProviderResult:
        """Generate a candidate without changing project or timing state."""
```

`CodeVisualProvider` 声明 `code_visual/keyword`、`causal`、`process`、`comparison`、`ranking`、`topology`；`StickmanProvider` 声明 `inner_conflict`、`escape_enclosure`、`relationship_tug`、`burden_boulder`、`generic_two_person_relation`。Provider 内部 metadata 继续保留现有短 template 名称。

- [x] **Step 4: 统一 Router intent 名称**

将现有 `_CODE_RULES`、`_STICKMAN_RULES` key 限制到 `SCENE_INTENTS`，fallback 明确返回 `generic`，并把 `ProviderRoute.rules_hit` 作为 Resolver 的 intent 证据复用，不再新增 Director-specific 文本分类器。

- [x] **Step 5: 运行多 Provider 测试并提交**

Run: `cd backend && pytest tests/test_multi_provider_visual_production.py -q`

Expected: PASS。

```bash
git add backend/visual_providers backend/shared/director_intents.py backend/tests/test_multi_provider_visual_production.py
git commit -m "feat: expose provider template catalogs"
```

### Task 3: 实现安全 archive、安装、immutable、导出和派生

**Files:**
- Create: `backend/services/director_pack_archive.py`
- Create: `backend/services/director_pack_store.py`
- Create: `backend/tests/test_director_pack_archive.py`
- Modify: `backend/config.py`

- [x] **Step 1: 写 archive 攻击与 immutable 失败测试**

```python
def test_archive_rejects_executable_and_parent_path(tmp_path):
    bad = tmp_path / "bad.vfdirector"
    with ZipFile(bad, "w") as archive:
        archive.writestr("director-pack.yaml", VALID_MANIFEST)
        archive.writestr("../renderer.py", "print('owned')")
    with pytest.raises(DirectorPackArchiveError) as exc:
        inspect_archive(bad)
    assert exc.value.code in {"unsafe_path", "executable_payload"}


def test_same_id_version_cannot_change_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DIRECTOR_PACKS_DIR", tmp_path / "installed")
    first = store.install(PACK_A)
    assert first.status == "enabled"
    with pytest.raises(DirectorPackStoreError) as exc:
        store.install(PACK_A_CHANGED)
    assert exc.value.code == "immutable_version_conflict"
```

- [x] **Step 2: 运行失败测试**

Run: `cd backend && pytest tests/test_director_pack_archive.py -q`

Expected: FAIL，archive/store 模块不存在。

- [x] **Step 3: 实现固定安全限制**

`inspect_archive()` 必须：

```python
ALLOWED_SUFFIXES = {".yaml", ".yml", ".json", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".md"}
EXECUTABLE_SUFFIXES = {".py", ".pyc", ".js", ".mjs", ".cjs", ".exe", ".dll", ".bat", ".cmd", ".ps1", ".sh"}
MAX_FILES = 200
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
ENTRYPOINT = "director-pack.yaml"
```

每个 ZIP member 必须拒绝 absolute path、drive path、`..`、symlink、重复规范化路径、危险后缀和超限数据。YAML 只能通过 `yaml.safe_load()` 读取，且入口必须是 mapping。

- [x] **Step 4: 实现安装记录和原子写入**

安装目录固定为：

```text
CONFIG_DIR/director-packs/<publisher>/<slug>/<version>/
  director-pack.yaml
  references/...
  presets/...
  installation.json
```

`installation.json` 保存：`id/version/manifestDigest/archiveDigest/sourceTrust/status/degradations/installedAt`。先写同级临时目录，再用 `Path.replace()` 发布；Windows `PermissionError` 使用现有项目原子重试模式。相同 digest 重装应幂等成功，不同 digest 必须冲突。

- [x] **Step 5: 实现 derive/export/uninstall 语义**

- `export_pack(id, version)` 产生确定排序、固定时间戳的 `.vfdirector`。
- `derive_pack()` 只允许修改 Manifest `editable` 列出的路径，强制新 ID、新版本，并写入 `derivedFrom`；结果是完整 Manifest，不建立 inheritance runtime。
- `uninstall()` 只删除安装包目录，不触碰 Project、candidate、asset、binding、Preview 或 JianYing。
- 若历史 Run 引用已卸载 Pack，只允许读取旧的 Resolved Policy；regenerate 返回 `director_pack_not_installed`。

- [x] **Step 6: 运行 archive 测试并提交**

Run: `cd backend && pytest tests/test_director_pack_archive.py -q`

Expected: PASS。

```bash
git add backend/config.py backend/services/director_pack_archive.py backend/services/director_pack_store.py backend/tests/test_director_pack_archive.py
git commit -m "feat: add safe director pack lifecycle"
```

### Task 4: 编译唯一的 Resolved Director Policy

**Files:**
- Create: `backend/services/director_policy_resolver.py`
- Create: `backend/tests/test_director_policy_resolver.py`
- Modify: `backend/models/director_pack.py`

- [x] **Step 1: 写依赖降级、审批交集和空 route 失败测试**

```python
def test_resolve_degrades_optional_provider_but_never_invents_route(monkeypatch):
    monkeypatch.setattr(resolver, "list_providers", lambda: [STICKMAN_METADATA])
    policy = resolver.resolve(MANIFEST, run_mode="auto", authorization=LOCAL_ONLY)
    assert policy.status == "enabled_with_degradation"
    assert policy.effectiveRouting["relationship"] == ["stickman"]
    assert policy.effectiveRouting["data"] == []
    assert "provider_missing:code_visual" in policy.degradations
    assert policy.effectiveApproval.forceReview is True


def test_user_review_can_never_be_weakened_to_auto():
    policy = resolver.resolve(MANIFEST, run_mode="review", authorization=LOCAL_ONLY)
    assert policy.effectiveApproval.mode == "review"
```

- [x] **Step 2: 运行失败测试**

Run: `cd backend && pytest tests/test_director_policy_resolver.py -q`

Expected: FAIL，resolver 不存在。

- [x] **Step 3: 实现 Resolve 算法**

固定顺序：

```text
load immutable installed manifest
→ validate protocol compatibility
→ resolve registered Provider exact versions/template IDs
→ resolve advisory Skills（v1 可为空）
→ remove unavailable routes without inventing replacements
→ apply only manifest-declared fallback order
→ intersect user run mode, Provider trust, permission and cost authorization
→ compute effective approval
→ freeze ResolvedDirectorPolicy + digest
```

强制 REVIEW 条件：用户选 REVIEW、fallback 被采用、Provider override、warning、external/paid Provider、媒体类型降级、动态 duration policy 非 `exact`。AUTO 只有可信本地 Provider、合法 hash/candidate、无 hard warning、无强制 Review 时才可绑定。

- [x] **Step 4: 验证模板与参考资产**

- `templates[].id` 必须出现在相应 Provider 的 `templateIds`。
- `references[].path`、`presets[].path` 必须存在于安装目录且 digest 与安装记录一致。
- 参考资产只写入 `effectiveReferences`，不会直接作为 Provider 输出或 AUTO 唯一决策来源。
- preset YAML 只允许 mapping/list/scalar，无自定义 YAML tag。

- [x] **Step 5: 运行 Resolver 测试并提交**

Run: `cd backend && pytest tests/test_director_policy_resolver.py -q`

Expected: PASS。

```bash
git add backend/models/director_pack.py backend/services/director_policy_resolver.py backend/tests/test_director_policy_resolver.py
git commit -m "feat: resolve immutable director policies"
```

### Task 5: 提供内置 Knowledge Cinematic Pack 和真实参考模板

**Files:**
- Create: `director_packs/builtin/knowledge-cinematic/1.0.0/director-pack.yaml`
- Create: `director_packs/builtin/knowledge-cinematic/1.0.0/references/composition-guide.svg`
- Create: `director_packs/builtin/knowledge-cinematic/1.0.0/references/examples/good-structured.svg`
- Create: `director_packs/builtin/knowledge-cinematic/1.0.0/references/examples/bad-random.svg`
- Create: `director_packs/builtin/knowledge-cinematic/1.0.0/presets/palette.yaml`
- Modify: `backend/services/director_pack_store.py`
- Modify: `backend/tests/test_director_pack_archive.py`

- [x] **Step 1: 写内置 Pack 安装与双 Provider Resolve 测试**

```python
def test_builtin_knowledge_pack_has_real_references_and_mixed_routes():
    record = install_builtin("kvxw/knowledge-cinematic", "1.0.0")
    policy = resolve_installed(record.id, record.version, run_mode="auto", authorization=LOCAL_ONLY)
    assert policy.effectiveRouting["causal"][0] == "code_visual"
    assert policy.effectiveRouting["relationship"][0] == "stickman"
    assert {item.role for item in policy.effectiveReferences} == {
        "composition", "positive_example", "negative_example", "palette"
    }
```

- [x] **Step 2: 创建不含脚本的参考内容**

SVG 只能使用静态 `<svg>/<rect>/<circle>/<line>/<path>/<text>`，禁止 `<script>`、外链、`foreignObject`、事件属性和 remote font。配色 preset 固定为：

```yaml
background: "#1a1814"
surface: "#28231d"
primary: "#d8c3a5"
accent: "#b8956a"
muted: "#7a6e5a"
saturation: low
contrast: restrained
```

- [x] **Step 3: 安装时对 SVG 做主动内容校验**

除 archive 后缀白名单外，读取 SVG 文本并拒绝：`<script`、`foreignObject`、`javascript:`、`http://`、`https://`、`onload=`、`onclick=`。这一步防止“无 `.js` 文件但 SVG 内嵌执行内容”的绕过。

- [x] **Step 4: 运行测试并提交**

Run: `cd backend && pytest tests/test_director_pack_archive.py -q`

Expected: PASS。

```bash
git add director_packs backend/services/director_pack_store.py backend/tests/test_director_pack_archive.py
git commit -m "feat: ship knowledge cinematic director pack"
```

### Task 6: 接入 Factory，但不创建第二套生命周期

**Files:**
- Modify: `backend/models/template_batch.py`
- Modify: `backend/services/template_batch_service.py`
- Modify: `backend/services/agent_factory_service.py`
- Modify: `backend/services/factory_visual_orchestrator.py`
- Create: `backend/tests/test_director_pack_factory_e2e.py`
- Modify: `backend/tests/test_autonomous_video_factory_v3.py`

- [x] **Step 1: 写互斥选择和运行快照失败测试**

```python
def test_batch_rejects_profile_and_director_pack_together():
    spec = _spec("exclusive", "auto")
    spec["productionProfile"] = "balanced_auto"
    spec["directorPack"] = {"id": "kvxw/knowledge-cinematic", "version": "1.0.0"}
    with pytest.raises(ValidationError):
        TemplateBatchSpec.model_validate(spec)


def test_director_pack_run_pins_policy_and_uses_existing_candidates(monkeypatch, tmp_path):
    result = run_factory_with_builtin_pack(monkeypatch, tmp_path, mode="auto")
    row = result["items"][0]
    snapshot = row["resolvedDirectorPolicy"]
    assert snapshot["pack"]["id"] == "kvxw/knowledge-cinematic"
    assert snapshot["pack"]["manifestDigest"].startswith("sha256:")
    assert row["visualCoverage"]["complete"] is True
    assert row["status"] == "succeeded"
```

- [x] **Step 2: 扩展 batch 输入且保持向后兼容**

```python
class DirectorPackSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: str

class TemplateBatchSpec(BaseModel):
    # existing fields remain unchanged
    productionProfile: str | None = None
    directorPack: DirectorPackSelection | None = None

    @model_validator(mode="after")
    def _exclusive_director_source(self):
        if self.productionProfile and self.directorPack:
            raise ValueError("productionProfile and directorPack are mutually exclusive")
        return self
```

- [x] **Step 3: 统一成 Orchestrator 可消费的 Effective Policy**

为现有 ProductionProfile 增加适配器 `resolved_policy_from_profile()`；无 Pack 时行为必须与 V3 相同。`run_factory_visuals()` 参数从具体 `ProductionProfile` 改为统一 `EffectiveVisualPolicy`，只读取：routing、fallback、candidateCount、style、continuity、motion、duration、approval。它仍然调用 `visuals.create_batch()`、`run_local_batch()` 和 `approve_candidates()`。

- [x] **Step 4: 按 Scene intent 执行 Pack route**

每个 Scene 使用现有 Router 的规则证据得到 intent，再取 `effectiveRouting[intent]`。首选 Provider 失败时只走 Manifest 声明的下一项；fallback 写入 approval audit 并在策略要求时暂停 REVIEW。禁止 Resolver 或 Orchestrator 猜测未声明 Provider。

- [x] **Step 5: 持久化并恢复同一快照**

batch 和 item 均保存 `directorPack` identity 与完整 `resolvedDirectorPolicy`。恢复批次时直接读取快照，不重新 Resolve 新版本；只有新的 Run 才能选择新 Pack 版本。incremental scene edit 继续使用该 Run 已固定的快照。

- [x] **Step 6: 运行回归和新主链测试并提交**

Run:

```bash
cd backend
pytest tests/test_director_pack_factory_e2e.py tests/test_autonomous_video_factory_v3.py tests/test_multi_provider_visual_production.py -q
```

Expected: PASS；ProductionProfile V3 行为不退化。

```bash
git add backend/models/template_batch.py backend/services/template_batch_service.py backend/services/agent_factory_service.py backend/services/factory_visual_orchestrator.py backend/tests/test_director_pack_factory_e2e.py backend/tests/test_autonomous_video_factory_v3.py
git commit -m "feat: run director packs through factory lifecycle"
```

### Task 7: 暴露 HTTP、CLI、MCP 的同一协议能力

**Files:**
- Create: `backend/routers/director_packs.py`
- Create: `backend/tests/test_director_pack_api.py`
- Modify: `backend/main.py`
- Modify: `vforge/client.py`
- Modify: `vforge/cli.py`
- Modify: `vforge/mcp_server.py`
- Modify: `vforge/skill/SKILL.md`

- [x] **Step 1: 写 API 失败测试**

```python
def test_import_list_resolve_export_and_derive(client, pack_file):
    imported = client.post("/api/director-packs/import", files={"file": ("pack.vfdirector", pack_file, "application/zip")})
    assert imported.status_code == 200
    listed = client.get("/api/director-packs").json()
    assert listed[0]["id"] == "kvxw/knowledge-cinematic"
    resolved = client.post("/api/director-packs/kvxw/knowledge-cinematic/1.0.0/resolve", json={"runMode": "auto"})
    assert resolved.status_code == 200
    assert resolved.json()["pack"]["manifestDigest"].startswith("sha256:")
```

- [x] **Step 2: 实现固定 API**

```text
GET    /api/director-packs
POST   /api/director-packs/import
GET    /api/director-packs/{publisher}/{slug}/{version}
POST   /api/director-packs/{publisher}/{slug}/{version}/resolve
GET    /api/director-packs/{publisher}/{slug}/{version}/export
POST   /api/director-packs/{publisher}/{slug}/{version}/derive
POST   /api/director-packs/{publisher}/{slug}/{version}/enable
POST   /api/director-packs/{publisher}/{slug}/{version}/disable
DELETE /api/director-packs/{publisher}/{slug}/{version}
```

上传使用临时目录、50 MB request cap 和 archive 校验。错误 body 延续 `{code, message}`，不泄露本地绝对路径。

- [x] **Step 3: 增加 CLI 命令**

```text
vforge director-pack-list
vforge director-pack-import --file pack.vfdirector
vforge director-pack-show --id kvxw/knowledge-cinematic --version 1.0.0
vforge director-pack-resolve --id ... --version ... --mode auto
vforge director-pack-export --id ... --version ... --output pack.vfdirector
vforge director-pack-derive --id ... --version ... --data @derive.json
```

CLI 保持 stdlib-only，只通过 HTTP client 操作后端，不在 Agent 进程本地解析 archive。

- [x] **Step 4: 增加 MCP tools**

工具名称固定为：`list_director_packs`、`import_director_pack`、`get_director_pack`、`resolve_director_pack`、`export_director_pack`、`derive_director_pack`。返回 Resolved Policy，但绝不返回 credential value；Provider 只暴露 `ready/trust/version/templateIds`。

- [x] **Step 5: 运行 API 与 Agent 测试并提交**

Run: `cd backend && pytest tests/test_director_pack_api.py -q`

Expected: PASS。

```bash
git add backend/routers/director_packs.py backend/tests/test_director_pack_api.py backend/main.py vforge/client.py vforge/cli.py vforge/mcp_server.py vforge/skill/SKILL.md
git commit -m "feat: expose director packs to agents"
```

### Task 8: 建立用户可理解的 Director Pack 产品入口

**Files:**
- Create: `frontend/src/types/directorPack.ts`
- Create: `frontend/src/components/factory/DirectorPackPicker.tsx`
- Create: `frontend/src/pages/DirectorPacks.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/Home.tsx`
- Modify: `frontend/src/pages/FactoryQuickStart.tsx`

- [x] **Step 1: 定义前端 DTO，禁止页面继续使用 `any` 表达核心协议**

```ts
export type PackStatus = 'enabled' | 'enabled_with_degradation' | 'disabled' | 'blocked'

export interface DirectorPackSummary {
  id: string
  version: string
  name: string
  description: string
  sourceTrust: 'LOCAL' | 'UNVERIFIED' | 'TRUSTED_BUILTIN'
  status: PackStatus
  degradations: string[]
  referenceCount: number
}

export type DirectorSource =
  | { kind: 'profile'; id: string }
  | { kind: 'director_pack'; id: string; version: string }
```

- [x] **Step 2: 实现互斥选择器**

Quick Start 显示一个“导演方式”区域：内置快捷预设与已安装 Director Pack 是同一单选组，不出现两个相互覆盖的 select。未安装 Pack 时现有 ProductionProfile 路径保持可用。Pack 卡片显示版本、信任来源、参考模板数量、依赖状态和降级提示。

选中 Pack 后请求只发送：

```ts
{
  productionMode: mode,
  productionProfile: null,
  directorPack: { id: selected.id, version: selected.version }
}
```

- [x] **Step 3: 实现 Director Packs 管理页**

页面提供：导入、本地列表、版本详情、参考模板缩略图、结构化 style/preset、Provider/Skill 依赖、Resolved Policy 预览、导出、有限字段派生、禁用和卸载。卸载弹窗明确说明“不会删除已有 Project/素材/绑定/输出，但旧 Run 无法重新导演”。

遵守项目 UI 规则：未选中项使用 `bg-surface + text-primary`，选中项使用 gold；不使用白字灰底全组反转、不使用 neon glow、不引入渐变文字和 Inter。

- [x] **Step 4: 构建并提交**

Run: `cd frontend && npm run build`

Expected: Vite build PASS，无 TypeScript 错误。

```bash
git add frontend/src
git commit -m "feat: add director pack product entry"
```

### Task 9: 浏览器验收、文档和完成证据

**Files:**
- Create: `browser_director_pack_e2e.py`
- Create: `docs/DIRECTOR_PACK_PROTOCOL_V1.md`
- Modify: `docs/START_HERE_FOR_AI.md`
- Modify: `docs/AUTONOMOUS_VIDEO_FACTORY_V3.md`
- Modify: `docs/DIRECTOR_PACK_VISION.md`

- [x] **Step 1: 写真实浏览器路径**

Playwright 脚本必须完成：

```text
打开 Director Packs
→ 导入 .vfdirector
→ 查看参考模板、preset、依赖和 Resolved Policy
→ 回到 Factory Quick Start
→ 选择 Knowledge Cinematic（与 ProductionProfile 互斥）
→ 输入至少包含 causal/process/relationship 的中文文案
→ AUTO 生成
→ 证明 Code Visual + Stickman 都产生真实 candidate
→ Scene binding coverage 完成
→ Preview + JianYing 成功
→ 新建 REVIEW run
→ 选择任意 candidate 并批准继续
→ 导出 Pack
→ 修改 editable 字段并派生为新 ID
```

脚本记录 console error、page error、未处理 5xx、重复提交和 loading 状态；保存 trace 与关键截图。

- [x] **Step 2: 加入降级和恢复场景**

在隔离 `VIDEOFORGE_DATA_DIR` 中模拟缺少 optional Provider，验证 Pack 显示 `enabled_with_degradation`、只走声明 route、强制 REVIEW；模拟 Run 开始后安装新版本，验证 resume 仍使用旧 snapshot。

- [x] **Step 3: 跑完整验证**

Run:

```bash
cd backend && pytest -q
cd ../frontend && npm run build
cd .. && python browser_director_pack_e2e.py
```

Expected:

- Backend 全量测试 PASS。
- Frontend build PASS。
- Browser AUTO/REVIEW/derive/export PASS。
- `consoleErrors == []`、`pageErrors == []`、本轮新增未处理 5xx 为 0。
- Preview 经 `ffprobe` 验证包含视频流；JianYing 至少 `JY_STRUCTURE_VERIFIED`。若未真实打开剪映 GUI，必须标记 `JY_GUI_NOT_VERIFIED`。

- [x] **Step 4: 更新事实文档**

`docs/START_HERE_FOR_AI.md` 必须区分：

- `IMPLEMENTED`：Manifest、archive 安全、install/resolve/run/audit/export/derive、内置 Pack、HTTP/CLI/MCP。
- `VERIFIED`：实际跑过的 backend/build/browser/Preview/JianYing 证据。
- `DESIGNED`：Scene segmentation proposal。
- `FUTURE`：签名、Marketplace、付费、AI Image/Video Provider、Pi runtime 深度集成。

- [x] **Step 5: 最终提交**

```bash
git add browser_director_pack_e2e.py docs
git commit -m "docs: verify director pack protocol v1"
```

## 5. 验收矩阵

| 能力 | 必须证据 |
|---|---|
| Data-only | 危险后缀、SVG script、ZIP slip、symlink 测试均拒绝 |
| Manifest 规范真相 | 未知字段失败；无 Skill 仍能 Resolve 和 AUTO |
| 参考模板 | UI 可查看；archive digest 覆盖；AUTO 不把参考图当输出 |
| Provider template 引用 | registry 校验 template ID；不存在时 Pack blocked/degraded |
| Immutable | 相同 ID/version 不同 digest 安装失败 |
| Run pinning | resume 与 incremental rerun 使用相同 Resolved Policy digest |
| 混合 Provider | 一条视频真实产生 Code Visual 与 Stickman candidates |
| AUTO | 可信本地、无 warning 时自动 approve/bind |
| REVIEW | 用户 REVIEW 永不被 Pack 降为 AUTO；fallback/override/warning 强制暂停 |
| 降级 | 只走 Manifest 白名单，不猜 Provider；降级写 audit |
| Canonical timing | Director Pack 和 Provider 均不修改 Scene start/end |
| Agent parity | HTTP、CLI、MCP 返回同一 Resolved Policy digest |
| 输出 | Preview 成功、ffprobe 合法、JianYing 结构通过 |
| 卸载安全 | 已有 Project、资产、binding 和输出仍可读 |

## 6. 完成定义与 Git 策略

完成状态必须按证据精确报告：

```text
EDITED
LOCALLY_VERIFIED
COMMITTED
PUSHED
PR_UPDATED / PR_CREATED
CI_PASSED
BROWSER_E2E_VERIFIED
```

实现分支应从 PR #34 head 创建独立 Draft PR，不向 PR #34 塞入 Director Pack 代码，不 merge main，不整枝合并 `codex/director-pack-studio-clean`。实验分支只允许按文件/概念提取经过验证的安全机制。

计划完成后最终交付应包含：分支与 head SHA、PR、全量测试数量、前端 build、浏览器截图/trace、Preview ffprobe、JianYing 验证级别、Pack/Policy digest 示例、未实现边界和下一阶段建议。
