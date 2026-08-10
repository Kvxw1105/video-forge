# AI Image Scene Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dual-channel AI image pipeline that binds generated still images to narration-timed VisualPlan Scenes through either a built-in OpenAI-compatible provider or a Codex/Agent upload protocol.

**Architecture:** Extend the current Agent Video Factory instead of creating a second timeline. A strict project-scoped batch service validates `visualPlanId`, `visualSourceHash`, and per-Scene `inputHash`; provider and Agent results become candidates, explicit approval creates project assets and binds them to Scenes, and the existing structured compiler drives preview and JianYing output.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, httpx, React 18, TypeScript, Vite, pytest, argparse CLI, FastMCP.

---

## File map

- Create `backend/models/image_generation.py`: strict provider, batch, item, candidate, and request contracts.
- Create `backend/services/image_generation_service.py`: durable state, provider execution, Agent upload, approval, stale validation, retry.
- Create `backend/routers/image_generation.py`: settings and project-scoped endpoints.
- Create `backend/tests/test_image_generation_service.py`: service lifecycle, stale and idempotency tests.
- Create `backend/tests/test_image_generation_api.py`: HTTP security and Agent upload tests.
- Modify `backend/main.py`: register both image-generation routers.
- Modify `frontend/src/lib/api.ts`: typed-enough request wrappers.
- Create `frontend/src/components/factory/AIImageGenerationPanel.tsx`: built-in and Agent channel UI.
- Modify `frontend/src/pages/FactoryVisualPairing.tsx`: mount the panel in the existing visual workflow.
- Modify `vforge/client.py`: image batch operations and multipart upload.
- Modify `vforge/cli.py`: pending/export/upload/status commands.
- Modify `vforge/mcp_server.py`: Agent-facing image generation tools.
- Modify `vforge/skill/SKILL.md`: Codex image-tool workflow.
- Create `docs/AI_IMAGE_SCENE_PIPELINE.md`: user/API workflow and credential boundary.
- Create `.agent/ai-image-scene-pipeline-continuation-prompt.md`: durable Agent handoff Prompt.

### Task 1: Strict contracts and durable service skeleton

**Files:**
- Create: `backend/models/image_generation.py`
- Create: `backend/services/image_generation_service.py`
- Test: `backend/tests/test_image_generation_service.py`

- [ ] **Step 1: Write failing lifecycle tests**

Add tests that build a structured project with two subtitle-timed Scenes, call `create_batch(..., channel="agent")`, and assert:

```python
assert batch["status"] == "awaiting_agent"
assert [item["sceneId"] for item in batch["items"]] == ["scene_1", "scene_2"]
assert batch["items"][0]["start"] == 0
assert batch["items"][0]["end"] == 1.5
assert len(batch["items"][0]["inputHash"]) == 64
```

Also assert the batch survives a fresh `get_batch()` read from disk.

- [ ] **Step 2: Run the new test and verify RED**

Run: `python -m pytest backend/tests/test_image_generation_service.py -q -p no:cacheprovider`

Expected: collection failure because `services.image_generation_service` does not exist.

- [ ] **Step 3: Implement contracts**

Define Pydantic models with `ConfigDict(extra="forbid")`, including:

```python
ImageGenerationChannel = Literal["builtin", "agent"]
ImageGenerationItemStatus = Literal["pending", "generating", "generated", "approved", "bound", "failed"]
ImageGenerationBatchStatus = Literal[
    "pending", "running", "awaiting_agent", "awaiting_approval",
    "succeeded", "partial", "failed", "stale",
]
```

`ImageGenerationItem` must contain `sceneId`, `blockId`, `subtitleIds`, `start`, `end`, `duration`, `text`, Prompt fields, aspect ratio, input hash, expected filename, status, errors, and candidates.

- [ ] **Step 4: Implement deterministic batch creation and persistence**

Use `_project_dir(project_id) / "image-generation" / "batches" / f"{batch_id}.json"`. Build Scene timing through the current visual planning context and subtitle records. Hash canonical JSON with SHA-256. Use a temporary file plus `os.replace` for every write.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `python -m pytest backend/tests/test_image_generation_service.py -q -p no:cacheprovider`

