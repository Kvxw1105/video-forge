# Agent Video Factory

The Factory is a durable two-stage wrapper around Template Batch production.
It is intended for structured Markdown only when `visualWorkflow.mode` is
`generation_pack`.

`plain_script` combined with `generation_pack` is rejected with
`generation_pack_requires_structured_input`: visual planning needs the
timestamp-aligned structured subtitles that plain scripts do not provide.

## Flow

1. Submit a normal Template Batch with `inputMode=structured_markdown` and an
   enabled `visualWorkflow`.
2. The batch creates the project, materializes Fish timestamp alignment,
   subtitles, block bindings, a Visual Plan, and a Generation Pack.
3. The item pauses as `awaiting_visual_assets`. No preview or JianYing draft is
   generated in this phase.
4. Read `GET /api/agent-factory/batches/{batchId}/pending-visuals`, generate
   the requested scene media, and import it with the item visual import route.
5. Validate coverage, then resume the item or batch. Resume compiles the active
   structured Variant before calling preview and JianYing production outputs.

`ready_to_resume` means every requested Scene is bound. `pending-visuals`
lists only items still awaiting assets. Generation Pack files are named
`scene_001.png`, `scene_002.png`, and so on; image or video extensions are
accepted at import time.

## Safety And Recovery

- Scene imports are project-local. Re-importing identical media is idempotent.
- A same-scene file with different bytes returns `asset_conflict` unless the
  caller explicitly requests replacement.
- A Visual Plan whose subtitles, bindings, or alignment changed returns
  `visual_plan_stale`; it must be proposed and saved again before resume.
- `visual_coverage_incomplete` is returned before output work begins.
- `item_not_ready_to_resume`, `item_not_found`, `batch_not_found`, and
  `asset_conflict` are actionable API errors; callers should not retry them
  blindly.
- Output reuse requires both an equal `inputHash` and an existing output path.
  A missing preview rebuilds only the preview; a missing JianYing draft rebuilds
  only the draft.
- Factory JianYing output always uses `create_new`; it never replaces a user
  draft.

## API Controls

`GET /api/agent-factory/batches/{batchId}/pending-visuals`

`POST /api/agent-factory/batches/{batchId}/items/{itemId}/visuals/import`

`POST /api/agent-factory/batches/{batchId}/items/{itemId}/visuals/validate`

`POST /api/agent-factory/batches/{batchId}/items/{itemId}/resume`

`POST /api/agent-factory/batches/{batchId}/resume`

`POST /api/agent-factory/batches/{batchId}/continue`

The same operations are available through `vforge` client helpers, CLI
subcommands, and MCP tools. These controls do not make paid TTS calls; Fish is
only reached by the first structured-audio materialization step when the batch
is originally executed.

See `examples/agent-factory/two-item-generation.json` and
`examples/agent-factory/generated-assets-layout.md` for a credential-free
two-item request and its expected generated-media layout.
