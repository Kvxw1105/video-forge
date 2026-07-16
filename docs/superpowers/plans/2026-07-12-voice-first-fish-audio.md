# Voice-First Fish Audio Configuration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make voice selection the first-class action in the script panel while keeping provider and API settings as advanced configuration.

**Architecture:** Reuse the existing persisted `fishVoicePresets` settings field and `fishReferenceId` API path. The frontend will show a direct Fish Audio voice picker, allow users to save custom Reference IDs or pasted voice URLs locally, and copy a provider configuration prompt without exposing API keys.

**Tech Stack:** React 18, TypeScript, existing settings API, Phosphor Icons, Vite build and browser verification

---

### Task 1: Direct Voice Picker

**Files:**
- Modify: `frontend/src/components/panels/ScriptPanel.tsx`

- [ ] Add a Fish Audio voice picker state and open it automatically when the Fish Audio provider button is selected.
- [ ] Render built-in and saved presets with name, style, selected state, and one-click activation above advanced Fish settings.
- [ ] Keep API key, model, speed, and raw Reference ID under the existing advanced configuration section.
- [ ] Run `npm run build` and confirm TypeScript/Vite compile.

### Task 2: Custom Voice And AI Handoff

**Files:**
- Modify: `frontend/src/components/panels/ScriptPanel.tsx`

- [ ] Add a compact custom voice form accepting a name, style, and Fish Audio URL or Reference ID. Extract a 32-character hex ID when a URL is pasted and otherwise use the trimmed value.
- [ ] Save the new profile through the existing `onTtsSettingsChange` path without copying or displaying the API key.
- [ ] Add `复制给 AI` to copy provider, voice name, Reference ID, model, and speed as plain text; report clipboard success/failure in the existing status area.
- [ ] Do not add an unverified “麦克阿瑟” preset; users can import its ID when they have a valid Fish Audio voice page.
- [ ] Run `npm run build` and inspect the picker in the browser at desktop and narrow widths.

### Task 3: Verification

**Files:**
- Modify: `docs/audit-reports/2026-07-12-voice-first-fish-audio.png` (generated evidence only)

- [ ] Verify selecting Fish Audio exposes voices without opening advanced settings.
- [ ] Verify selecting a preset updates the active Reference ID and persists through the existing settings request.
- [ ] Verify custom voice save and AI copy never include API key text.
- [ ] Verify the default voice list remains usable when `fishVoicePresets` is empty and no voice is hard-coded for the unverified MacArthur request.
