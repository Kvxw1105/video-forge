import re
import asyncio
import httpx
import tempfile
import json
from pathlib import Path
from config import MANBO_API_KEY, MANBO_API_URL, MANBO_MAX_CHARS
from process_utils import run as run_process
from shared.text_processing import normalize_script_for_tts, split_script_for_subtitles

EDGE_VOICE = "zh-CN-XiaoxiaoNeural"
EDGE_MAX_CHARS = 500
SILENCE_DURATION = 0.3  # 音频块间的静音间隙（秒）


# ── 文本分句（与 subtitle.py 保持一致） ─────────────────────

def split_sentences(text: str) -> list[str]:
    """按标点/换行拆成句子。无标点时fallback到空格拆分。"""
    # 先试试按句末标点+换行拆
    raw = re.split(r'(?<=[。！？；\n])', text)
    sentences = [s.strip() for s in raw if s.strip()]

    # 如果拆出来只有一句（说明没有句末标点也没有换行），按空格再拆一次
    if len(sentences) <= 1:
        raw2 = re.split(r'(?<=[，、；\s])', text)
        sentences = [s.strip() for s in raw2 if s.strip()]

    # 如果还是只有一句，整段返回
    if not sentences:
        sentences = [text]

    return sentences


def normalize_for_tts(text: str, engine: str) -> str:
    """
    根据引擎特性规范化文本。
    - manbo: 换行→句号，无标点时空格也→句号（曼波认句号停顿）
    - edge/custom: 保持原样（Edge TTS 自然处理换行/标点）
    """
    if engine == "manbo":
        normalized = re.sub(r'\n+', '。', text)
        normalized = re.sub(r'\s+', ' ', normalized)
        # 如果文本中没有句末标点，把空格转句号
        if not re.search(r'[。！？；]', normalized):
            normalized = re.sub(r' +', '。', normalized)
        normalized = re.sub(r'。{2,}', '。', normalized)
        return normalized
    return text


def split_sentences(text: str) -> list[str]:
    return split_script_for_subtitles(text)


def normalize_for_tts(text: str, engine: str) -> str:
    return normalize_script_for_tts(text)


def batch_sentences(sentences: list[str], max_chars: int) -> list[str]:
    """把句子合并成不超过 max_chars 的批，长句按自然断点切开。"""
    batches, current = [], ""
    for sentence in sentences:
        for part in _split_long_sentence(sentence, max_chars):
            if len(current) + len(part) <= max_chars:
                current += part
            else:
                if current:
                    batches.append(current)
                current = part
    if current:
        batches.append(current)
    return batches or ([sentences[0][:max_chars]] if sentences else [])


def _split_long_sentence(text: str, max_chars: int) -> list[str]:
    """Split one sentence into <= max_chars chunks, preferring punctuation/space near the limit."""
    text = text.strip()
    if not text:
        return []
    out = []
    while len(text) > max_chars:
        window = text[:max_chars + 1]
        cut_at = -1
        for sep in ['。', '！', '？', '；', '，', '、', ' ', ',']:
            idx = window.rfind(sep)
            if idx >= max(1, int(max_chars * 0.45)):
                cut_at = idx + len(sep)
                break
        if cut_at <= 0:
            cut_at = max_chars
        out.append(text[:cut_at].strip())
        text = text[cut_at:].strip()
    if text:
        out.append(text)
    return out


# ── 音频时长探测 ──────────────────────────────────────────

