import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.tts_settings import TtsSettings
from routers import settings


def test_tts_settings_response_masks_api_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "_SETTINGS_FILE", tmp_path / "tts_settings.json")
    settings._save_settings(TtsSettings(
        fishApiKey="fish-secret",
        manboApiKey="manbo-secret",
        volcApiKey="volc-secret",
        customApiKey="custom-secret",
    ))

    public = settings.get_tts_settings()

    assert public["fishApiKey"] == ""
    assert public["manboApiKey"] == ""
    assert public["volcApiKey"] == ""
    assert public["customApiKey"] == ""
    assert public["fishApiKeyConfigured"] is True
    assert public["manboApiKeyConfigured"] is True
    assert public["volcApiKeyConfigured"] is True
    assert public["customApiKeyConfigured"] is True


def test_blank_key_from_masked_form_preserves_existing_secret(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "_SETTINGS_FILE", tmp_path / "tts_settings.json")
    settings._save_settings(TtsSettings(fishApiKey="fish-secret", fishSpeed=1.0))

    public = settings.update_tts_settings({
        "fishApiKey": "",
        "fishApiKeyConfigured": True,
        "fishSpeed": 1.2,
    })

    assert settings.get_tts_settings_raw().fishApiKey == "fish-secret"
    assert settings.get_tts_settings_raw().fishSpeed == 1.2
    assert public["fishApiKey"] == ""
    assert public["fishApiKeyConfigured"] is True
