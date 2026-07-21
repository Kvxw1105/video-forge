# JianYing Text Segment Compatibility

This note records the production invariant established while validating long
subtitle tracks against JianYing desktop. A draft that parses as JSON and has
the expected number of track segments is not necessarily usable by the client.

## Failure pattern

The generated draft contained 239 text segments and 239 text materials, but
JianYing displayed only the first few subtitle clips. The target time ranges
were valid, ordered, non-overlapping, and covered the full voiceover duration.

The missing dependency was in each text segment's `extra_material_refs`.
`pyJianYingDraft.TextSegment` inherits a speed material reference, while the
library's text branch did not register the corresponding object in
`materials.speeds`. JianYing discarded most segments with unresolved refs.

VideoForge repairs this boundary in
`backend/adapters/jianying.py:_add_jianying_text_segment` by registering the
segment through `ScriptFile.add_segment` and then ensuring its speed material
is present.

## Required invariants

For every generated text segment:

- `material_id` resolves to an entry in `materials.texts`;
- every ID in `extra_material_refs` resolves to a material entry;
- target ranges use integer microseconds and have positive duration;
- subtitle ranges remain ordered and non-overlapping;
- the last subtitle end time matches the expected transcript coverage;
- direct-export staging stays outside the JianYing-watched draft root until
  media path rewriting and validation complete.

The regression check is
`backend/tests/test_jianying_export_safety.py:test_real_renderer_text_segments_have_no_orphan_material_refs`.

## Layout conversion

Project text sizes are canvas pixels; JianYing `TextStyle.size` uses a different
scale. The current conversion is `font_size / 6`, with a minimum of 2. JianYing
also uses an upward-positive Y axis, so project top-to-bottom coordinates must
invert Y during lowering. These conversions live in
`backend/shared/render_params.py` and are covered by focused tests.

## Delivery gate

Do not approve a JianYing text change from structural counts alone. Validation
must include:

1. JSON parse and reference-integrity checks.
2. A long subtitle fixture, not only two or three sample captions.
3. Real JianYing playback near the beginning, middle, and end.
4. Visual confirmation of font size, wrapping, and vertical placement.

This check applies to subtitles, titles, watermarks, and directory-progress
text because they share the same lowering path.
