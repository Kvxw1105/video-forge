# Pi Video Director Handoff

## Current Architecture

The Director Desk calls the FastAPI Director API. DirectorService persists Run
state and ordered event records through DirectorStore. The current transport is
FakePiTransport; it emits deterministic session and tool-call events without
network access. The first plugin, vector_card, creates an SVG artifact in the
Run artifact directory. An approval gates the binding step; approval resumes the
Run and creates preview and JianYing candidate artifacts.

## Implemented

- Director endpoints for Run create/list/read, event replay, SSE, messages,
  approvals, resume, cancel, and artifacts.
- API version endpoint returning branch, commit, build time, and environment.
- Director Desk UI with task creation, timeline, approval action, version
  display, and artifact list.
- FakePi closed loop with mockTransport=true, liveCallPerformed=false, and
  networkCalls=0.
- Local SVG vector-card plugin artifact.

## Not Implemented

- Real Pi source adoption, RPC sidecar, and session persistence.
- Connection from DirectorService to actual Video Agent Lab recipe execution.
- Binding generated artifacts into a real VideoForge Project or VisualPlan.
- Real preview MP4 or JianYing draft output through the Director path.
- Browser refresh smoke, packaged candidate, GitHub PR/CI delivery.

## Key Files

- backend/agent_runtime/director_service.py
- backend/agent_runtime/director_store.py
- backend/agent_runtime/pi_transport.py
- backend/agent_runtime/plugin_tools.py
- backend/routers/director.py
- backend/routers/version.py
- frontend/src/pages/DirectorDesk.tsx
- scripts/verify_pi_director.py

## API

POST /api/director/runs creates a Run. GET /api/director/runs/{id}/events
replays ordered events. GET /api/director/runs/{id}/stream emits SSE with
Last-Event-ID support and heartbeats. POST /api/director/runs/{id}/approvals
resolves the pending action and resumes the Run.

## Process Relationship

The frontend never starts a process. The FastAPI process owns DirectorService.
FakePi is in-process for the initial phase. The real Pi sidecar must be launched
and stopped by the backend adapter only.

## Environment

Optional values VIDEOFORGE_BRANCH, VIDEOFORGE_COMMIT, VIDEOFORGE_BUILD_TIME,
and VIDEOFORGE_ENV override the API version endpoint.

## Commands

    python scripts\verify_pi_director.py
    cd frontend
    npm run build

## Local Entry Verification

The workstream started its own detached uvicorn process:

    PID: 37348
    Port: 8011
    URL: http://127.0.0.1:8011/director
    Command: python -m uvicorn production_app:app --host 127.0.0.1 --port 8011

At 2026-07-25T01:57:15Z, GET /director returned 200 and GET
/api/version returned branch codex/pi-video-director with the initial Director
code commit 6df7cd851a21c9610a8922f1d59b5b339fdd78e7.

## Known Limitations

The delivery artifacts are candidate marker files, not the real renderer MP4
or JianYing output. No Pi source has been adopted yet.

## Next Precise Task

Audit the supplied Pi source version, add a PiRpcTransport that preserves the
existing FakePiTransport interface, then use Director tool events to invoke the
existing Lab Runner and Factory APIs.

## Draft PR

Draft PR #29 is open against codex/video-agent-lab:

https://github.com/Kvxw1105/video-forge/pull/29

Its verify workflow started after the initial feature and handoff commits.
