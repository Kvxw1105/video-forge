# Video Semantic Contract

This contract defines the facts a Video Director Agent may inspect, propose, or request through VideoForge APIs. VideoForge remains the authority for project state and execution state. The agent must not edit project files directly.

## Global Rules

- VideoForge owns durable project facts: project files, subtitles, alignments, scenes, assets, previews, and editable draft exports.
- Agent runs store references only: projectId, batchId, itemId, sceneId, assetId, artifact ids, and tool call ids.
- Timed content is derived from subtitles or alignment. The agent must not invent free start or end values.
- Scenes may group units only inside the same Block. Cross-Block scene grouping is invalid.
- Paid providers and destructive operations require explicit approval before execution.
- Re-running a step must reuse completed artifacts when the idempotency key and source generation ids still match.

## Object Contracts

### Episode

Authority: VideoForge structured content API.
Source: project structured episode or factory item script.
Agent write scope: draft proposal only.
Immutable fields: projectId, episodeId, sourceDocumentHash.
Stale when: source document hash changed; structure profile changed; user rejected latest proposal.
Validate with: inspect_video_project, prepare_structured_script.
Downstream: Block, NarrationUnit, Subtitle.
Failure codes: episode_missing, episode_stale, structure_profile_missing.

### Block

Authority: VideoForge structured content API.
Source: Structured Episode.
Agent write scope: draft proposal only.
Immutable fields: blockId, order, semanticRole.
Stale when: episode generation id changed; block text changed after scene proposal.
Validate with: inspect_video_project, inspect_video_readiness.
Downstream: NarrationUnit, Scene.
Failure codes: block_missing, block_order_invalid, block_boundary_crossed.

### NarrationUnit

Authority: VideoForge alignment and visual planning context.
Source: subtitle-timed narration unit.
Agent write scope: read-only.
Immutable fields: narrationUnitId, blockId, subtitleIds, start, end.
Stale when: alignmentGenerationId changed; subtitle ids changed; subtitle text changed.
Validate with: get_visual_planning_context.
Downstream: Scene, VisualBinding.
Failure codes: narration_unit_missing, narration_unit_stale, narration_unit_crosses_block.

### Subtitle

Authority: VideoForge Alignment.
Source: voiceover generation, SRT import, or alignment API.
Agent write scope: read-only text and read-only time.
Immutable fields: id, text, start, end, alignmentGenerationId.
Stale when: alignmentGenerationId changed; subtitle start/end changed; subtitle text changed.
Validate with: inspect_video_project, validate_video_readiness.
Downstream: Scene, TimelineSegment, Preview.
Failure codes: subtitle_missing, subtitle_timing_missing, subtitle_timing_mutation_forbidden.

### Alignment

Authority: VideoForge audio alignment.
Source: TTS, imported audio, imported SRT, or alignment service.
Agent write scope: read-only.
Immutable fields: alignmentGenerationId, audioPath, duration, subtitleTiming.
Stale when: audio regenerated; source transcript changed; subtitles regenerated.
Validate with: inspect_video_project, inspect_video_readiness.
Downstream: Subtitle, Scene, TimelineSegment.
Failure codes: alignment_missing, alignment_stale, audio_missing.

### Scene

Authority: VideoForge visual scene plan.
Source: narration units grouped by validated Block boundaries.
Agent write scope: proposal only until persisted by API.
Immutable fields: sceneId after persistence, blockId, start, end, narrationUnitIds.
Stale when: visualPlanGenerationId changed; alignmentGenerationId changed; source Block changed.
Validate with: review_visual_scene_plan, validate_video_assets.
Downstream: VisualBinding, TimelineSegment, Preview.
Failure codes: scene_missing, scene_crosses_block, scene_timing_mutation_forbidden, scene_plan_stale.

### Asset

Authority: VideoForge asset library and project assets.
Source: upload, library import, generated visual pack, or existing project asset.
Agent write scope: metadata proposal only.
Immutable fields: assetId, filePath, mediaType, checksum.
Stale when: file missing; checksum changed; user replaced asset.
Validate with: inspect_pending_visuals, validate_video_assets.
Downstream: VisualBinding, Preview, JianYingDraft.
Failure codes: asset_missing, asset_type_invalid, asset_unplayable, asset_conflict.

### VisualBinding

Authority: VideoForge factory visual pairing API.
Source: bind_scene_assets or factory visual import.
Agent write scope: only through API with policy approval when replacing.
Immutable fields: sceneId, assetId, bindingGenerationId.
Stale when: scene plan changed; asset checksum changed; user unbound asset.
Validate with: bind_scene_assets, validate_video_assets.
Downstream: TimelineSegment, Preview.
Failure codes: binding_missing, binding_stale, visual_coverage_incomplete.

### TimelineSegment

Authority: VideoForge renderer and preview builder.
Source: Subtitle, Scene, VisualBinding, and render settings.
Agent write scope: read-only.
Immutable fields: start, end, subtitleIds, sceneId.
Stale when: subtitles changed; scene plan changed; visual binding changed.
Validate with: build_video_preview, audit_video_preview.
Downstream: Preview, JianYingDraft.
Failure codes: timeline_gap, timeline_overlap, timeline_asset_missing.

### Variant

Authority: VideoForge factory batch manifest.
Source: batch item or generated project variant.
Agent write scope: recipe-level proposal only.
Immutable fields: batchId, itemId, projectId, variantId.
Stale when: batch manifest changed; item state changed after inspection.
Validate with: get_video_job_status, inspect_video_project.
Downstream: Preview, JianYingDraft.
Failure codes: variant_missing, item_not_ready, batch_manifest_stale.

### Preview

Authority: VideoForge renderer.
Source: build_video_preview.
Agent write scope: read-only.
Immutable fields: previewPath, previewGenerationId, sourceProjectUpdatedAt.
Stale when: project updated after preview; visual binding changed; audio changed.
Validate with: build_video_preview, audit_video_preview.
Downstream: JianYingDraft, QA report.
Failure codes: preview_missing, preview_stale, preview_unplayable.

### JianYingDraft

Authority: VideoForge export API.
Source: export_editable_draft.
Agent write scope: read-only.
Export mode: create_new.
Immutable fields: draftPath, exportGenerationId, sourceProjectUpdatedAt.
Stale when: project updated after export; preview stale.
Validate with: export_editable_draft.
Downstream: none.
Failure codes: draft_export_failed, draft_path_missing, draft_unopenable.

### Batch

Authority: VideoForge batch manifest and agent factory APIs.
Source: create_video_factory_job or template batch API.
Agent write scope: only through batch APIs.
Immutable fields: batchId, manifestPath, itemIds.
Stale when: manifest version changed; project state differs from manifest source ids.
Validate with: get_video_job_status, recover_video_job.
Downstream: Variant, VisualBinding, Preview.
Failure codes: batch_not_found, batch_manifest_stale, batch_recovery_failed.
