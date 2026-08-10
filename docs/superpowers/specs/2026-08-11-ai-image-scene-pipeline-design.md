# AI Image Scene Pipeline Design

## 1. Outcome

Video Forge turns a script or idea into a structured, voice-timed visual plan and lets either the local product or an external Agent generate most scene images. Every approved image is bound to the exact Scene whose duration comes from aligned narration and subtitles. The same project can then produce an FFmpeg preview and a JianYing draft without rebuilding timing in the image-generation layer.

This feature extends the existing Agent Video Factory. It does not introduce a second project model, timeline, or renderer.

## 2. Product position

Video Forge remains the primary user product. People can operate the AI image workflow from the Factory visual pairing screen. The same capability is also exposed as API, CLI, MCP, and Skill operations so Codex or another Agent can act as an image-generation provider.

The two generation channels are:

1. **Built-in provider:** Video Forge calls an OpenAI-compatible image API configured by the user.
2. **Agent provider:** Codex or another Agent fetches pending Scene requests, uses its own image tool or quota, and uploads the result to the matching Scene.

Video Forge does not attempt to access a Codex client's private image quota from its backend. Codex uses the Agent provider protocol instead.

## 3. Authoritative timing model

Narration and subtitles are the timing authority:

1. Structured Blocks define semantic content sections.
2. Timestamped TTS materializes subtitles and Block audio bindings.
3. `VisualPlan.scenes` groups continuous subtitle IDs inside a single Block.
4. Each Scene derives `start`, `end`, and `duration` from those subtitle IDs.
5. Generated images bind to the Scene; they never choose their own duration.
6. The structured variant compiler lowers Scene bindings into the canonical timeline.
7. FFmpeg preview and JianYing export consume that same compiled result.

This preserves the existing invariant that preview and JianYing share one canonical timeline.

## 4. Architecture

### 4.1 Existing components to retain

- `backend/shared/visual_scene.py` owns deterministic Scene planning and timing.
- `backend/models/project.py` owns `VisualPlan`, `VisualScene`, assets, subtitles, and structured content.
- `backend/services/agent_factory_service.py` owns the two-stage pause/bind/resume production flow.
- `backend/shared/structured_content.py` lowers bound visual assets into structured timeline segments.
- `frontend/src/pages/FactoryVisualPairing.tsx` is the user-facing visual coverage workbench.
- `vforge/client.py`, `vforge/cli.py`, and `vforge/mcp_server.py` expose Agent entry points.

### 4.2 New bounded components

- `backend/models/image_generation.py`: strict batch, item, candidate, provider, and upload contracts.
- `backend/services/image_generation_service.py`: durable batch storage, stale-input validation, built-in provider execution, candidate approval, and Agent upload binding.
- `backend/routers/image_generation.py`: settings and project-scoped image-generation endpoints.
- `frontend/src/components/factory/AIImageGenerationPanel.tsx`: provider settings, Scene selection, Prompt editing, generation progress, candidates, and approval.
- `vforge` client/CLI/MCP operations: list pending requests, upload a generated Scene image, and inspect batch state.
- `vforge/skill/SKILL.md`: Agent workflow for using its own image tool and returning artifacts.

The service is independent of Pi Director and Agent Lab. Those branches may remain future inputs, but this implementation selectively ports only the proven AI image batch behavior.

## 5. Data contracts

### 5.1 Image generation batch

An `ImageGenerationBatch` contains:

- `schemaVersion`
- `batchId`
- `projectId`
- `visualPlanId`
- `visualSourceHash`
- `channel`: `builtin` or `agent`
- `providerId`, `model`, `size`, and `candidateCount`
- `status`: `pending`, `running`, `awaiting_agent`, `awaiting_approval`, `succeeded`, `partial`, `failed`, or `stale`
- ordered `items`
- creation and update timestamps

Batch files live inside the project directory under `image-generation/batches/`. API keys remain in the application configuration directory and never enter a project or Git.

### 5.2 Scene generation item

Every item contains:

- `sceneId`, `blockId`, and `subtitleIds`
- exact `start`, `end`, and `duration`
- Scene narration text
- positive and negative Prompt
- aspect ratio and requested image size
- continuity/style metadata
- deterministic `inputHash`
- `expectedFilename`
- status, errors, and zero or more candidates

The item hash covers the VisualPlan source hash, Scene identity and timing, Prompt fields, aspect ratio, provider/model, and generation settings. A result with a mismatched hash cannot be approved or bound.

### 5.3 Generated asset provenance

An approved project asset records:

- `generatedBy: "ai_image"`
- generation channel and provider
- model
- batch ID and Scene ID
- input hash
- positive and negative Prompt
- original candidate identifier

The Scene receives the asset ID in `visualAssetIds` and `primaryAssetId`.

## 6. Prompt system

The generation request distinguishes editable Scene content from reusable direction:

