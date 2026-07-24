import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_video_agent_lab_manifest_points_to_existing_assets():
    manifest = json.loads((ROOT / "agent" / "manifest.json").read_text(encoding="utf-8"))
    for group in ("contracts", "prompts", "recipes", "policies"):
        for rel in manifest[group]:
            assert (ROOT / "agent" / rel).exists(), rel


def test_video_agent_lab_linter_passes():
    result = subprocess.run(
        [sys.executable, str(ROOT / "agent" / "evals" / "runner" / "lint_agent_lab.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_video_agent_lab_phase0_verifier_passes():
    result = subprocess.run(
        [sys.executable, str(ROOT / "agent" / "evals" / "runner" / "verify_phase0.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
