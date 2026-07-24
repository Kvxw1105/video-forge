# MediaKit Provider v0.1

VideoForge uses the official `mediakit-cli` as a local sidecar. The provider boundary exposes canonical names while the adapter alone owns MediaKit command names.

Implemented local capabilities:

- `media.probe` -> `video probe-video-metadata`
- `video.trim` -> `editing trim-video`
- `audio.extract` -> `editing extract-audio`

Install the official sidecar with `npx @volcengine/mediakit-cli install -y`. Set `VIDEOFORGE_MEDIAKIT_CLI` to an absolute executable path when it is not on `PATH`. If the system FFmpeg uses a nightly `N-*` version string, set `VIDEOFORGE_MEDIAKIT_FFMPEG_DIR` to a stable FFmpeg `bin` directory because MediaKit 0.2.0 validates semantic versions. Discovery calls the sidecar's `--schema` endpoint and exposes the returned schema at `GET /api/media/providers/mediakit`.

Submit a request with `POST /api/projects/{project_id}/media/execute`. A successful derived file is ffprobe-validated, copied into the project `assets/` folder, registered in `Project.assets`, and accompanied by a durable record at `media-processing/mediakit/runs/` containing provider, source, parameters, status, result, retryability, privacy mode, idempotency token, and reserved cloud task/cost fields.

The model supports `submitted`, `waiting`, `running`, `succeeded`, `failed`, and `cancelled`. This release only executes synchronous local work. No JianYing edit operation is flattened into an MP4 by this provider.

Official sidecar verification on Windows used MediaKit CLI 0.2.0 and FFmpeg 8.1.2. All three capabilities completed against a real MP4 whose path contains spaces and Chinese characters; trim and extract outputs were validated again with ffprobe.

Next order: cloud task polling and resume; ASR to editable subtitle tracks; scene segmentation to primary-track cuts; separation to voice/BGM tracks; subtitle removal; portrait matting; localizing high-volume capabilities; upstream schema synchronization.
