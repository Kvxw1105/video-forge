# SRT Import and Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add robust SRT import to the script workflow and export the current editable subtitle list as SRT.

**Architecture:** Put format logic in a dependency-free backend helper, expose import/export through project subtitle routes, and keep the frontend as a thin upload/download client. Existing project subtitle styles remain authoritative while imported text and timing replace existing captions.

**Tech Stack:** Python 3, FastAPI, pytest, React 18, TypeScript, Vite, Phosphor icons

---

### Task 1: SRT Format Helper

**Files:**
- Create: `backend/shared/srt.py`
- Create: `backend/tests/test_srt.py`

- [ ] Write failing tests that call `decode_srt`, `parse_srt`, `subtitles_to_transcript`, and `serialize_srt` with UTF-8 BOM, GB18030, optional indexes, CRLF, dot milliseconds, multiline captions, and invalid time ranges.
- [ ] Run `python -m pytest backend/tests/test_srt.py -q` and confirm import failure because `shared.srt` does not exist.
- [ ] Implement pure helpers with no filesystem or project dependencies. `parse_srt` returns `(subtitles, ignored_count)` and generated subtitles use `sub_001` IDs.
- [ ] Run `python -m pytest backend/tests/test_srt.py -q` and confirm all helper tests pass.

### Task 2: Project Import And Export Routes

**Files:**
- Modify: `backend/routers/subtitle.py`
- Create: `backend/tests/test_subtitle_routes.py`

- [ ] Write failing route tests proving import saves both script and timed subtitles, preserves existing style, reports ignored blocks, exports UTF-8-BOM SRT with attachment headers, and rejects export without subtitles.
- [ ] Run `python -m pytest backend/tests/test_subtitle_routes.py -q` and confirm failures for missing behavior/routes.
- [ ] Replace the router-local parser with `shared.srt` helpers. Extend `POST /import-srt` to save `script`; add `GET /export-srt` returning `Response` with sanitized UTF-8 filename.
- [ ] Run `python -m pytest backend/tests/test_srt.py backend/tests/test_subtitle_routes.py -q` and confirm all tests pass.

### Task 3: Script Panel Workflow

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/panels/ScriptPanel.tsx`
- Modify: `frontend/src/pages/Editor.tsx`

- [ ] Add `api.exportSrt(projectId)` as a fetch-based Blob download alongside `importSrt`.
- [ ] Add a hidden `.srt` file input and `导入 SRT` button beside the script editor; report progress and pass the returned project/script/subtitles back to the editor.
- [ ] Add `导出 SRT` with a download icon to the generated subtitle-list header; disable it when no subtitles exist.
- [ ] Update `Editor` to refresh its project after import and show success/failure through the existing toast.
- [ ] Run `npm run build` in `frontend` and confirm TypeScript and Vite succeed.

### Task 4: Remove Duplicate Entry And Verify

**Files:**
- Modify: `frontend/src/components/panels/OverlayPanel.tsx`
- Modify: `frontend/src/pages/Editor.tsx`

- [ ] Remove the overlay-panel SRT upload state, input, UI, callback prop, and duplicated Editor callback.
- [ ] Run focused backend tests plus `python -m pytest backend/tests/test_subtitle_text_processing.py backend/tests/test_jianying_subtitles.py -q`.
- [ ] Run `npm run build` in `frontend`.
- [ ] Start or confirm backend/frontend services, then use the browser to import a sample SRT, verify extracted script and preserved timings, export it, and inspect the downloaded file.
