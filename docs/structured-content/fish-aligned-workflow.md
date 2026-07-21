# Fish-aligned Structured Content Workflow

VideoForge keeps Fish credentials in the existing local TTS settings file. The browser only sends structured text, reference ID, and generation options; it never receives or stores the API key.

## Prepare

Create a Structured Episode with enabled Blocks in episode order. Configure the existing Fish Audio key and reference ID through the Settings API/UI. The status endpoint reports configuration without exposing secrets.

## Generate

`POST /api/projects/{project_id}/structured/audio/fish-aligned` sends the complete Episode text once to Fish's timestamp endpoint. The response stream is parsed in arrival order, alignment snapshots are retained per chunk, and chunk-local segment times are converted to global source times.

The aligner normalizes Unicode, punctuation, Latin text, numbers, and Chinese characters before deterministic sequence matching. A Block is accepted only when its confidence is at least 0.75 and the overall match is at least 0.90. Failed alignment never replaces an existing voiceover, subtitles, or bindings.

On success, one `structured_master_<generation>.wav` is saved in the project directory. Every Block references that same voiceover ID with a source range. Generated subtitles carry `fish_timestamp_alignment` metadata and remain in absolute master-audio time.

## Variants

`publish`, `master`, and `chapter` preview/export endpoints compile the existing bindings into derived Project Views. The source project JSON is not rewritten by preview/export. Direct JianYing export always uses `policy=create_new`.

## Cache and errors

`GET /api/projects/{project_id}/structured/audio/status` reads the latest local alignment manifest and never returns a token. Repeating a request should use the existing generation in the UI; `force` is reserved for an explicit regeneration action. Missing credentials return 409, alignment confidence failure returns 422, rate limiting returns 429, and upstream/network failures return 502.

`REAL_FISH_VALIDATION_REQUIRED` remains the correct status when no existing local credentials are configured. Do not paste keys into project JSON, source code, logs, screenshots, PR text, or release artifacts.
