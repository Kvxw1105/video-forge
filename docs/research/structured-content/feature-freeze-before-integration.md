# Structured Content Feature Freeze

This authoring slice is the final large capability before integration and release validation. It provides a deterministic Markdown/marker import path, user-confirmed Episode Blocks and Variant presets, a safe Structured Project create/update API, a four-step browser entry point, and read-only Agent/MCP operations.

## Available before integration

- Structured Episode creation and Block/Variant editing.
- Fish timestamp alignment and automatic subtitle materialization (existing backend path).
- Publish, master, and chapter media variants.
- Composition catalog, compile, preview, and JianYing export.
- Agent/MCP access through the backend HTTP contract.
- Windows candidate packaging from the existing portable workflow.

## Deferred validation

- Real Fish Audio calls and credentials.
- Independent portable startup validation.
- Complete browser workflow validation.
- Human JianYing playback validation.
- Stacked PR integration and merge order.

Until these checks are complete, do not add multi-track/PIP, transitions, filters, stickers, or other large editing features. Keep the authoring contract deterministic and preserve legacy projects unchanged.
