import re


DEFAULT_MAX_SUBTITLE_CHARS = 18


def normalize_script_for_tts(text: str) -> str:
    """Normalize user script before sending it to TTS.

    Spaces become Chinese commas so TTS pauses naturally.
    Dunhao is preserved as-is.
    """
    if not text:
        return ""
    normalized = text.replace("\u3000", " ")
    normalized = re.sub(r"[ \t\r\n]+", "，", normalized)
    normalized = re.sub(r"[，]+", "，", normalized)
    normalized = re.sub(r"\s*([，。！？；?!;])\s*", r"\1", normalized)
    normalized = re.sub(r"^[，]+|[，]+$", "", normalized)
    return normalized.strip()


def split_script_for_subtitles(text: str, max_chars: int = DEFAULT_MAX_SUBTITLE_CHARS) -> list[str]:
    """Split script into short subtitle segments.

    Split on commas and sentence punctuation. Do not split on dunhao.
    Long chunks fall back to max_chars.
    """
    normalized = normalize_script_for_tts(text)
    if not normalized:
        return []

    raw_parts = re.findall(r"[^，。！？；?!;]+[，。！？；?!;]?", normalized)
    segments: list[str] = []
    for part in raw_parts:
        part = part.strip(" \t\r\n")
        if not part:
            continue
        segments.extend(_split_long_part(part, max_chars))
    return segments


def _split_long_part(text: str, max_chars: int) -> list[str]:
    if max_chars <= 0 or len(text) <= max_chars:
        return [text] if text else []

    out: list[str] = []
    rest = text
    while len(rest) > max_chars:
        cut_at = max_chars
        window = rest[: max_chars + 1]
        for sep in ("，", "。", "；", "！", "?", ";", ","):
            idx = window.rfind(sep)
            if idx >= max(1, int(max_chars * 0.45)):
                cut_at = idx + 1
                break
        out.append(rest[:cut_at].strip(" \t\r\n"))
        rest = rest[cut_at:].strip(" \t\r\n")
    if rest:
        out.append(rest)
    return [item for item in out if item]
