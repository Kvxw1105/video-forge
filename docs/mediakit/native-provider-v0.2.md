# VideoForge Native Media Provider v0.2

VideoForge now owns the high-frequency local media execution path. `videoforge_native` is the default provider for `media.probe`, `video.trim`, and `audio.extract`; the MediaKit CLI adapter remains optional for compatibility and upstream schema comparison.

The native provider includes:

- Canonical VideoForge capability schemas.
- Local-only path validation and subprocess argument arrays with no shell interpolation.
- FFmpeg and FFprobe dependency discovery.
- Native probe normalization for format, video stream, and audio stream metadata.
- Stream-copy video trimming and MP3 extraction.
- Output existence and media-stream validation.
- Project asset registration with provider, capability, source asset, execution ID, parameters, and ffprobe metadata.

Provider selection is optional in execution requests. Omitting `provider` selects `videoforge_native`; callers may explicitly set `provider: "mediakit"` while the compatibility adapter is installed.

The implementation was informed by MediaKit's registry, local executor, generated plans, dependency admission, and safety boundaries. Attribution is retained in `backend/media_processing/THIRD_PARTY_NOTICES.md`.