Expected: lifecycle tests pass.

- [ ] **Step 6: Commit only Task 1 files**

```powershell
git add -- backend/models/image_generation.py backend/services/image_generation_service.py backend/tests/test_image_generation_service.py
git commit -m "feat: add durable scene image generation batches"
```

### Task 2: Agent upload, stale protection, approval, and retry

**Files:**
- Modify: `backend/services/image_generation_service.py`
- Modify: `backend/tests/test_image_generation_service.py`

- [ ] **Step 1: Add failing Agent and stale tests**

Cover:

```python
candidate = upload_agent_candidate(project_id, batch_id, "scene_1", input_hash, png_path)
duplicate = upload_agent_candidate(project_id, batch_id, "scene_1", input_hash, png_path)
assert duplicate["candidateId"] == candidate["candidateId"]

with pytest.raises(ImageGenerationError, match="stale"):
    upload_agent_candidate(project_id, batch_id, "scene_1", "0" * 64, png_path)
```

Approve the candidate and assert asset provenance plus `primaryAssetId`. Change the project VisualPlan source hash and assert later approval fails without mutating assets. Add a retry test in which one item succeeds and one failed item alone returns to `pending`.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest backend/tests/test_image_generation_service.py -q -p no:cacheprovider`

Expected: missing upload, approval, and retry functions.

- [ ] **Step 3: Implement safe upload and approval**

Validate batch/project/plan hashes before every mutation. Accept `.png`, `.jpg`, `.jpeg`, and `.webp`; reject empty or files over the configured maximum. Copy into the batch candidate directory using a content hash filename. Approval copies the selected candidate to `assets/`, appends provenance metadata, updates `visualAssetIds` and `primaryAssetId`, then calls `update_project` once.

- [ ] **Step 4: Implement retry**

`retry_failed_items()` changes only failed items back to pending and preserves candidates and completed items. Recompute aggregate batch status after each state change.

- [ ] **Step 5: Verify GREEN and commit**

Run: `python -m pytest backend/tests/test_image_generation_service.py -q -p no:cacheprovider`

```powershell
git add -- backend/services/image_generation_service.py backend/tests/test_image_generation_service.py
git commit -m "feat: bind Agent generated images to timed scenes"
```

### Task 3: Built-in OpenAI-compatible provider and secret-safe settings

**Files:**
- Modify: `backend/models/image_generation.py`
- Modify: `backend/services/image_generation_service.py`
- Create: `backend/routers/image_generation.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_image_generation_api.py`

- [ ] **Step 1: Add failing HTTP and provider tests**

Test that settings PUT preserves an existing key when the new key is blank and GET returns `apiKey: ""` plus `apiKeyConfigured: true`. Mock `/images/generations` returning base64 PNG data, run a built-in batch, and assert candidates are created. Test partial failure and retry. Assert URL responses reject non-image content and over-limit payloads.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest backend/tests/test_image_generation_api.py -q -p no:cacheprovider`

Expected: router import or endpoint failure.

- [ ] **Step 3: Implement settings and provider calls**

Store configuration in `CONFIG_DIR / "ai_image_provider.json"`. Redact secrets from public output. Call `${baseUrl}/images/generations` with explicit timeout and one request per Scene; support `b64_json` and `url`. Bound concurrency with `ThreadPoolExecutor(max_workers=settings.maxConcurrency)` and update durable item status after each result.

- [ ] **Step 4: Implement endpoints**

Register:

```text
GET/PUT  /api/settings/ai-image
POST     /api/settings/ai-image/test
POST     /api/projects/{project_id}/image-generation/batches
GET      /api/projects/{project_id}/image-generation/batches/{batch_id}
GET      /api/projects/{project_id}/image-generation/batches/{batch_id}/pending
POST     /api/projects/{project_id}/image-generation/batches/{batch_id}/run
POST     /api/projects/{project_id}/image-generation/batches/{batch_id}/upload
POST     /api/projects/{project_id}/image-generation/batches/{batch_id}/approve
POST     /api/projects/{project_id}/image-generation/batches/{batch_id}/retry
```

Translate domain errors into stable HTTP codes and error details.

- [ ] **Step 5: Verify tests and commit**