- `sceneIntent`: the visual meaning of the current narration span.
- `subject`: people, objects, environment, and action that must appear.
- `composition`: shot size, camera angle, subject placement, and motion implication.
- `styleAnchor`: the shared cinematic style for the project.
- `continuityAnchor`: stable character, clothing, palette, location, and era traits.
- `safeArea`: aspect ratio and subtitle-safe composition guidance.
- `negativePrompt`: text, watermark, logo, malformed anatomy, conflicting style, and project-specific exclusions.

Video Forge stores and transports these fields, and builds a deterministic provider Prompt from them. An Agent may propose or edit the semantic fields. The local product does not pretend to infer high-quality creative intent without an AI model.

The UI always shows the final Prompt before a paid provider call. Users can edit individual Scenes and opt out of generation per Scene.

## 7. API and Agent operations

### 7.1 Built-in provider

- Read and update local provider settings.
- Test an OpenAI-compatible endpoint and list models when supported.
- Create a built-in generation batch from selected VisualPlan Scenes.
- Run the batch with bounded concurrency.
- Read progress and candidate metadata.
- Approve one candidate per Scene and bind approved assets.

Supported response inputs include base64 image data and image URLs. Remote URLs are downloaded with explicit timeout, size, and content-type limits before being stored locally.

### 7.2 Agent provider

- Create an `agent` channel batch.
- List pending Scene generation requests as structured JSON.
- Upload one generated image with `batchId`, `sceneId`, and `inputHash`.
- Reject missing, duplicate, stale, oversized, or unsupported images.
- Mark the uploaded artifact as a candidate.
- Approve explicitly or use an explicit auto-approve option supplied when creating the batch.

MCP and CLI wrap the same HTTP endpoints; they do not mutate project JSON directly.

## 8. User experience

The existing Factory visual pairing page remains the primary entry. It gains an AI image section with:

- generation channel selection: external API or Agent/Codex;
- selected Scene count and estimated provider call count;
- final Prompt and negative Prompt editing;
- project style and continuity anchors;
- provider model, size, candidate count, and concurrency settings;
- explicit confirmation before external paid calls;
- per-Scene progress and errors;
- candidate preview, replacement, and approval;
- Agent task export and refresh actions;
- the existing manual upload path as a fallback;
- resume output action enabled only when required Scene coverage is complete.

Unselected buttons follow the existing progressive-contrast design rules. No global CSS hacks, neon glow, gradient text, or new generic cinematic utility classes are introduced.

## 9. Error and recovery behavior

- Missing VisualPlan: direct the user to generate the timed visual plan first.
- Stale VisualPlan: mark the batch stale and require a new batch; never silently bind old images.
- Partial provider failure: preserve successful candidates and allow retry only for failed items.
- Interrupted process: durable batch state supports status reload and retry.
- Invalid upload: return a stable error code without modifying the project.
- Approval failure: perform project mutation transactionally; the batch remains recoverable.
- Duplicate Agent upload: idempotently return the existing candidate when the content hash matches.
- Provider secret exposure: redact API keys from all responses, logs, batches, and project metadata.
- Missing generated Scene: keep the Factory in `awaiting_visual_assets`; do not render a misleading completed result.

## 10. Verification and acceptance

Completion requires evidence for all of the following:

1. A structured script produces multiple Scenes whose timing matches bound subtitles.
2. Every requested Scene exposes a complete Prompt and exact time window.
3. A mocked OpenAI-compatible provider generates candidates, approval binds them, and provenance is saved.
4. Agent CLI and MCP can list pending requests and upload a generated Scene image.
5. Stale `visualSourceHash` or `inputHash` prevents an incorrect bind.
6. Partial generation can retry failed items without regenerating successful items.
7. Complete Scene coverage compiles into the canonical timeline with the expected image windows.
8. Preview and JianYing adapter regression tests cover the generated bindings.
9. Settings security tests prove provider secrets are not returned or committed.
10. Frontend production build and full relevant Python test suites pass.
11. A real local smoke workflow reaches an Agent-awaiting batch without paid calls.
12. The implementation, design, plan, tests, and continuation Prompt are committed and pushed to GitHub.

Real paid image generation is optional for automated verification because credentials and quota may be unavailable. When no paid call is made, the delivery report must state that boundary and rely on contract tests plus the Agent upload smoke workflow.

## 11. Delivery and handoff

Implementation occurs on a `codex/` feature branch, preserving the user's existing uncommitted TTS work. Commits are divided by contract/service, Agent interfaces, UI, documentation, and final integration. After verification, the feature branch is pushed to `origin`; integration into `main` occurs only after checking that the pre-existing local changes are safely accounted for.

The repository will contain a continuation Prompt with:

- repository URL and working directory;
- active branch and latest pushed commit;
- product objective and non-negotiable invariants;
- implemented files and API operations;
- verification commands and observed results;
- credential-dependent checks not performed;
- remaining work, if any;
- instruction to inspect current Git and filesystem state before continuing.

## 12. Scope boundaries

This phase does not add AI video generation, character-training pipelines, automatic BGM selection, multi-track/PIP, transitions, filters, stickers, or a new autonomous Director runtime. BGM remains supported by the existing project and JianYing workflow. The phase succeeds when AI-generated still images are semantically planned, precisely timed, reliably bound, and consumable by both preview and JianYing export.
