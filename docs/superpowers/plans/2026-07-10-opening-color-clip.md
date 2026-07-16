# Opening Color Clip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support a real opening black screen that shifts voiceover/subtitles while letting BGM start independently, and exports correctly to JianYing.

**Architecture:** Keep the existing `type: "black"`/timeline block model. Generate a local color image only when JianYing export needs a real main-track asset, because pyJianYingDraft's main video track must start at 0s. Avoid a broad TimelinePlan refactor in this pass.

**Tech Stack:** FastAPI backend, pyJianYingDraft, FFmpeg preview renderer, React/Vite editor.

---

### Task 1: JianYing Color Clip Export

**Files:**
- Modify: `backend/adapters/jianying.py`
- Test: `backend/tests/test_jianying_color_clip.py`

- [ ] Write a failing test that exports a project with `{type: "black", start: 0, end: 3}` and asserts the first JianYing video segment starts at `0s` with duration `3s`.
- [ ] Implement a small helper that creates/reuses a canvas-sized black PNG in the draft folder.
- [ ] In the main video track loop, when `seg.type` is `black` or `color`, use the generated PNG instead of requiring `assetPath`.
- [ ] Run `python -m pytest backend/tests/test_jianying_color_clip.py -q`.

### Task 2: Opening Black Action

**Files:**
- Modify: `frontend/src/pages/Editor.tsx`
- Modify: `frontend/src/components/panels/AssetPanel.tsx`

- [ ] Add an `onInsertOpeningBlack` callback to `AssetPanel`.
- [ ] Add a compact "开场黑幕 3s" button near carousel controls.
- [ ] In `Editor.tsx`, update `timeline.voiceoverStartAt` to `3`, prepend a black timeline block, regenerate segments when assets exist, and leave BGM `startAt` unchanged.
- [ ] Run `npm run build`.

### Task 3: Verification

- [ ] Run `python -m pytest backend/tests -q`.
- [ ] Run `python -m py_compile backend/adapters/jianying.py backend/engines/renderer.py`.
- [ ] Run `npm run build`.
- [ ] Create or inspect a project with a 3s black opener: preview should show black first, voiceover should start after 3s, and JianYing export should contain a real first main-track clip.
