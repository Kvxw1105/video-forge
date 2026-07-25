# Code Visual Motion Assets

PR #28 integrates \`code_visual_svg\` through the existing Visual Asset Provider system. The SVG renderer still emits deterministic SVG/PNG assets, Manifest entries, generation reports, cache hashes, Project.assets records, and VisualScene bindings.

## Current Motion Status

- The donor HTML workbench animation is driven by browser JavaScript (\`renderAt(t)\` with \`requestAnimationFrame\`), not by self-animating SVG files.
- Exported SVG files are static layered SVGs. Importing one as a normal SVG/image asset loses the MotionPlan animation.
- \`motionHint.motionPlan\` is persisted in Manifest items and a \`.motion.json\` sidecar.
- For \`code_visual_svg\`, the backend now bakes SVG + MotionPlan into an ordinary MP4, registers that MP4 as a \`Project.assets\` video asset, binds it to the VisualScene, and writes a normal \`segments\` video clip for the existing Preview renderer.

## Chosen First-Stage Route

The first-stage production route is:

\`\`\`text
SVG + MotionPlan -> MP4 -> Project.assets video -> VisualScene primaryAssetId -> Preview segment
\`\`\`

This keeps one main visual track, uses the existing FFmpeg Preview renderer, uses the existing JianYing main video track path, and avoids adding a parallel Scene, Timeline, Manifest, cache, or project store.

## Deferred Transparent Motion

Transparent PNG sequences, WebM alpha, ProRes 4444 MOV, overlay tracks, and multi-visual-track composition remain second-stage work. They require separate Preview and JianYing compatibility decisions because the current first-stage Preview path expects a normal main visual asset and encodes H.264 MP4 without alpha.
