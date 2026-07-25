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

Transparent PNG sequences, WebM alpha, ProRes 4444 MOV, and alpha-capable multi-track composition remain second-stage work. They require separate Preview and JianYing compatibility decisions because the current Preview path encodes H.264 MP4 without alpha.

## Picture-in-Picture V1

Code Visual can also be generated as a normal MP4 overlay while preserving the
scene's existing background asset. This is a small extension of the existing
project overlay contract, not a second scene or timeline:

```text
POST /api/projects/{project_id}/visual-assets/code-visual/render
{
  "presentationMode": "overlay",
  "overlayX": 0.5,
  "overlayY": 0.32,
  "overlayScale": 0.36,
  "overlayOpacity": 1.0,
  "overlayDurationPolicy": "loop"
}
```

The generated video remains a normal `Project.assets` video record with an id
such as `visual_code_visual_overlay_scene_code`. The scene preserves its
`primaryAssetId`; its `metadata.videoOverlayIds` records the related asset.
The project records placement and timing in `overlays.videoOverlays[]`, for
example:

```json
{
  "id": "code_visual_overlay_scene_code",
  "assetId": "visual_code_visual_overlay_scene_code",
  "start": 0,
  "end": 2,
  "x": 0.5,
  "y": 0.32,
  "scale": 0.36,
  "opacity": 1,
  "durationPolicy": "loop",
  "zIndex": 0
}
```

The shared timeline compiler resolves and validates this record. Preview feeds
the overlay MP4 to FFmpeg as a second visual input and composites it over the
main visual. JianYing export creates a second video track named
`code_visual_overlay` with the same timing and transform. V1 is opaque MP4
picture-in-picture: opacity is applied by Preview, but JianYing opacity parity
is not implemented yet. Preview currently renders the PIP layer after subtitle
filters, so the default upper-middle placement avoids the subtitle band.