def probe_duration(path: Path) -> float:
    """用 ffprobe 获取音频实际时长（秒）"""
    try:
        r = run_process(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', str(path)],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(r.stdout)
        for s in data.get('streams', []):
            dur = s.get('duration')
            if dur:
                return float(dur)
    except Exception:
        pass
    return 0.0


# ── 曼波 VIP API ────────────────────────────────────────────

def synthesize_manbo(text: str, api_url: str = None, api_key: str = None, speed: int = 0, fmt: str = "mp3") -> bytes:
    url = api_url or MANBO_API_URL
    key = api_key or MANBO_API_KEY
    params = {"text": text, "key": key, "speed": str(speed), "format": fmt}
    headers = {"Authorization": f"Bearer {key}"}
    resp = httpx.get(url, params=params, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 200:
        raise RuntimeError(f"曼波 API 错误: {data.get('msg', 'unknown')}")
    mp3_url = data.get("url")
    if not mp3_url:
        raise RuntimeError(f"响应中没有音频 URL: {data}")
    audio_resp = httpx.get(mp3_url, timeout=60)
    audio_resp.raise_for_status()
    return audio_resp.content


# ── Edge TTS ──────────────────────────────────────────

def _edge_rate_value(speed: float) -> str:
    value = float(speed or 0)
    return f"{value:+g}%"


def _edge_pitch_value(pitch: float) -> str:
    value = float(pitch or 0)
    return f"{value:+g}Hz"


async def _synthesize_edge_async(
    text: str,
    voice: str,
    output_path: str = None,
    rate: str = "+0%",
    volume: str = "+0%",
    pitch: str = "+0Hz",
) -> bytes:
    try:
        import edge_tts
    except ModuleNotFoundError as exc:
        raise RuntimeError("Edge TTS 依赖未安装，请先安装 edge-tts") from exc
    communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume, pitch=pitch)
    if output_path:
        await communicate.save(output_path)
        return Path(output_path).read_bytes()
    else:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        await communicate.save(tmp_path)
        data = Path(tmp_path).read_bytes()
        Path(tmp_path).unlink(missing_ok=True)
        return data


def synthesize_edge(text: str, voice: str = EDGE_VOICE, rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
    return asyncio.run(_synthesize_edge_async(text, voice, rate=rate, pitch=pitch))


def synthesize_edge_to_file(
    text: str,
    output_path: Path,
    voice: str = EDGE_VOICE,
    rate: str = "+0%",
    pitch: str = "+0Hz",
):
    asyncio.run(_synthesize_edge_async(text, voice, str(output_path), rate=rate, pitch=pitch))


# ── 自定义 API ──────────────────────────────────────────────

def synthesize_custom(text: str, api_url: str, api_key: str = "", speed: int = 0) -> bytes:
    if not api_url:
        raise ValueError("自定义 API URL 不能为空")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"text": text, "speed": speed}
    resp = httpx.post(api_url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    ct = resp.headers.get("content-type", "")
    if "audio" in ct or resp.headers.get("content-disposition", ""):
        return resp.content
    try:
        data = resp.json()
    except Exception:
        return resp.content
    for key in ("url", "audio_url", "data", "mp3", "audio"):
        val = data.get(key, "")
        if val and isinstance(val, str) and val.startswith("http"):
            audio_resp = httpx.get(val, timeout=60)
            audio_resp.raise_for_status()
            return audio_resp.content
    return resp.content


# ── Fish Audio ───────────────────────────────────────────────

FISH_API_URL = "https://api.fish.audio/v1/tts"
FISH_MAX_CHARS = 5000  # Fish 单次支持 1 万字，留一半 buffer


def synthesize_fish(
    text: str,
    api_key: str = "",
    reference_id: str = "",
    model: str = "s2.1-pro-free",
    fmt: str = "mp3",
    speed: float = 1.0,
) -> bytes:
    """
    Fish Audio TTS。返回 mp3 字节。
    - API: https://api.fish.audio/v1/tts
    - Auth: Bearer <key>
    - Body: { text, reference_id, model, format }
    """
    if not api_key:
        raise ValueError("Fish Audio API Key 未配置")
    if not reference_id:
        raise ValueError("Fish Audio reference_id 未配置")

    payload = {
        "text": text,
        "reference_id": reference_id,
        "model": model,
        "format": fmt,
    }
    if speed and float(speed) != 1.0:
        payload["prosody"] = {"speed": float(speed)}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "model": model,
    }
    resp = httpx.post(FISH_API_URL, json=payload, headers=headers, timeout=120)
    # Fish 错误返回 JSON，正常返回音频二进制
    ct = resp.headers.get("content-type", "")
    if resp.status_code != 200 or "audio" not in ct and "octet-stream" not in ct:
        try:
            err = resp.json()
            raise RuntimeError(f"Fish Audio 错误 [{resp.status_code}]: {err.get('message', err)}")
        except Exception:
            raise RuntimeError(f"Fish Audio 错误 [{resp.status_code}]: {resp.text[:200]}")
    return resp.content


# ── 统一接口 ────────────────────────────────────────────────

def generate_voiceover(
    text: str,
    output_dir: Path,
    engine: str = "edge",
    speed: float = 0,
    pitch: float = 0,
    settings=None,
) -> tuple[Path, float]:
    """
    生成配音音频。
    返回: (音频文件路径, 实际音频时长秒数)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if engine == "edge":
        voice = getattr(settings, "edgeVoice", EDGE_VOICE) if settings else EDGE_VOICE
        return _generate_with_sentences(text, output_dir, "edge", voice, speed, pitch, EDGE_MAX_CHARS)
    elif engine == "manbo":
        api_url = getattr(settings, "manboApiUrl", MANBO_API_URL) if settings else MANBO_API_URL
        api_key = getattr(settings, "manboApiKey", MANBO_API_KEY) if settings else MANBO_API_KEY
        return _generate_with_sentences(text, output_dir, "manbo", voice=None, speed=speed,
                                         pitch=0, max_chars=MANBO_MAX_CHARS, api_url=api_url, api_key=api_key)
    elif engine == "fish_audio":
        api_key = getattr(settings, "fishApiKey", "") if settings else ""
        reference_id = getattr(settings, "fishReferenceId", "") if settings else ""
        model = getattr(settings, "fishModel", "s2.1-pro-free") if settings else "s2.1-pro-free"
        return _generate_with_sentences(text, output_dir, "fish_audio", voice=None, speed=speed,
                                         pitch=0, max_chars=FISH_MAX_CHARS, api_key=api_key,
                                         api_url=reference_id, model=model)
    elif engine == "custom":
        if not settings or not settings.customApiUrl:
            raise ValueError("自定义 API 未配置 URL")
        return _generate_with_sentences(text, output_dir, "custom", voice=None, speed=speed,
                                         pitch=0, max_chars=500, api_url=settings.customApiUrl, api_key=settings.customApiKey)
    else:
        raise ValueError(f"未知引擎: {engine}")


def _generate_with_sentences(
    text: str, output_dir: Path, engine: str,
    voice: str | None, speed: float, pitch: float, max_chars: int,
    api_url: str = "", api_key: str = "",
    model: str = "s2-pro",
) -> tuple[Path, float]:
    """
    按句分批合成 → 块间插静音 → 测实际时长 → 返回
    """
    # 1. 分句 → 分批
    sentences = split_sentences(text)
    batches = batch_sentences(sentences, max_chars)

    if not batches:
        raise ValueError("文案为空")

    # 2. 逐批合成（传给API前做引擎特定的规范化）
    part_paths: list[Path] = []
    for i, batch in enumerate(batches):
        part = output_dir / f"voice_part_{i:03d}.mp3"
        api_text = normalize_for_tts(batch, engine)  # ← 关键：换行→句号等规范化
        try:
            if engine == "edge":
                synthesize_edge_to_file(
                    api_text,
                    part,
                    voice or EDGE_VOICE,
                    rate=_edge_rate_value(speed),
                    pitch=_edge_pitch_value(pitch),
                )
            elif engine == "manbo":
                data = synthesize_manbo(api_text, api_url, api_key, speed=speed)
                part.write_bytes(data)
            elif engine == "fish_audio":
                fish_speed = speed if speed and float(speed) > 0 else 1.0
                data = synthesize_fish(api_text, api_key, api_url, model=model, speed=fish_speed)
                part.write_bytes(data)
            elif engine == "custom":
                data = synthesize_custom(api_text, api_url, api_key, speed=speed)
                part.write_bytes(data)
        except Exception as e:
            # Clean up partial files and re-raise with context
            for p in part_paths:
                p.unlink(missing_ok=True)
            raise RuntimeError(f"第 {i+1}/{len(batches)} 段配音合成失败: {e}") from e
        part_paths.append(part)

    # 3. 拼接音频（块间插静音）
    final_path = _concat_with_gaps(part_paths, output_dir)

    # 4. 测实际时长
    actual_duration = probe_duration(final_path)
    if actual_duration <= 0:
        actual_duration = sum(len(b) for b in batches) / 4.0  # fallback

    return final_path, actual_duration


def _concat_with_gaps(parts: list[Path], output_dir: Path) -> Path:
    """拼接音频，块间插入静音间隙。文件名带时间戳，支持多版本共存。"""
    from datetime import datetime
    final_path = output_dir / f"voiceover_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"

    if len(parts) == 1:
        parts[0].replace(final_path)
        return final_path

    # 创建静音文件
    silence_path = output_dir / "_silence.mp3"
    run_process(
        ['ffmpeg', '-y', '-f', 'lavfi', '-i', f'anullsrc=r=44100:cl=stereo',
         '-t', str(SILENCE_DURATION), str(silence_path)],
        capture_output=True, check=True
    )

    # 构建 concat 列表，块间插入静音
    concat_parts = []
    for p in parts:
        concat_parts.append(p)
        concat_parts.append(silence_path)
    concat_parts.pop()  # 去掉最后一段静音

    list_path = output_dir / "_concat_list.txt"
    list_path.write_text("\n".join(f"file '{p.name}'" for p in concat_parts), encoding="utf-8")

    run_process(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
         "-c", "copy", str(final_path)],
        cwd=str(output_dir), capture_output=True, check=True
    )

    # 清理
    list_path.unlink(missing_ok=True)
    silence_path.unlink(missing_ok=True)
    for p in parts:
        if p != final_path and p.exists():
            p.unlink()
    return final_path
