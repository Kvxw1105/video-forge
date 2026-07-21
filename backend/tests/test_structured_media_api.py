import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.project import Project
from routers import render, export
from shared.structured_content import compile_structured_media_variant
from test_structured_media import _project


@pytest.fixture
def structured_project(tmp_path):
    return Project.model_validate(_project(tmp_path))


def test_preview_uses_derived_variant_view_and_preserves_project(monkeypatch, tmp_path, structured_project):
    original = copy.deepcopy(structured_project.model_dump())
    captured = []
    monkeypatch.setattr(render, "get_project", lambda _: structured_project)
    monkeypatch.setattr(render, "_project_dir", lambda _: tmp_path)
    monkeypatch.setattr(render, "resolve_project_paths", lambda _, value: value)
    monkeypatch.setattr(render, "probe_media_duration", lambda _: 7.0)
    def fake_render(project, output):
        captured.append(project)
        output.write_bytes(b"mp4")
    monkeypatch.setattr(render, "render_preview", fake_render)
    result = render.generate_structured_variant_preview("p1", "master")
    assert result["variantId"] == "master"
    assert captured[0]["name"].endswith("[master]")
    assert captured[0]["segments"][0]["id"].startswith("master__")
    assert captured[0]["audio"]["voiceoverSegments"]
    assert captured[0]["subtitles"]
    assert structured_project.model_dump() == original


@pytest.mark.parametrize("variant_id", ["publish", "master", "chapter"])
def test_structured_variant_preview_paths_are_distinct(monkeypatch, tmp_path, structured_project, variant_id):
    monkeypatch.setattr(render, "get_project", lambda _: structured_project)
    monkeypatch.setattr(render, "_project_dir", lambda _: tmp_path)
    monkeypatch.setattr(render, "resolve_project_paths", lambda _, value: value)
    monkeypatch.setattr(render, "probe_media_duration", lambda _: 7.0)
    monkeypatch.setattr(render, "render_preview", lambda _, output: output.write_bytes(b"mp4"))
    result = render.generate_structured_variant_preview("p1", variant_id)
    assert result["previewUrl"].endswith(f"preview_{variant_id}.mp4")
    assert (tmp_path / f"preview_{variant_id}.mp4").exists()


def test_direct_export_rejects_replace_explicit(monkeypatch, structured_project):
    monkeypatch.setattr(export, "get_project", lambda _: structured_project)
    with pytest.raises(Exception) as error:
        export.export_structured_variant_direct("p1", "publish", policy="replace_explicit")
    assert getattr(error.value, "status_code", None) == 400


def test_direct_export_uses_each_variant_view(monkeypatch, tmp_path, structured_project):
    captured = []
    monkeypatch.setattr(export, "JIANYING_DRAFT_DIR", tmp_path / "drafts")
    monkeypatch.setattr(export, "get_project", lambda _: structured_project)
    monkeypatch.setattr(export, "_project_dir", lambda _: tmp_path)
    monkeypatch.setattr(export, "resolve_project_paths", lambda _, value: value)
    monkeypatch.setattr(export, "_require_active_voiceover", lambda _: None)
    monkeypatch.setattr(export, "compile_project_timeline", lambda project: SimpleNamespace(
        total_duration=3.5, voiceover_clips=(1, 2), visual_clips=(1,), subtitles=(1,), warnings=(),
    ))
    monkeypatch.setattr(export, "generate_jianying_draft", lambda project, **_: captured.append(project) or SimpleNamespace(
        warnings=(), to_metadata=lambda: {"draftName": project["name"], "finalPath": str(tmp_path / project["name"]), "policy": "create_new"},
    ))
    result = export.export_structured_variant_direct("p1", "master")
    assert result["variantId"] == "master"
    assert captured[0]["name"].endswith("[master]")
