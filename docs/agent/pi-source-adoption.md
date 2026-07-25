# Pi Source Adoption

## Status

No external Pi source tree, package, version, or commit has been supplied to
this worktree. The initial phase deliberately uses FakePiTransport so the
Director API, UI, approval state, artifact contract, and CI path can be tested
without a model account or network call.

## Integration Boundary

The future PiRpcTransport belongs in backend/agent_runtime. It must expose the
same operations now used by FakePiTransport:

- create or resume a session;
- emit ordered agent and tool events;
- accept cancellation;
- shut down only its own sidecar process.

DirectorService remains the owner of Run state. Pi must not write project JSON,
JianYing files, or a second Run Store.

## Required Source Audit

Before replacing FakePi, record:

1. Pi version, commit, source path, and license.
2. JSONL/RPC framing and request-response correlation implementation.
3. AgentSession and SessionManager lifecycle.
4. Event subscription and replay behavior.
5. ResourceLoader, extensions, skills, and tool registration APIs.
6. Cancellation and shutdown semantics on Windows.
7. Exact copied code, if any, and the upgrade path.

## Current Adopted Modules

None. The existing FakePiTransport is VideoForge-owned test infrastructure,
not copied Pi source.
