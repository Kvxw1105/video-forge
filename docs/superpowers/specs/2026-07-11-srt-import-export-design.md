# VideoForge SRT Import and Export Design

## Goal

Make SRT a first-class interchange format in the script workflow. A user can import an SRT file from the script panel, immediately retain its subtitle timing, edit or generate voiceover from the extracted text, and export the current subtitle list as a standard SRT file.

## User Experience

- Put `导入 SRT` beside the script editor so users find it before voice generation.
- Importing replaces the current script and subtitle list after a file is selected.
- Extracted caption text is written into the script as one caption per line.
- Imported start/end times remain active until voiceover is generated again.
- Put a visible `导出 SRT` action in the generated subtitle-list header.
- Export is enabled only when the project has subtitles and downloads `<project-name>.srt`.
- Remove the duplicate SRT import control from the overlay/adjustment panel.

## Parsing And Serialization

- Decode UTF-8 with or without BOM, then fall back to GB18030 for common Chinese Windows files.
- Accept CRLF/LF line endings, optional numeric sequence lines, comma or dot milliseconds, and multiline caption text.
- Reject files with no valid captions. Ignore malformed blocks when at least one valid caption exists and return an ignored count.
- Reject individual captions whose end time is not after the start time.
- Preserve current project subtitle styling while replacing text and timing.
- Serialize current subtitles in chronological list order with CRLF line endings, comma milliseconds, a UTF-8 BOM, and sequential indexes starting at 1.

## Architecture

The backend is the source of truth. `backend/shared/srt.py` owns pure parsing, decoding, transcript extraction, and serialization. The subtitle router applies parsed data to projects and streams exports. The React client only uploads a file, refreshes project state, and downloads the returned file. This makes the same behavior reusable by future GUI, batch, AI, and MCP callers.

## Error Handling

- Unsupported/invalid SRT: HTTP 400 with a clear Chinese message.
- Missing project: HTTP 404.
- Project with no subtitles on export: HTTP 400.
- Frontend reports import errors through the existing editor toast and always resets the hidden file input.

## Verification

- Unit tests prove decoding, tolerant parsing, invalid timing handling, transcript extraction, and serialization.
- Router tests prove import updates both `script` and `subtitles`, and export returns an SRT attachment.
- Frontend TypeScript/Vite build proves component contracts.
- Browser validation proves button placement, real file import, visible subtitle count/list, and downloaded SRT content.
