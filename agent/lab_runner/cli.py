from __future__ import annotations

import argparse
import json
from pathlib import Path

from .executor import LabRunner
from .recipe_loader import load_recipe_by_id
from .run_store import RunStore


def _load_json(path: str | None) -> dict:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent.lab_runner.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "run"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--recipe", required=True)
        cmd.add_argument("--input", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--recipe", required=True)
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--input")
    resume.add_argument("--decision-file")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)

    store = RunStore()
    runner = LabRunner(store=store)
    if args.command == "inspect":
        print(json.dumps(store.load(args.run_id), ensure_ascii=False, indent=2))
        return 0
    recipe = load_recipe_by_id(args.recipe)
    case = _load_json(getattr(args, "input", None))
    if args.command == "plan":
        print(json.dumps(runner.plan(recipe, case), ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        print(json.dumps(runner.start(recipe, case), ensure_ascii=False, indent=2))
        return 0
    decisions = _load_json(args.decision_file)
    print(json.dumps(runner.resume(recipe, args.run_id, case, decisions), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
