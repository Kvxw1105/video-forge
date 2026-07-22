import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.project import Project
from routers import composition
from test_structured_composition import source_project, composition_project


def test_catalog_excludes_legacy(monkeypatch, tmp_path):
    structured = Project.model_validate(source_project(tmp_path, "A"))
    legacy = Project(id="legacy", name="Legacy")
    monkeypatch.setattr(composition, "list_projects", lambda: [{"id": "A"}, {"id": "legacy"}])
    monkeypatch.setattr(composition, "get_project", lambda project_id: structured if project_id == "A" else legacy)
    result = composition.structured_catalog()
    assert [item["projectId"] for item in result] == ["A"]
    assert "fishApiKey" not in result[0]


def test_compile_api_returns_items_and_does_not_mutate(monkeypatch, tmp_path):
    source = Project.model_validate(source_project(tmp_path, "A"))
    comp = composition_project([{"id": "chapter", "sourceProjectId": "A", "variantId": "chapter", "chapterTitle": "A", "chapterCardDuration": 1.0}])
    before = copy.deepcopy(comp.model_dump())
    monkeypatch.setattr(composition, "get_project", lambda project_id: source if project_id == "A" else comp)
    monkeypatch.setattr(composition, "_project_dir", lambda _: tmp_path)
    monkeypatch.setattr(composition, "resolve_project_paths", lambda _, value: value)
    result = composition.compile_composition("composition")
    assert result["itemCount"] == 1
    assert result["duration"] == 4.0
    assert comp.model_dump() == before


def test_preview_api_uses_compiled_view(monkeypatch, tmp_path):
    source = Project.model_validate(source_project(tmp_path, "A"))
    comp = composition_project([{"id": "chapter", "sourceProjectId": "A", "variantId": "chapter"}])
    captured = []
    monkeypatch.setattr(composition, "get_project", lambda project_id: source if project_id == "A" else comp)
    monkeypatch.setattr(composition, "_project_dir", lambda _: tmp_path)
    monkeypatch.setattr(composition, "resolve_project_paths", lambda _, value: value)
    monkeypatch.setattr(composition, "render_preview", lambda view, output: captured.append(view) or output.write_bytes(b"mp4"))
    result = composition.preview_composition("composition")
    assert result["status"] == "ok"
    assert captured[0]["name"].endswith("[composition]")
    assert (tmp_path / "preview_composition.mp4").exists()


def test_export_rejects_replace_policy(monkeypatch):
    with pytest.raises(Exception) as error:
        composition.export_composition("composition", policy="replace_explicit")
    assert error.value.status_code == 400
