# Overnight Fish Workbench Report

## Automated validation

- Fish timestamp SSE parser: Mock SSE coverage for ordered audio chunks, multiline data, comments, null alignment, duplicate chunk snapshots, invalid JSON, and global offsets.
- Structured aligner: normalization, deterministic matching, block confidence thresholds, boundary interpolation, and subtitle metadata.
- Materializer/API: valid WAV fixture, one master voiceover, Block bindings, generated subtitles, manifest persistence, missing-key 409, and failure-safe project behavior.
- Legacy regression: the existing backend suite remains the release gate.

## Mock validation

Mock Fish responses use generated PCM WAV bytes and never use a real credential. The mock path verifies source ranges, subtitle generation, cache/status shape, and project persistence boundaries.

## Isolated 8-block E2E smoke

Using generated 32-second WAV and five generated PNGs under `D:\A-Project\labs\videoforge-structured-fish-e2e`, the complete offline materializer produced one master voiceover and bindings for HOOK, CTA_TAG, BRIDGE_IN, STORY, MECHANISM, JUDGMENT, SHORT_OUTRO, and BRIDGE_OUT.

- `publish`: 27.0s content, 27.5s MP4, 6 voiceover clips, 6 text segments.
- `master`: 17.0s content, 17.5s MP4, 3 voiceover clips, 3 text segments.
- `chapter`: 22.0s content, 22.5s MP4, 5 voiceover clips, 5 text segments.

All three MP4s contain video and audio streams. All three JianYing drafts contain video, audio, and text tracks; target timeranges start at zero and are contiguous. Source timeranges reference the same generated master WAV. No staging path or user asset is involved.

## Real Fish validation

Not executed unless an existing local credential and reference ID are already configured. No new key was requested, created, printed, or persisted.

## Remaining validation

Real Fish timestamp response schema and real JianYing visual playback require a local credential/client and remain manual or conditional smoke checks.
