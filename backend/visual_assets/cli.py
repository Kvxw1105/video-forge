from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contracts import VisualAssetRenderRequest
from .rasterizer import FfmpegSvgRasterizer
from .service import render_visual_asset_project
from .stickman.templates import TEMPLATES


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m visual_assets.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list-templates")
    render = sub.add_parser("render")
    render.add_argument("--input", required=True)
    render.add_argument("--output", required=True)
    render.add_argument("--svg", action="store_true")
    render.add_argument("--png", action="store_true")
    render.add_argument("--contact-sheet", action="store_true")
    regen = sub.add_parser("regenerate")
    regen.add_argument("--input", required=True)
    regen.add_argument("--output", required=True)
    regen.add_argument("--segment-id", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "list-templates":
        for name in sorted(TEMPLATES):
            print(name)
        return 0
    if args.command == "inspect":
        path = Path(args.output) / "manifest.json"
        print(path.read_text(encoding="utf-8") if path.exists() else "{}")
        return 0
    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if args.command == "regenerate":
        raw.setdefault("behavior", {})["existingOutputPolicy"] = "regenerate"
        raw["behavior"]["replaceManualEdits"] = True
        raw["behavior"]["segmentId"] = args.segment_id
    if args.command == "render":
        raw.setdefault("exports", {})["svg"] = bool(args.svg) or raw.get("exports", {}).get("svg", True)
        raw["exports"]["png"] = bool(args.png)
        raw["exports"]["contactSheet"] = bool(args.contact_sheet) or raw.get("exports", {}).get("contactSheet", True)
    result = render_visual_asset_project(VisualAssetRenderRequest.model_validate(raw), Path(args.output), FfmpegSvgRasterizer())
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
