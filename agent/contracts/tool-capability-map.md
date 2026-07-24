# Tool Capability Map

High-level Video Director tools wrap existing VideoForge APIs. They are intentionally fewer and more domain-specific than the atomic backend operations.

## Capability Rules

- Tools return structured JSON only.
- Tools never edit project files directly.
- Tools that write must use VideoForge HTTP APIs and carry an idempotency key when the backend supports it.
- Tools must surface stale, missing, and policy-blocked states as explicit error codes.
- Paid and destructive tools must not execute until policy approval has been recorded.

## Tool Map

| Tool | Default Policy | Writes | Existing Backend/API Surface | Primary Output | Notes |
| --- | --- | --- | --- | --- | --- |
| inspect_video_project | auto | no | project API, visual plan context | Project summary, subtitle/alignment/scene/asset status | Use before planning or recovery. |
| inspect_video_readiness | auto | no | project, visual plan validation, batch status | Readiness checklist | Alias exposed as validate_video_readiness in the first wrapper set. |
| prepare_structured_script | auto or approval for original text changes | draft only | structured content APIs and profiles | Structured Episode proposal | Must not overwrite source text without user confirmation. |
| create_video_factory_job | confirmation when paid TTS/LLM is selected | yes | template batch production APIs | Batch id and manifest refs | Does not call Fish unless explicitly selected and approved. |
| review_visual_scene_plan | auto | draft or API write after validation | visual plan context/propose/set/validate | Scene plan report | Scene timing comes from narration units. |
| prepare_visual_generation_pack | auto, cost approval if provider is invoked | yes | visual plan generation pack API | Prompt pack and missing asset list | Pack generation is local; provider calls are separate. |
| inspect_pending_visuals | auto | no | agent factory pending visuals API | Missing scene assets | Used to pause when visual coverage is incomplete. |
| bind_scene_assets | confirmation for replace/overwrite | yes | agent factory visual import/bind APIs | Binding result | Must bind by sceneId. |
| validate_video_assets | auto | no | agent factory validate visuals API | Coverage and playability report | Blocks preview when required assets are missing. |
| build_video_preview | auto | yes | project preview render API | Preview artifact ref | Must reuse existing fresh preview when possible. |
| audit_video_preview | auto | no | preview metadata plus QA hooks | QA report | Later Phase 4 expands semantic QA. |
| export_editable_draft | auto create_new | yes | JianYing export API | Draft artifact ref | Never overwrites a user draft. |
| recover_video_job | auto for safe retry, approval for destructive repair | yes | batch/item resume APIs | Recovery result | Must not rerun succeeded steps. |
| get_video_job_status | auto | no | batch manifest/status APIs | Batch/item status | Source of truth remains VideoForge. |

## Phase 0 Wrapper Set

Phase 0 exposes these wrappers immediately:

- inspect_video_project
- inspect_video_readiness
- prepare_structured_script
- create_video_factory_job
- review_visual_scene_plan
- prepare_visual_generation_pack
- inspect_pending_visuals
- bind_scene_assets
- validate_video_assets
- validate_video_readiness
- build_video_preview
- audit_video_preview
- export_editable_draft
- recover_video_job
- get_video_job_status

The wrappers stay thin: they delegate to existing VideoForge HTTP APIs and do not introduce a second project store.