Run: `python -m pytest backend/tests/test_image_generation_service.py backend/tests/test_image_generation_api.py backend/tests/test_settings_security.py -q -p no:cacheprovider`

```powershell
git add -- backend/models/image_generation.py backend/services/image_generation_service.py backend/routers/image_generation.py backend/main.py backend/tests/test_image_generation_api.py
git commit -m "feat: add built-in AI image provider API"
```

### Task 4: CLI, MCP, and Skill Agent channel

**Files:**
- Modify: `vforge/client.py`
- Modify: `vforge/cli.py`
- Modify: `vforge/mcp_server.py`
- Modify: `vforge/skill/SKILL.md`
- Create: `tests/test_vforge_image_generation_cli.py`
- Create: `tests/test_vforge_image_generation_mcp.py`

- [ ] **Step 1: Write failing wrapper tests**

Assert CLI and MCP call the HTTP client rather than editing project files. Required operations:

```text
image-batch-create
image-batch-status
image-batch-pending
image-batch-upload
image-batch-approve
image-batch-retry
```

The upload command requires `--pid`, `--batch`, `--scene`, `--input-hash`, and `--file`.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_vforge_image_generation_cli.py tests/test_vforge_image_generation_mcp.py -q -p no:cacheprovider`

- [ ] **Step 3: Implement client and wrappers**

Add JSON methods and a multipart uploader to `VideoForgeClient`. MCP tool descriptions must explicitly instruct an Agent to generate exactly one image for each request and return it with the unchanged input hash.

- [ ] **Step 4: Document the Codex flow in the Skill**

Document this deterministic loop:

```text
create or fetch Agent batch
→ read pending Scene request
→ call the Agent's image tool with finalPrompt
→ save output locally
→ upload with sceneId + inputHash
→ inspect status
→ approve candidates
→ resume Factory output
```

- [ ] **Step 5: Verify and commit without staging unrelated existing edits**

Run: `python -m pytest tests/test_vforge_image_generation_cli.py tests/test_vforge_image_generation_mcp.py -q -p no:cacheprovider`

Before committing, inspect `git diff` in `vforge/cli.py` and `vforge/mcp_server.py`; those files already contain user TTS edits. Stage only AI-image hunks with `git add -p`, then verify the cached diff.

```powershell
git commit -m "feat: expose scene image generation to Agents"
```

### Task 5: Factory UI integration

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/components/factory/AIImageGenerationPanel.tsx`
- Modify: `frontend/src/pages/FactoryVisualPairing.tsx`

- [ ] **Step 1: Add API wrappers and the bounded panel**

The panel receives `projectId`, `visualPlanId`, `scenes`, and an `onBound` callback. It supports:

- `builtin` and `agent` channel selection;
- project-wide style and continuity anchors;
- per-Scene enable, Prompt, and negative Prompt editing;
- provider settings and explicit paid-call confirmation;
- batch creation, progress refresh, candidates, approval, retry;
- Agent JSON task download and manual refresh;
- existing manual upload fallback remains visible in the parent page.

- [ ] **Step 2: Mount it in FactoryVisualPairing**

Place the panel below the Scene timing/Prompt area and above the resume action. Refresh Factory coverage after approval so the existing `complete` gate becomes authoritative.

- [ ] **Step 3: Check design invariants**

Use `bg-surface + text-primary` for unselected controls, gold only for selected/primary actions, `bg-elevated` only for depth, no glow shadows or gradient text, and no attribute-selector CSS changes.

- [ ] **Step 4: Build and commit**

Run: `npm run build` from `frontend/`.

Because `frontend/src/lib/api.ts` already contains user TTS edits, stage only AI-image hunks and verify the cached diff.

```powershell
git add -- frontend/src/components/factory/AIImageGenerationPanel.tsx frontend/src/pages/FactoryVisualPairing.tsx
git add -p -- frontend/src/lib/api.ts
git commit -m "feat: add AI image generation to visual pairing"
```

### Task 6: Timeline/export regression and no-paid-call smoke flow

**Files:**
- Modify: `backend/tests/test_structured_media.py`
- Create: `backend/tests/test_ai_image_scene_e2e.py`

