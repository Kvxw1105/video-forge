"""Run Phase 0 Video Agent Lab static verification."""

from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CHECKS = [
    ROOT / "agent" / "evals" / "runner" / "run_eval_cases.py",
    ROOT / "agent" / "evals" / "runner" / "lint_agent_lab.py",
]
COMPILE_TARGETS = [
    ROOT / "vforge" / "client.py",
    ROOT / "vforge" / "mcp_server.py",
    ROOT / "agent" / "evals" / "runner" / "run_eval_cases.py",
    ROOT / "agent" / "evals" / "runner" / "lint_agent_lab.py",
    ROOT / "agent" / "evals" / "runner" / "verify_phase0.py",
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


def main() -> int:
    results = [_run(path) for path in CHECKS]
    compile_errors: list[str] = []
    for path in COMPILE_TARGETS:
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            compile_errors.append(f"{path.relative_to(ROOT)}: {exc.msg}")

    failed = [item for item in results if item["returncode"] != 0]
    status = "failed" if failed or compile_errors else "passed"
    summary = {
        "status": status,
        "checks": results,
        "compiled": [str(path.relative_to(ROOT)) for path in COMPILE_TARGETS],
        "compileErrors": compile_errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
