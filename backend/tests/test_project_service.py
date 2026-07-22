import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.project import Project
from routers import project as project_router
from services import project_service
from shared.voiceover import select_active_voiceover


def test_new_project_has_no_fake_voiceover_file():
    assert Project().audio.voiceover.file == ""


def test_placeholder_voiceover_is_not_migrated():
    project = Project(audio={"voiceover": {"file": "voiceover.mp3", "duration": 0, "text": ""}})
    assert project.audio.voiceovers == []


def test_placeholder_voiceover_is_not_selected():
    active = select_active_voiceover({
        "voiceovers": [],
        "voiceover": {"file": "voiceover.mp3", "duration": 0, "text": ""},
    })
    assert active == {}


def test_get_project_raises_parse_error_instead_of_returning_missing(monkeypatch, tmp_path):
    project_id = "proj_bad"
    project_dir = tmp_path / project_id
    project_dir.mkdir()
    (project_dir / "project.json").write_text('{"id": "proj_bad"', encoding="utf-8")
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)

    with pytest.raises(project_service.ProjectLoadError) as exc:
        project_service.get_project(project_id)

    assert project_id in str(exc.value)
    assert "project.json" in str(exc.value)


def test_get_project_route_reports_load_error_as_500(monkeypatch):
    monkeypatch.setattr(
        project_router,
        "get_project",
        lambda project_id: (_ for _ in ()).throw(project_service.ProjectLoadError("bad json")),
    )

    with pytest.raises(project_router.HTTPException) as exc:
        project_router.get_one("proj_bad")

    assert exc.value.status_code == 500
    assert "bad json" in str(exc.value.detail)


def test_create_project_ids_do_not_collide(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)

    first = project_service.create_project("first")
    second = project_service.create_project("second")

    assert first.id != second.id
    assert (tmp_path / first.id / "project.json").exists()
    assert (tmp_path / second.id / "project.json").exists()


def _atomic_payload(project_id="proj_atomic"):
    return {"id": project_id, "name": "atomic"}


def test_atomic_structured_project_validation_failure_creates_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    with pytest.raises(Exception):
        project_service.create_project_from_payload({"id": "bad", "name": "bad", "canvas": {"ratio": "not-a-ratio"}})
    assert list(tmp_path.iterdir()) == []


def test_atomic_structured_project_write_failure_cleans_staging(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    original_open = Path.open

    def fail_temp_open(path, *args, **kwargs):
        if path.name == "project.json.tmp":
            raise OSError("disk full")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_temp_open)
    with pytest.raises(OSError, match="disk full"):
        project_service.create_project_from_payload(_atomic_payload())
    assert list(tmp_path.iterdir()) == []


def test_atomic_structured_project_publish_failure_cleans_staging(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    original_replace = project_service.os.replace
    calls = []

    def fail_directory_publish(source, target):
        calls.append((source, target))
        if len(calls) == 2:
            raise OSError("directory rename failed")
        return original_replace(source, target)

    monkeypatch.setattr(project_service.os, "replace", fail_directory_publish)
    with pytest.raises(OSError, match="directory rename failed"):
        project_service.create_project_from_payload(_atomic_payload())
    assert list(tmp_path.iterdir()) == []


def test_update_project_keeps_valid_previous_version_as_backup(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    project = project_service.create_project("before")
    project_file = tmp_path / project.id / "project.json"
    original = project_file.read_text(encoding="utf-8")

    updated = project_service.update_project(project.id, {"name": "after"})

    assert updated is not None
    assert updated.name == "after"
    assert (tmp_path / project.id / "project.json.bak").read_text(encoding="utf-8") == original
    assert not (tmp_path / project.id / "project.json.tmp").exists()


def test_create_project_applies_template_in_one_operation(monkeypatch, tmp_path):
    from services import template_service

    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(template_service, "TEMPLATES_DIR", tmp_path / "templates")
    template = template_service.save_template({
        "name": "carousel preset",
        "templateId": "image_carousel",
        "visualMode": "carousel",
        "canvas": {"ratio": "16:9", "width": 1920, "height": 1080},
        "timeline": {"voiceoverStartAt": 3, "blocks": [{"type": "black", "duration": 3}]},
        "audio": {
            "voiceover": {"api": "fish_audio", "voice": "voice-a", "file": "old.mp3"},
            "voiceovers": [{"file": "old.mp3", "duration": 12}],
            "bgm": {"file": "old-bgm.mp3", "tracks": [{"file": "old-bgm.mp3"}]},
        },
    })

    project = project_service.create_project("from template", template_id=template["id"])

    assert project.visualMode == "carousel"
    assert project.canvas.ratio == "16:9"
    assert project.timeline.voiceoverStartAt == 3
    assert project.audio.voiceover.api == "fish_audio"
    assert project.audio.voiceover.file == ""
    assert project.audio.voiceovers == []
    assert project.audio.bgm.file == ""
    assert project.audio.bgm.tracks == []


def test_deleted_project_can_be_restored(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    project = project_service.create_project("recover me")

    trash_item = project_service.delete_project(project.id)

    assert trash_item is not None
    assert project_service.get_project(project.id) is None
    assert project_service.list_deleted_projects()[0]["name"] == "recover me"

    restored = project_service.restore_project(trash_item["trashId"])

    assert restored is not None
    assert restored.id == project.id
    assert restored.name == "recover me"
    assert project_service.list_deleted_projects() == []


def test_delete_project_refuses_non_project_directories(monkeypatch, tmp_path):
    monkeypatch.setattr(project_service, "PROJECTS_DIR", tmp_path)
    trash_root = tmp_path / ".trash"
    trash_root.mkdir()

    assert project_service.delete_project(".trash") is None
    assert trash_root.exists()

def test_resolve_project_paths_resolves_multi_voiceovers(tmp_path):
    voice_file = tmp_path / "vo_active.mp3"
    voice_file.write_bytes(b"mp3")
    project = {
        "audio": {
            "voiceover": {"file": "legacy.mp3"},
            "voiceovers": [
                {"id": "a", "file": "vo_active.mp3", "isActive": True, "duration": 1.2},
                {"id": "b", "file": "missing.mp3", "isActive": False, "duration": 0.8},
            ],
            "bgm": {"tracks": []},
        },
        "segments": [],
    }

    resolved = project_service.resolve_project_paths(tmp_path, project)
    active = resolved["audio"]["voiceovers"][0]["file"]
    assert Path(active).is_absolute()
    assert Path(active).exists()
    # missing relative path stays relative
    assert resolved["audio"]["voiceovers"][1]["file"] == "missing.mp3"


def test_select_active_voiceover_skips_placeholder_and_prefers_active(tmp_path):
    real = tmp_path / "real.mp3"
    real.write_bytes(b"mp3")
    audio = {
        "voiceover": {"file": "voiceover.mp3", "duration": 0, "text": ""},
        "voiceovers": [
            {"id": "old", "file": str(real), "isActive": False, "duration": 2.0},
            {"id": "cur", "file": str(real), "isActive": True, "duration": 2.0},
        ],
    }
    active = select_active_voiceover(audio)
    assert active.get("id") == "cur"


def test_select_active_voiceover_no_inactive_fallback_when_versions_exist(tmp_path):
    real = tmp_path / "real.mp3"
    real.write_bytes(b"mp3")
    audio = {
        "voiceovers": [
            {"id": "old", "file": str(real), "isActive": False, "duration": 2.0},
        ],
    }
    assert select_active_voiceover(audio) == {}
