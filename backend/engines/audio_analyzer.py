"""
音频特征分析引擎 — 基于 librosa
提取 BPM、节拍时间戳、onset、RMS 能量、频谱特征、段落分割
"""
import json
import sys
from pathlib import Path
from process_utils import run as run_process


def analyze_audio(audio_path: str | Path) -> dict:
    """
    分析音频文件，返回完整的特征数据。
    这个函数在子进程中运行 librosa，避免主线程阻塞。
    """
    audio_path = str(audio_path)
    script = f'''
import json, sys
import numpy as np
import librosa

y, sr = librosa.load("{audio_path}", sr=22050, mono=True)
duration = float(len(y)) / sr

# 1. BPM + beat timestamps
tempo_result = librosa.beat.beat_track(y=y, sr=sr, units="time")
tempo = float(np.atleast_1d(tempo_result[0])[0]) if hasattr(tempo_result[0], '__len__') else float(tempo_result[0])
beats = np.atleast_1d(tempo_result[1]).tolist() if len(tempo_result) > 1 else []

# 2. Onset detection (音头/重音)
onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="time")
onsets = np.atleast_1d(onset_frames).tolist()

# 3. RMS energy (音量曲线) — 降采样到每秒 10 个点
hop_length = 512
rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
rms_times = librosa.times_like(rms, sr=sr, hop_length=hop_length).tolist()
# 降采样: 每 0.1 秒取一个值
energy = []
step = max(1, int(len(rms) / (duration * 10)))
for i in range(0, len(rms), step):
    energy.append({{"time": round(rms_times[i], 3), "value": round(float(rms[i]), 4)}})

# 4. Spectral centroid (音调高低)
centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]
centroid_times = librosa.times_like(centroid, sr=sr, hop_length=hop_length).tolist()
pitch = []
for i in range(0, len(centroid), step):
    if i < len(centroid_times):
        pitch.append({{"time": round(centroid_times[i], 3), "value": round(float(centroid[i]), 1)}})

# 5. Section detection — 基于能量变化的简单分段
# 计算每秒平均能量
sec_energy = []
sec_dur = 1.0  # 1 秒窗口
for t_start in np.arange(0, duration, sec_dur):
    t_end = min(t_start + sec_dur, duration)
    s_start = int(t_start * sr)
    s_end = int(t_end * sr)
    seg_rms = float(np.sqrt(np.mean(y[s_start:s_end] ** 2))) if s_start < s_end else 0
    sec_energy.append({{"time": round(float(t_start), 1), "energy": round(seg_rms, 4)}})

# 用能量变化找段落边界
threshold = np.mean([e["energy"] for e in sec_energy]) * 0.8 if sec_energy else 0
sections = []
current_section = {{"start": 0, "end": duration, "type": "full"}}
if sec_energy:
    current_start = 0.0
    current_type = "low"
    for i, se in enumerate(sec_energy):
        if se["energy"] > threshold and current_type == "low":
            if i > 0:
                sections.append({{"start": round(current_start, 1), "end": round(se["time"], 1), "type": current_type, "avg_energy": round(np.mean([e["energy"] for e in sec_energy[int(current_start):i]]) if i > int(current_start) else 0, 4)}})
            current_start = se["time"]
            current_type = "high"
        elif se["energy"] <= threshold and current_type == "high":
            sections.append({{"start": round(current_start, 1), "end": round(se["time"], 1), "type": current_type, "avg_energy": round(np.mean([e["energy"] for e in sec_energy[int(current_start):i]]) if i > int(current_start) else 0, 4)}})
            current_start = se["time"]
            current_type = "low"
    sections.append({{"start": round(current_start, 1), "end": round(duration, 1), "type": current_type, "avg_energy": round(np.mean([e["energy"] for e in sec_energy[int(current_start):]]) if sec_energy[int(current_start):] else 0, 4)}})
if not sections:
    sections = [{{"start": 0, "end": round(duration, 1), "type": "full", "avg_energy": 0.5}}]

result = {{
    "duration": round(duration, 3),
    "bpm": round(tempo, 1),
    "beats": [round(b, 3) for b in beats],
    "onsets": [round(o, 3) for o in onsets],
    "energy": energy,
    "pitch": pitch,
    "sections": sections
}}
print(json.dumps(result))
'''
    r = run_process(
        [sys.executable, '-c', script],
        capture_output=True, text=True, timeout=120
    )
    if r.returncode != 0:
        raise RuntimeError(f"Audio analysis failed: {r.stderr[:500]}")
    return json.loads(r.stdout.strip())


