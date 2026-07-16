from models.project import Project
from services import template_service
from services.template_service import get_template


def test_builtin_templates_define_distinct_visual_modes():
    single = get_template("tpl_single_voiceover")
    carousel = get_template("tpl_carousel")

    assert single is not None
    assert carousel is not None
    assert single["visualMode"] == "single"
    assert carousel["visualMode"] == "carousel"
    assert single["templateId"] != carousel["templateId"]


def test_new_project_defaults_to_single_visual_mode():
    project = Project(id="project_single")

    assert project.visualMode == "single"


def test_legacy_project_with_distinct_visual_segments_infers_carousel():
    project = Project(
        id="project_legacy_carousel",
        segments=[
            {"id": "one", "assetPath": "one.png", "type": "image", "start": 0, "end": 1},
            {"id": "two", "assetPath": "two.png", "type": "image", "start": 1, "end": 2},
        ],
    )

    assert project.visualMode == "carousel"


def test_saved_template_strips_project_media_and_generated_content(monkeypatch, tmp_path):
    monkeypatch.setattr(template_service, "TEMPLATES_DIR", tmp_path)

    saved = template_service.save_template({
        "name": "clean preset",
        "visualMode": "single",
        "audio": {
            "voiceover": {
                "api": "fish_audio",
                "voice": "voice-a",
                "speed": 1.1,
                "volume": 0.8,
                "file": r"D:\\old-project\\voiceover.mp3",
                "duration": 10,
                "text": "old script",
            },
            "voiceovers": [{"file": r"D:\\old-project\\voiceover.mp3"}],
            "bgm": {
                "file": r"D:\\old-project\\bgm.mp3",
                "tracks": [{"file": r"D:\\old-project\\bgm.mp3"}],
                "volume": 0.25,
                "loop": False,
            },
            "sfx": [{"file": r"D:\\old-project\\click.wav"}],
        },
    })

    assert saved["audio"]["voiceover"] == {
        "api": "fish_audio",
        "voice": "voice-a",
        "speed": 1.1,
        "volume": 0.8,
    }
    assert saved["audio"]["voiceovers"] == []
    assert saved["audio"]["bgm"] == {"volume": 0.25, "loop": False}
    assert saved["audio"]["sfx"] == []
