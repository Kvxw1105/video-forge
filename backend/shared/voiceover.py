from pathlib import Path


def select_active_voiceover(audio: dict) -> dict:
    """Return the active playable voiceover config, or {} if none exists."""
    if not isinstance(audio, dict):
        return {}

    voiceovers = audio.get("voiceovers") or []
    if voiceovers:
        # Multi-version mode: only the explicitly active + playable entry counts.
        # Do not silently fall back to an inactive version.
        return next((v for v in voiceovers if _is_playable_voiceover(v) and v.get("isActive")), {})

    legacy = audio.get("voiceover", {})
    return legacy if _is_playable_voiceover(legacy) else {}


def _is_playable_voiceover(vo: dict) -> bool:
    if not isinstance(vo, dict):
        return False
    file_path = str(vo.get("file") or "").strip()
    if not file_path:
        return False

    path = Path(file_path)
    duration = float(vo.get("duration") or 0)
    text = str(vo.get("text") or "").strip()

    # Only reject the classic bare placeholder default, not real files named voiceover.mp3.
    if path.name.lower() == "voiceover.mp3" and not path.is_absolute() and duration <= 0 and not text:
        return False

    if path.is_absolute():
        return path.exists()

    return duration > 0 or bool(text)
