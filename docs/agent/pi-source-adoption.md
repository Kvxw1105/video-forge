# Pi Source Adoption

## Adopted Source

- Repository: https://github.com/earendil-works/pi
- Local audit checkout: `D:/A-Project/video-forge-worktrees/pi-source`
- Audited commit: `8eef62ed3ea62d646a7fad92fa583fc8d71fec17`
- Package: `@earendil-works/pi-coding-agent` `0.82.0`
- License: MIT

No Pi source is copied into VideoForge. VideoForge launches Pi's built
`packages/coding-agent/dist/rpc-entry.js` as a sidecar and speaks Pi's public
RPC protocol.

## Implemented Boundary

`PiRpcTransport` in `backend/agent_runtime/pi_transport.py` owns one child
process per Director Run. It uses Pi's strict LF JSONL framing, correlates
responses by `id`, forwards unsolicited events into the Director event stream,
and maps cancellation to Pi `abort` followed by a bounded child shutdown.

The authoritative Pi session id and session file returned by `get_state` are
persisted in the Director Run. VideoForge remains the owner of Lab RunStore,
project JSON, VisualPlan binding, preview generation, and JianYing drafts.

The production switch is deliberately opt-in:

```powershell
$env:VIDEOFORGE_PI_TRANSPORT = 'rpc'
$env:VIDEOFORGE_PI_SOURCE = 'D:\A-Project\video-forge-worktrees\pi-source'
```

`fake` remains the default transport, which preserves deterministic CI and
does not make a model or network request.

## Tool Boundary

Pi starts with all built-in tools disabled. The only explicit extension is
`backend/agent_runtime/pi_extensions/recipe_contract.mjs` and its only tool is
`videoforge_recipe_contract`. It can describe the already-selected Lab recipe
contract, but has no filesystem, process, network, project-write, renderer, or
JianYing permissions.

## Source Evidence

- RPC entry: `packages/coding-agent/src/rpc-entry.ts`
- JSONL framing: `packages/coding-agent/src/modes/rpc/jsonl.ts`
- Commands/responses: `packages/coding-agent/src/modes/rpc/rpc-types.ts`
- RPC lifecycle and signal cleanup: `packages/coding-agent/src/modes/rpc/rpc-mode.ts`

Minimum build order verified on Windows:

```powershell
npm ci --ignore-scripts
npm --prefix packages/tui run build
npm --prefix packages/ai run build
npm --prefix packages/agent run build
npm --prefix packages/coding-agent run build
```

## Verification

- `python scripts/verify_pi_rpc_transport.py`: starts built Pi, obtains a
  correlated `get_state` response, confirms a non-mock session, then aborts and
  shuts down the sidecar.
- API smoke with `VIDEOFORGE_PI_TRANSPORT=rpc`: Director Run records
  `transport=pi_rpc`, a real Pi session id, and reaches `cancelled` after
  controlled shutdown.

## Still Separate

- Pi prompts are not yet the completion authority for the Lab recipe.
- Pi event translation into Director planning/tool timeline is not yet wired.
- VideoForge's Factory preview/JianYing render chain remains separate; its
  known local ffmpeg preview stall is not masked by this adapter.
