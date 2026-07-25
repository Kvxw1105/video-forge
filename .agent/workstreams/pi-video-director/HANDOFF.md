# Pi Video Director Handoff

## Current Architecture

The Director Desk calls the FastAPI Director API. DirectorService persists Run
state and ordered event records through DirectorStore. FakePiTransport remains
the deterministic default. An opt-in PiRpcTransport now launches the audited
Pi RPC entrypoint as a per-run sidecar, persists session metadata, captures
streamed events, and performs abort plus controlled child shutdown. The first
Pi extension is a restricted recipe-contract tool with no raw workspace access.
The first VideoForge plugin, vector_card, creates an SVG artifact in the Run
artifact directory. An approval gates the binding step; approval resumes the Run
and creates preview and JianYing candidate artifacts.

## Implemented

- Director endpoints for Run create/list/read, event replay, SSE, messages,
  approvals, resume, cancel, and artifacts.
- API version endpoint returning branch, commit, build time, and environment.
- Director Desk UI with task creation, timeline, approval action, version
  display, and artifact list.
- FakePi closed loop with mockTransport=true, liveCallPerformed=false, and
  networkCalls=0.
- Local SVG vector-card plugin artifact.
- Audited and built Pi source at commit 8eef62ed3ea62d646a7fad92fa583fc8d71fec17.
- Added PiRpcTransport JSONL sidecar, a restricted extension, and RPC/API smoke checks.

## Not Implemented

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
FakePi is in-process for the default CI path. PiRpcTransport is launched and
stopped by the backend adapter only when VIDEOFORGE_PI_TRANSPORT=rpc.

DirectorStore is now only a compatibility adapter over the Lab RunStore. New
Director Runs are persisted under .agent-runs alongside Lab Runs. The old
projects/.director-runs directory may remain on a developer machine from the
first implementation pass; it is historical data and must not be deleted by
this workstream.

DirectorService now loads the selected Lab Recipe before Run creation, persists
its id/version/step count in the Run, and emits a recipe.loaded event. Unknown
recipe ids return HTTP 422 without creating a Run.

Recipe loading uses the repository-relative agent/recipes directory so it works
when the production backend process starts from the backend directory.

## Environment

Optional values VIDEOFORGE_BRANCH, VIDEOFORGE_COMMIT, VIDEOFORGE_BUILD_TIME,
and VIDEOFORGE_ENV override the API version endpoint.

## Commands

    python scripts\verify_pi_director.py
    python scripts\verify_pi_rpc_transport.py
    cd frontend
    npm run build

## Local Entry Verification

The workstream started its own detached uvicorn process:

    PID: 9212
    Port: 8012
    URL: http://127.0.0.1:8012/director
    Command: python -m uvicorn production_app:app --host 127.0.0.1 --port 8012

At 2026-07-25T01:57:15Z, GET /director returned 200 and GET
/api/version returned branch codex/pi-video-director with the initial Director
code commit 6df7cd851a21c9610a8922f1d59b5b339fdd78e7.

## Known Limitations

The delivery artifacts are candidate marker files, not the real renderer MP4
or JianYing output. Pi session startup is real, but Pi prompts are not yet the
completion authority for the Lab recipe.

The Lab closed-loop verifier reaches mock Fish generation and visual asset
binding on this machine, then can stall in the real ffmpeg preview process.
The item remains at rendering_preview with a zero-byte preview file after the
verifier's 30-second HTTP limit. This is an open renderer/environment issue,
not a passing verification result.

## Next Precise Task

Translate Pi streamed events into the Director timeline and bind one
approval-gated Lab recipe action through the existing Lab Runner/Factory API.
Keep Pi restricted to explicit VideoForge extensions; do not enable raw Pi
read, write, edit, bash, or filesystem tools.

## Draft PR

Draft PR #29 is open against codex/video-agent-lab:

https://github.com/Kvxw1105/video-forge/pull/29

Its verify workflow passed for the initial implementation branch. The workstream
is ready for handoff; the next agent should start with the real Pi source audit.