def generate_cue_points(analysis: dict, total_images: int, mode: str = "beat") -> list[dict]:
    """
    根据音频分析生成每个图片的时间点（卡点）。
    mode:
      - "beat": 每个节拍切换一张图
      - "onset": 每个重音切换（更密）
      - "energy": 高能量段加速切换，低能量段慢速
      - "section": 按段落分组
    """
    duration = analysis["duration"]
    beats = analysis.get("beats", [])
    onsets = analysis.get("onsets", [])
    energy = analysis.get("energy", [])
    sections = analysis.get("sections", [])

    if total_images <= 0:
        return []

    if mode == "beat" and len(beats) >= 2:
        # 每个节拍切换一张图
        if len(beats) >= total_images:
            # 节拍多于图片：选能量最强的 N 个
            scored = _score_times_by_energy(beats, energy)
            scored.sort(key=lambda x: x[1], reverse=True)
            cue_times = sorted([b[0] for b in scored[:total_images]])
        else:
            # 节拍少于图片：在节拍间均匀插入
            cue_times = _distribute_among_beats(beats, total_images, duration)

    elif mode == "onset" and len(onsets) >= 2:
        if len(onsets) >= total_images:
            scored = _score_times_by_energy(onsets, energy)
            scored.sort(key=lambda x: x[1], reverse=True)
            cue_times = sorted([o[0] for o in scored[:total_images]])
        else:
            cue_times = _distribute_among_beats(onsets, total_images, duration)

    elif mode == "energy" and energy:
        # 高能量段：密集切换；低能量段：稀疏切换
        cue_times = _energy_driven_distribution(energy, total_images, duration)

    elif mode == "section" and sections:
        # 按段落比例分配图片数量
        cue_times = _section_driven_distribution(sections, total_images, duration)

    else:
        # fallback: 均匀分布
        interval = duration / total_images
        cue_times = [i * interval for i in range(total_images)]

    if total_images <= 0:
        return []
    if duration <= 0:
        return [{"time": 0.0, "duration": 0.0} for _ in range(total_images)]

    cue_times = sorted(float(t) for t in cue_times if 0 <= float(t) < duration)
    if not cue_times or cue_times[0] > 0:
        cue_times.insert(0, 0.0)
    cue_times = _ensure_count(cue_times, total_images, duration)

    result = []
    for i, t in enumerate(cue_times):
        end = cue_times[i + 1] if i + 1 < len(cue_times) else duration
        result.append({"time": round(t, 3), "duration": round(max(0.001, end - t), 3)})
    return result


def _ensure_count(times: list[float], total: int, duration: float) -> list[float]:
    """Return exactly `total` monotonically sorted cue times within [0, duration)."""
    # De-duplicate close values first.
    cleaned = []
    for t in sorted(times):
        if not cleaned or abs(t - cleaned[-1]) > 0.05:
            cleaned.append(t)
    times = cleaned

    if len(times) >= total:
        return times[:total]

    # ponytail: fill missing cues uniformly; good enough until smarter beat warping is needed.
    uniform = [i * duration / total for i in range(total)]
    merged = sorted(times + uniform)
    out = []
    for t in merged:
        if 0 <= t < duration and (not out or abs(t - out[-1]) > 0.05):
            out.append(t)
        if len(out) == total:
            break
    while len(out) < total:
        out.append((len(out)) * duration / total)
    return sorted(out[:total])


def _score_times_by_energy(times: list[float], energy: list[dict]) -> list[tuple[float, float]]:
    """给时间点打能量分"""
    scored = []
    for t in times:
        # 找最近的能量点
        best = 0.0
        for e in energy:
            if abs(e["time"] - t) < 0.2:
                best = max(best, e["value"])
        scored.append((t, best))
    return scored


def _distribute_among_beats(anchor_times: list[float], total: int, duration: float) -> list[float]:
    """在锚点（节拍/onset）间均匀分配图片"""
    if not anchor_times:
        return [i * duration / total for i in range(total)]

    result = []
    # 先把锚点分配给前 N 个图片
    anchor_count = min(len(anchor_times), total)
    for i in range(anchor_count):
        result.append(anchor_times[i])

    # 如果图片比锚点多，在锚点之间插入
    if total > anchor_count:
        gaps = []
        for i in range(len(anchor_times) - 1):
            gaps.append((anchor_times[i], anchor_times[i + 1]))
        gaps.append((anchor_times[-1], duration))

        extra_needed = total - anchor_count
        for gap_start, gap_end in gaps:
            gap_len = gap_end - gap_start
            if extra_needed <= 0:
                break
            n_in_gap = max(1, int(extra_needed * gap_len / (duration - anchor_times[-1] + 0.1)))
            for j in range(1, n_in_gap + 1):
                t = gap_start + gap_len * j / (n_in_gap + 1)
                result.append(round(t, 3))
                extra_needed -= 1

    return sorted(result[:total])


def _energy_driven_distribution(energy: list[dict], total: int, duration: float) -> list[float]:
    """高能量段分配更多图片，低能量段分配更少"""
    if not energy:
        return [i * duration / total for i in range(total)]

    total_energy = sum(e["value"] for e in energy) or 1
    result = []
    for i in range(total):
        # 按能量权重分配时间
        target_time = (i / total) * duration
        # 找最近的能量点，用能量值加权
        best_time = target_time
        best_score = -1
        for e in energy:
            score = e["value"] - abs(e["time"] - target_time) * 0.1
            if score > best_score:
                best_score = score
                best_time = e["time"]
        result.append(round(best_time, 3))

    return sorted(set(result))


def _section_driven_distribution(sections: list[dict], total: int, duration: float) -> list[float]:
    """按段落比例分配图片数量"""
    if not sections:
        return [i * duration / total for i in range(total)]

    result = []
    for sec in sections:
        sec_len = sec["end"] - sec["start"]
        n_images = max(1, round(total * sec_len / duration))
        for j in range(n_images):
            t = sec["start"] + sec_len * j / n_images
            result.append(round(t, 3))

    return sorted(result[:total])
