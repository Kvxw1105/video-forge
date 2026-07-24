# Artifact Contract

Agent artifacts are references to VideoForge-owned facts or agent-owned reasoning outputs. They are not a second copy of the project.

## Artifact Reference Shape

Required fields:

- artifactId
- kind
- authority
- projectId
- batchId
- itemId
- sceneId
- sourceGenerationIds
- uri
- createdAt
- stale

## Artifact Kinds

| Kind | Authority | Mutable | Required Source Ids | Validation |
| --- | --- | --- | --- | --- |
| script_analysis | agent | append-only | sourceDocumentHash, structureProfileId | schema validation |
| structured_episode_proposal | agent | append-only | sourceDocumentHash, structureProfileId | user approval before materialization |
| scene_plan_report | agent | append-only | alignmentGenerationId, projectUpdatedAt | no cross-Block scenes |
| visual_generation_pack | VideoForge | immutable | visualPlanGenerationId | file exists and scene ids match |
| pending_visuals_report | VideoForge | immutable snapshot | batchManifestVersion | missing scenes listed by sceneId |
| asset_validation_report | VideoForge | immutable snapshot | bindingGenerationId | no missing required assets |
| preview_ref | VideoForge | immutable | projectUpdatedAt, previewGenerationId | file playable |
| draft_export_ref | VideoForge | immutable | projectUpdatedAt, exportGenerationId | draft path exists |
| qa_report | agent plus VideoForge facts | append-only | previewGenerationId | every scene-specific issue points to sceneId |
| run_log | agent | append-only | runId | conforms to run log schema |

## Stale Rules

An artifact is stale when any source generation id differs from the current VideoForge fact. Stale artifacts may be displayed for explanation but must not drive a write step.

## Storage Rules

- Project files stay under VideoForge project storage.
- Agent artifacts stay under the future Agent Run Store or the Phase 0 eval/run output directories.
- Artifacts may contain summaries, decisions, and references. They must not embed full project JSON unless a test fixture explicitly marks itself as synthetic.

## Failure Codes

- artifact_missing
- artifact_stale
- artifact_schema_invalid
- artifact_authority_mismatch
- artifact_source_generation_mismatch
- artifact_scene_reference_invalid
