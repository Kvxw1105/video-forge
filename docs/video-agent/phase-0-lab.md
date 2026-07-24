# Video Agent Lab Phase 0

Phase 0 validates how a Video Director Agent should operate before VideoForge adds a persistent Agent Control Plane or a Pi Runtime Adapter.

The goal is to make the agent workflow reviewable as contracts, recipes, policies, high-level tools, eval cases, and run-log shape. VideoForge remains the execution engine and source of truth.

## Scope

Included:

- Video semantic contracts for project, timed content, scene, asset, preview, draft, batch, and run-log facts.
- A constrained Video Director system prompt.
- Three MVP recipes: structured knowledge talking video, existing assets recut, and book summary short video.
- Default, paid-operation, and destructive-operation policies.
- A fixed 20-case eval fixture set.
- High-level MCP/client tools that wrap existing VideoForge APIs.
- Static checks that keep recipes, tools, policies, and eval cases aligned.

Excluded:

- A new Agent Runtime.
- Pi sidecar integration.
- Persistent Agent Run Store.
- Frontend Director Desk UI.
- ASR talking-head recut, picture-in-picture, multitrack editing, and transition effects.
- Direct paid provider calls without explicit user approval.

## Fact Boundary

VideoForge owns durable production facts:

- Project
- Structured Episode
- Block
- Subtitle
- Alignment
- Scene
- Asset
- Timeline
- Preview
- JianYing draft
- Batch manifest

The agent owns only planning and operational artifacts:

- Recipe choice
- Prompt or script analysis
- Scene-plan report
- Policy decision
- Approval request
- Tool execution log
- Eval result
- Run log

The agent must reference VideoForge facts by ids such as projectId, batchId, itemId, sceneId, and assetId. It must not duplicate full project state as a second source of truth.

## Timing And Scene Rules

- Subtitle text and timing are read-only for the agent.
- Scene start/end timing comes from subtitles or alignment.
- The agent must not write free start or end values.
- Scene groups must stay inside one Block.
- If alignment, subtitle, or visual-plan generation ids change, dependent artifacts become stale.

## High-Level Tool Surface

Phase 0 exposes these Video Director tools through vforge.client and MCP:

| Tool | Purpose |
| --- | --- |
| inspect_video_project | Read a project summary plus structured, subtitle, audio, asset, visual context, and visual-plan status. |
| inspect_video_readiness | Documented capability name for readiness inspection. |
| validate_video_readiness | Current wrapper that returns a project readiness checklist. |
| prepare_structured_script | Parse source text or read a structured project draft as a proposal. |
| create_video_factory_job | Start factory production through existing batch APIs. |
| review_visual_scene_plan | Read, propose, draft, or persist visual scene plans through existing validation APIs. |
| prepare_visual_generation_pack | Export a visual generation pack from the visual-plan API. |
| inspect_pending_visuals | Inspect batch scenes/items waiting for visual assets. |
| bind_scene_assets | Import/bind visual assets through existing factory APIs. |
| validate_video_assets | Validate visual coverage for one factory item. |
| build_video_preview | Render a preview through the existing preview API. |
| audit_video_preview | Run a lightweight local preview readiness audit. |
| export_editable_draft | Export a new editable JianYing draft. |
| recover_video_job | Resume a failed batch or item without rerunning succeeded work. |
| get_video_job_status | Read current job/batch state for continuation and recovery. |

These tools are thin wrappers. They do not introduce a new project store and do not write project files directly.

## Eval Dataset

The fixed Phase 0 eval set contains 20 synthetic cases:

- 5 structured knowledge talking videos
- 5 book summary short videos
- 3 missing-asset cases
- 3 incorrect asset-binding cases
- 2 preview recovery cases
- 2 editable-draft recovery cases

Each case records expected recipe selection, final state, constraints, and metric fields for later runtime comparisons.

## Verification

Run the full Phase 0 static verification:

    python agent\evals\runner\verify_phase0.py

The verifier runs:

- eval case linter
- Agent Lab manifest/recipe/policy linter
- Python compile checks for changed Python entry points

Run focused MCP and Lab tests:

    $env:PYTHONPATH=(Get-Location).Path
    pytest -q tests\test_agent_factory_mcp.py tests\test_vforge_batch_mcp.py tests\test_video_director_tools_mcp.py tests\test_video_agent_lab_assets.py

## Completion Gate

Do not move to Agent Control Plane until all Phase 0 gates are true:

- Three recipes run through.
- At least three real videos complete end to end.
- High-level tools do not directly edit project files.
- Agent does not modify subtitle timing.
- Agent does not create cross-Block scenes.
- Paid calls require approval.
- Failed projects can recover.
- Repeat runs do not duplicate production.
- Eval runner outputs structured results.
- Users can understand why the agent paused.

## Next Phase Trigger

If fixed recipes are enough after real video runs, keep improving VideoForge tools and recipes before adding a complex runtime.

If Phase 0 shows that long context, multi-turn reasoning, and durable task control are required, proceed to Agent Control Plane, then Runtime Adapter.
