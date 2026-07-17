import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_apply_draft_params_to_project_updates_scale_position_and_subtitle_style():
    from adapters.jianying_sync import apply_draft_params_to_project

    project = {
        "segments": [
            {
                "id": "seg_1",
                "assetPath": "D:/assets/a.png",
                "type": "image",
                "transform": {"x": 0.5, "y": 0.5, "scale": 0.85, "rotation": 0, "fit": "contain"},
            }
        ],
        "subtitles": [
            {
                "id": "sub_1",
                "text": "字幕",
                "start": 0,
                "end": 1,
                "style": {"fontSize": 36, "position": "bottom_center"},
            }
        ],
    }
    draft_params = {
        "videoSegments": [
            {
                "path": "D:/assets/a.png",
                "scaleX": 1.15,
                "scaleY": 1.15,
                "transformX": 0.2,
                "transformY": -0.4,
                "rotation": 5,
            }
        ],
        "textSegments": [
            {
                "type": "subtitle",
                "fontSize": 14,
                "transformX": 0.78,
                "transformY": -0.78,
            }
        ],
    }

    updated, changes = apply_draft_params_to_project(project, draft_params)

    assert changes == {"segments": 1, "subtitles": 1}
    assert updated["segments"][0]["transform"]["scale"] == 1.15
    assert updated["segments"][0]["transform"]["x"] == 0.6
    assert updated["segments"][0]["transform"]["y"] == 0.3
    assert updated["segments"][0]["transform"]["rotation"] == 5
    assert updated["subtitles"][0]["style"]["fontSize"] == 42
    assert updated["subtitles"][0]["style"]["position"] == "top_right"


def test_select_draft_for_project_prefers_project_name(tmp_path):
    from adapters.jianying_sync import select_draft_for_project

    latest = tmp_path / "latest"
    exact = tmp_path / "My Project"
    latest.mkdir()
    exact.mkdir()
    (latest / "draft_content.json").write_text(json.dumps({}), encoding="utf-8")
    (exact / "draft_content.json").write_text(json.dumps({}), encoding="utf-8")

    selected, matched_by = select_draft_for_project({"name": "My Project"}, tmp_path)

    assert selected == exact
    assert matched_by == "project-name"


def test_select_draft_for_project_ignores_internal_directories(tmp_path):
    from adapters.jianying_sync import select_draft_for_project

    visible = tmp_path / "Visible Draft"
    visible.mkdir()
    visible_content = visible / "draft_content.json"
    visible_content.write_bytes(b"visible")
    internal = tmp_path / ".videoforge-backups"
    internal.mkdir()
    internal_content = internal / "draft_content.json"
    internal_content.write_bytes(b"internal")
    internal_content.touch()

    selected, matched_by = select_draft_for_project({"name": ".videoforge-backups"}, tmp_path)

    assert selected == visible
    assert matched_by == "latest"


def test_sync_jianying_params_route_saves_updated_project(monkeypatch, tmp_path):
    from models.project import Project
    from routers import export

    draft = tmp_path / "Project"
    draft.mkdir()
    (draft / "draft_content.json").write_text(json.dumps({}), encoding="utf-8")
    project = Project(
        id="proj_1",
        name="Project",
        segments=[
            {
                "id": "seg_1",
                "assetPath": "D:/assets/a.png",
                "type": "image",
                "start": 0,
                "end": 1,
                "transform": {"x": 0.5, "y": 0.5, "scale": 0.85, "rotation": 0, "fit": "contain"},
            }
        ],
        subtitles=[
            {
                "id": "sub_1",
                "text": "字幕",
                "start": 0,
                "end": 1,
                "style": {"fontSize": 36, "position": "bottom_center"},
            }
        ],
    )
    saved = {}

    monkeypatch.setattr(export, "JIANYING_DRAFT_DIR", tmp_path)
    monkeypatch.setattr(export, "get_project", lambda project_id: project)
    monkeypatch.setattr(
        export,
        "parse_jianying_draft",
        lambda draft_dir: {
            "videoSegments": [{"path": "D:/assets/a.png", "scaleX": 1.2, "transformX": 0.0, "transformY": 0.0}],
            "textSegments": [{"type": "subtitle", "fontSize": 15, "transformX": 0, "transformY": 0.78}],
        },
    )

    def fake_update(project_id, data):
        saved["data"] = data
        return Project(**data)

    monkeypatch.setattr(export, "update_project", fake_update)

    result = export.sync_jianying_params("proj_1")

    assert result["changes"] == {"segments": 1, "subtitles": 1}
    assert result["project"]["segments"][0]["transform"]["scale"] == 1.2
    assert saved["data"]["subtitles"][0]["style"]["fontSize"] == 45
