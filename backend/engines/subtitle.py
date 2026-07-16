import re

def text_to_sentences(text: str) -> list[str]:
    raw = re.split(r'(?<=[。！？；\n])', text)
    return [s.strip() for s in raw if s.strip()]

def sentences_to_srt(sentences: list[str], chars_per_sec: float = 4.0, gap: float = 0.3) -> str:
    srt_lines = []
    current_time = 0.0
    for i, sentence in enumerate(sentences, 1):
        duration = max(1.0, len(sentence) / chars_per_sec)
        start = current_time
        end = current_time + duration
        current_time = end + gap
        srt_lines.append(f"{i}")
        srt_lines.append(f"{_fmt_time(start)} --> {_fmt_time(end)}")
        srt_lines.append(sentence)
        srt_lines.append("")
    return "\n".join(srt_lines)

def srt_to_subtitles(srt_text: str) -> list[dict]:
    pattern = re.compile(
        r'(\d+)\n(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})\n((?:.+\n?)+?)(?=\n\d+\n|\Z)'
    )
    results = []
    for m in pattern.finditer(srt_text.strip()):
        results.append({
            "index": int(m.group(1)),
            "start": _parse_time(m.group(2)),
            "end": _parse_time(m.group(3)),
            "text": m.group(4).strip().replace('\n', ' ')
        })
    return results

def _fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def _parse_time(ts: str) -> float:
    ts = ts.replace(',', '.')
    h, m, s = ts.split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)

def generate_subtitles(text: str) -> tuple[list[dict], str, float]:
    sentences = text_to_sentences(text)
    srt = sentences_to_srt(sentences)
    subs = srt_to_subtitles(srt)
    total_duration = subs[-1]["end"] if subs else 0.0
    return subs, srt, total_duration
