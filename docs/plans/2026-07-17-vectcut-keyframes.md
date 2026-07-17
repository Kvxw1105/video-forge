# VectCutAPI visual keyframes implementation plan

**Goal:** add one provider-neutral visual keyframe model to the canonical
timeline and lower it to JianYing physical image children without changing
project JSON or the existing safe publish flow.

**Implementation:** validate and normalize six properties in the compiler;
preserve keyframes on semantic clips; interpolate child-boundary values in a
separate JianYing lowering module; apply only mapped `KeyframeProperty` values
when constructing `VideoSegment` objects.

**Verification:** compiler edge-case tests, lowering interpolation tests,
adapter parity test, full backend suite, TypeScript check, `git diff --check`,
and an isolated real-image 14-second draft POC. No HTTP/MCP/frontend or real
JianYing client work is included.
