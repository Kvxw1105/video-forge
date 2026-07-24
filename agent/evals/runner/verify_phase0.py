"""Run Phase 0 Video Agent Lab static verification."""

from __future__ import annotations

import argparse
import json
import py_compile
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
STATIC_CHECKS = [
    ROOT / "agent" / "evals" / "runner" / "run_eval_cases.py",
    ROOT / "agent" / "evals" / "runner" / "lint_agent_lab.py",
]
COMPILE_TARGETS = [
    ROOT / "vforge" / "client.py",
    ROOT / "vforge" / "mcp_server.py",
    ROOT / "agent" / "evals" / "runner" / "run_eval_cases.py",
    ROOT / "agent" / "evals" / "runner" / "lint_agent_lab.py",
    ROOT / "agent" / "evals" / "runner" / "verify_phase0.py",
    ROOT / "agent" / "lab_runner" / "models.py",
    ROOT / "agent" / "lab_runner" / "recipe_loader.py",
    ROOT / "agent" / "lab_runner" / "policy_checker.py",
    ROOT / "agent" / "lab_runner" / "run_store.py",
    ROOT / "agent" / "lab_runner" / "artifact_registry.py",
    ROOT / "agent" / "lab_runner" / "tool_registry.py",
    ROOT / "agent" / "lab_runner" / "executor.py",
    ROOT / "agent" / "lab_runner" / "cli.py",
]


def _run(path: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "name": str(path.relative_to(ROOT)),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _closed_loop_status(base_url: str, report_dir: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "agent.lab_runner.closed_loop", "run", "--base-url", base_url, "--report-dir", report_dir],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    if result.returncode:
        return {"status": "failed", "stdout": result.stdout, "stderr": result.stderr}
    return {"status": "passed", "report": json.loads(result.stdout)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", choices=["static", "closed-loop", "full"], default="full")
    parser.add_argument("--base-url", default="http://127.0.0.1:8767")
    parser.add_argument("--report-dir", default="agent/evals/results")
    args = parser.parse_args(argv)

    results = [_run(path) for path in STATIC_CHECKS] if args.level in {"static", "full"} else []
    compile_errors: list[str] = []
    if args.level in {"static", "full"}:
        for path in COMPILE_TARGETS:
            try:
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as exc:
                compile_errors.append(f"{path.relative_to(ROOT)}: {exc.msg}")

    failed = [item for item in results if item["returncode"] not in {0, 2}]
    closed_loop = _closed_loop_status(args.base_url, args.report_dir) if args.level in {"closed-loop", "full"} else {"status": "not_requested"}
    status = "failed" if failed or compile_errors else closed_loop["status"] if args.level in {"closed-loop", "full"} and closed_loop["status"] != "passed" else "passed"
    summary = {
        "level": args.level,
        "status": status,
        "checks": results,
        "compiled": [str(path.relative_to(ROOT)) for path in COMPILE_TARGETS],
        "compileErrors": compile_errors,
        "closedLoop": closed_loop,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if status == "failed" else 2 if status == "incomplete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
