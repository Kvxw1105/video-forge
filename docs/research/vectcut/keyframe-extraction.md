# VectCutAPI keyframe extraction

## Verified source chain

The locked upstream source implements the path:

```text
add_video_keyframe_impl.py
  -> Track.add_pending_keyframe()
  -> Track.process_pending_keyframes()
  -> Visual_segment.add_keyframe()
  -> Keyframe_list.export_json()/Keyframe.export_json()
  -> Script_file.dumps()
  -> save_draft_impl.write_profile_content()
```

Relevant files read directly:

- `add_video_keyframe_impl.py`
- `pyJianYingDraft/track.py`
- `pyJianYingDraft/segment.py`
- `pyJianYingDraft/keyframe.py`
- `pyJianYingDraft/script_file.py`
- `save_draft_impl.py`
- `draft_profiles.py`

The successful upstream experiment at
`D:\A-Project\labs\vectcut\keyframe-experiment\draft_content.json`
confirmed these facts:

- supported source names include `position_x`, `position_y`, `scale_x`,
  `scale_y`, `rotation`, and `alpha`;
- JSON property IDs are `KFTypePositionX`, `KFTypePositionY`,
  `KFTypeScaleX`, `KFTypeScaleY`, `KFTypeRotation`, and `KFTypeAlpha`;
- keyframe `time_offset` is integer microseconds;
- keyframes are stored under
  `tracks[].segments[].common_keyframes[]`, not on the material itself;
- source values are ordinary numeric values; position values are not assumed
  to be clamped to `[-1, 1]` by the upstream API;
- `scale_x`/`scale_y` are positive scale ratios; rotation is degrees; alpha is
  opacity in `[0, 1]`;
- keyframe time is relative to the segment, not absolute project time;
- `pyJianYingDraft` exposes `VisualSegment.add_keyframe(property, time_offset,
  value)` and accepts string times such as `"1.5s"`.

## VideoForge migration decisions

VideoForge keeps one provider-neutral `CompiledKeyframe` model in
`backend/shared/timeline_compiler.py`. It uses clip-local seconds and supports
exactly six first-version properties: `position_x`, `position_y`, `scale_x`,
`scale_y`, `rotation`, and `opacity`. `opacity` maps to upstream JianYing
`alpha` only in the adapter.

Invalid objects, unsupported properties, non-finite/out-of-window times,
non-positive scales, and non-finite values are rejected with compiler
warnings. Opacity is clamped to `[0, 1]` with a warning. Easing is retained as
`linear`; non-linear input is warned and lowered as linear. Duplicate
`property + normalized time` entries use the last valid input and output is
stably sorted.

The JianYing-only module `backend/adapters/jianying_keyframes.py` performs
linear window slicing through the shared compiler math, canonical position
conversion, and the `opacity -> KeyframeProperty.alpha` mapping. The adapter
passes child-local string times to the currently installed public
`VideoSegment.add_keyframe()` API; the generated JSON was checked to contain
integer microsecond `time_offset` values. The module is intentionally separate
from the adapter's draft orchestration.

Canonical position values use the same normalized canvas coordinate system as
static transforms: `0.0` is the left/bottom edge, `0.5` is center, and `1.0`
is the right/top edge. JianYing lowering converts either position property with
`(value - 0.5) * 2`; scale, rotation, and opacity/alpha are not additionally
scaled.

Window slicing is shared by compiler and JianYing lowering. It interpolates a
property at both window boundaries, retains interior source points, converts
to window-local time, deduplicates by `(property, rounded_time)`, and sorts
deterministically. Thus a `0s=1, 10s=2` curve cut at 6 seconds ends at `1.6`,
and the 14-second POC's 6/12-second boundaries remain continuous.

Adapter warnings are accumulated during lowering and merged with compiler
warnings into `DraftWriteResult.warnings`; a supported keyframe write failure
raises a contextual `RuntimeError` instead of producing a superficially valid
draft.

## Long-image boundary POC

The isolated POC is at:

- Script: `D:\A-Project\labs\videoforge-keyframes\poc_keyframes.py`
- Result: `D:\A-Project\labs\videoforge-keyframes\poc-result.json`
- Draft root: `D:\A-Project\labs\videoforge-keyframes\drafts`

It uses a real Pillow-generated PNG and a 14-second semantic image clip. The
generated physical ranges are `0-6`, `6-12`, and `12-14`; scale boundary values
match at 6 seconds (`1.12`) and 12 seconds (`0.9`). JSON parsing, asset
existence, IDs, and keyframe groups were checked. Opening in the real desktop
client remains:

`REAL_JIANYING_VALIDATION_REQUIRED`