- [ ] **Step 1: Add end-to-end test**

Create a structured project with timed subtitles, propose a VisualPlan, create an Agent batch, upload two fixture PNGs, approve both, compile the active variant, and assert each generated asset occupies its Scene's exact target window. Exercise the preview/JianYing adapter boundary with mocks where external binaries are unavailable.

- [ ] **Step 2: Verify RED then GREEN**

Run before final fixes, confirm the new assertion fails for the expected missing behavior, implement the minimal correction, then run:

`python -m pytest backend/tests/test_ai_image_scene_e2e.py backend/tests/test_structured_media.py backend/tests/test_timeline_adapter_parity.py -q -p no:cacheprovider`

- [ ] **Step 3: Run a local Agent-awaiting smoke request**

Use FastAPI TestClient with a temporary project directory. Create the project, VisualPlan, and Agent batch; assert the pending response contains exact timings and no network call occurs.

- [ ] **Step 4: Commit**

```powershell
git add -- backend/tests/test_ai_image_scene_e2e.py backend/tests/test_structured_media.py
git commit -m "test: verify AI images follow narration timing"
```

### Task 7: Product docs and continuation Prompt

**Files:**
- Create: `docs/AI_IMAGE_SCENE_PIPELINE.md`
- Create: `.agent/ai-image-scene-pipeline-continuation-prompt.md`
- Modify: `README.md`

- [ ] **Step 1: Write user and Agent instructions**

Document the built-in provider, Codex/Agent channel, security boundary, exact CLI/MCP sequence, Factory UI flow, supported image types, stale behavior, and the fact that no paid API validation is claimed unless actually performed.

- [ ] **Step 2: Write the continuation Prompt**

Include repository URL, local path, feature branch, the actual commit returned by `git rev-parse HEAD` at the time the Prompt is finalized, product objective, invariants, changed files, test commands, observed results, unverified paid-provider boundary, and instructions to inspect `git status`, remote state, and this plan before editing.

- [ ] **Step 3: Scan and commit**

Run: `rg -n "TBD|TODO|FIXME|sk-[A-Za-z0-9]|apiKey\s*[:=]\s*['\"]?[^'\" ]+" docs/AI_IMAGE_SCENE_PIPELINE.md .agent/ai-image-scene-pipeline-continuation-prompt.md README.md`

Expected: no placeholders or secrets.

```powershell
git add -- docs/AI_IMAGE_SCENE_PIPELINE.md .agent/ai-image-scene-pipeline-continuation-prompt.md README.md
git commit -m "docs: document AI image scene workflow"
```

### Task 8: Full verification, existing local changes, and GitHub delivery

**Files:**
- Verify all changed files
- Update: `.agent/ai-image-scene-pipeline-continuation-prompt.md` with observed evidence

- [ ] **Step 1: Run backend tests**

Run: `python -m pytest backend/tests tests vforge/tests -q -p no:cacheprovider`

Expected: zero failures; environment-dependent tests may skip only with an explicit reason.

- [ ] **Step 2: Run frontend build**

Run: `npm run build` from `frontend/`.

Expected: exit code 0. Existing chunk-size warnings are non-fatal but must be reported.

- [ ] **Step 3: Run repository safety checks**

```powershell
git diff --check
git status --short
git log --oneline -10
```

Inspect every remaining local modification. Run the TTS-focused tests for the pre-existing work and either commit those verified changes separately or leave them explicitly documented; do not imply GitHub synchronization while tracked work remains only local.

- [ ] **Step 4: Refresh handoff evidence and commit**

Record exact pass counts, build output, branch, and unresolved credential-dependent checks in the continuation Prompt. Commit that evidence update.

- [ ] **Step 5: Push feature branch**

Run: `git push -u origin codex/ai-image-scene-pipeline`

Verify: `git status --short --branch` shows the branch tracking its remote with no unpushed commits.

- [ ] **Step 6: Integrate main only after a clean audit**

If all pre-existing local changes have been safely committed and tests remain green, merge the feature branch into local `main`, rerun the decisive verification commands, and push `origin/main`. If that condition is not met, keep the verified feature branch pushed and state precisely why `main` was not changed.
