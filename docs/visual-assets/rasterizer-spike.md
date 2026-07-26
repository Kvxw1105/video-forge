# Rasterizer Spike

Tested on Windows on 2026-07-24.

| Candidate | Result |
| --- | --- |
| FFmpeg | The binary lists svg_pipe and PNG, but actual SVG decoding failed with Decoding requested, but no decoder found for svg. Not selected. |
| CairoSVG | Not installed. |
| resvg | Not installed. |
| Playwright | Not installed. |
| ImageMagick | No usable magick command. |
| Pillow | Installed; selected for the restricted line/circle/ellipse/rect/polyline/polygon SVG subset emitted by this provider. |

PillowSvgRasterizer renders offline RGBA PNG through a .tmp.png staging file,
validates PNG dimensions/alpha, and atomically publishes the final PNG. FFmpeg
remains an optional probe candidate but is not used by project integration on
this machine.

The restricted rasterizer does not claim general SVG support: unsupported SVG
paths are omitted. Provider templates retain stick figures made from supported
primitives, so output stays visible and transparent.
