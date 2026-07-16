# VideoForge V0 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建单图贯穿旁白视频的完整链路——上传图片、输入文案、生成配音字幕、导出剪映草稿。

**Architecture:** FastAPI 后端 (Python 3.11) + React 前端 (Vite + TypeScript + Tailwind CSS v3) + pyJianYingDraft 生成剪映草稿 + 曼波 VIP API 配音。JSON 文件存储，无数据库。

**Tech Stack:** Python 3.11.9, FastAPI, Pydantic, pyJianYingDraft, FFmpeg, React 18, TypeScript, Vite, Tailwind CSS v3, Framer Motion, @phosphor-icons/react

---

### Task 1: 项目脚手架 — 后端

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/config.py`
- Create: `backend/main.py`

- [ ] **Step 1: 创建 requirements.txt**

```txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.3
python-multipart==0.0.18
aiofiles==24.1.0
pyjianyingdraft==0.2.7
```

Run: `pip install -r backend/requirements.txt`

- [ ] **Step 2: 创建 config.py**

```python
# backend/config.py
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECTS_DIR = BASE_DIR / "projects"
TEMPLATES_DIR = BASE_DIR / "templates"
PROJECTS_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

MANBO_API_KEY = os.getenv("MANBO_API_KEY", "")
MANBO_API_URL = "https://api.milorapart.top/apis/mbAIscvip"
MANBO_MAX_CHARS = 250  # 安全上限,API 硬限制 299
```

- [ ] **Step 3: 创建 main.py 骨架**

```python
# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="VideoForge", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
```

- [ ] **Step 4: 验证后端启动**

Run: `cd backend && python -m uvicorn main:app --reload --port 8000`

Expected: 访问 `http://localhost:8000/api/health` 返回 `{"status":"ok","version":"0.1.0"}`

---

### Task 2: 后端数据模型

**Files:**
- Create: `backend/models/__init__.py`
- Create: `backend/models/project.py`
- Create: `backend/models/template.py`

- [ ] **Step 1: 创建 Project 数据模型**

```python
# backend/models/__init__.py
from .project import Project, Canvas, Asset, Segment, Audio, Subtitle, Overlay, ExportSettings
from .template import Template
```

```python
# backend/models/project.py
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

class Canvas(BaseModel):
    ratio: Literal["9:16", "16:9", "1:1", "4:5"] = "9:16"
    width: int = 1080
    height: int = 1920
    fps: int = 30
    background: dict = Field(default_factory=lambda: {"type": "color", "value": "#000000"})

class Asset(BaseModel):
    id: str
    type: Literal["image", "audio", "video"]
    name: str
    path: str
    metadata: dict = Field(default_factory=dict)

class Segment(BaseModel):
    id: str
    assetPath: str
    type: Literal["image", "video"]
    start: float = 0.0
    end: float = 0.0
    transform: dict = Field(default_factory=lambda: {
        "x": 0.5, "y": 0.5, "scale": 0.85, "rotation": 0, "fit": "contain"
    })
    animation: Optional[dict] = None

class AudioConfig(BaseModel):
    api: Literal["manbo_vip", "manbo_free"] = "manbo_vip"
    voice: str = "manbo"
    speed: int = 0
    file: str = "voiceover.mp3"

class BGMConfig(BaseModel):
    file: str = ""
    volume: float = 0.3
    loop: bool = True
    fadeIn: float = 0.0
    fadeOut: float = 2.0

class Audio(BaseModel):
    voiceover: AudioConfig = Field(default_factory=AudioConfig)
    bgm: BGMConfig = Field(default_factory=BGMConfig)

class Subtitle(BaseModel):
    id: str
    text: str
    start: float
    end: float
    style: dict = Field(default_factory=lambda: {
        "fontSize": 36, "color": "#ffffff",
        "strokeColor": "#000000", "strokeWidth": 2, "position": "bottom"
    })

class Overlay(BaseModel):
    title: dict = Field(default_factory=lambda: {
        "text": "", "position": "top_center", "fontSize": 48,
        "color": "#ffffff", "enabled": False
    })
    watermark: dict = Field(default_factory=lambda: {
        "text": "", "position": "top_right", "fontSize": 24,
        "color": "#ffffff80", "enabled": False
    })

class ExportSettings(BaseModel):
    targets: list[str] = ["jianying_draft"]
    outputDir: str = ""

class Project(BaseModel):
    id: str = ""
    name: str = "未命名项目"
    version: str = "0.1"
    canvas: Canvas = Field(default_factory=Canvas)
    templateId: str = "single_image_voiceover"
    assets: list[Asset] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    audio: Audio = Field(default_factory=Audio)
    subtitles: list[Subtitle] = Field(default_factory=list)
    overlays: Overlay = Field(default_factory=Overlay)
    exportSettings: ExportSettings = Field(default_factory=ExportSettings)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
```

```python
# backend/models/template.py
from pydantic import BaseModel
from typing import Optional

class Template(BaseModel):
    id: str
    name: str
    type: str = "workflow"
    version: str = "0.1"
    canvas: dict
    segments: list[dict]
    audio: dict
    overlays: dict
```

- [ ] **Step 2: 验证模型可导入**

Run: `cd backend && python -c "from models.project import Project; p = Project(); print(p.model_dump_json(indent=2))"`

Expected: 打印出完整的默认 project JSON

---

### Task 3: 后端项目服务

**Files:**
- Create: `backend/services/__init__.py`
- Create: `backend/services/project_service.py`

- [ ] **Step 1: 实现项目 CRUD**

```python
# backend/services/project_service.py
import json
import uuid
from pathlib import Path
from datetime import datetime
from config import PROJECTS_DIR
from models.project import Project

def _project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id

def _project_file(project_id: str) -> Path:
    return _project_dir(project_id) / "project.json"

def create_project(name: str, canvas_ratio: str = "9:16") -> Project:
    pid = f"proj_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    project = Project(id=pid, name=name)
    w, h = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}.get(canvas_ratio, (1080, 1920))
    project.canvas.width = w
    project.canvas.height = h
    project.canvas.ratio = canvas_ratio
    project.exportSettings.outputDir = str(_project_dir(pid))
    _save_project(project)
    return project

def get_project(project_id: str) -> Project | None:
    f = _project_file(project_id)
    if not f.exists():
        return None
    return Project(**json.loads(f.read_text(encoding="utf-8")))

def update_project(project_id: str, data: dict) -> Project | None:
    p = get_project(project_id)
    if not p:
        return None
    updated = p.model_copy(update=data)
    updated.updated_at = datetime.now().isoformat()
    _save_project(updated)
    return updated

def list_projects() -> list[dict]:
    results = []
    for d in sorted(PROJECTS_DIR.iterdir(), key=lambda x: x.name, reverse=True):
        if d.is_dir() and (d / "project.json").exists():
            p = json.loads((d / "project.json").read_text(encoding="utf-8"))
            results.append({"id": p["id"], "name": p["name"], "created_at": p.get("created_at", "")})
    return results

def delete_project(project_id: str) -> bool:
    d = _project_dir(project_id)
    if not d.exists():
        return False
    import shutil
    shutil.rmtree(d)
    return True

def _save_project(project: Project):
    d = _project_dir(project.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "assets").mkdir(exist_ok=True)
    _project_file(project.id).write_text(project.model_dump_json(indent=2), encoding="utf-8")
```

- [ ] **Step 2: 验证服务可用**

Run:
```bash
cd backend && python -c "
from services.project_service import create_project, list_projects
p = create_project('测试项目', '9:16')
print(f'Created: {p.id}')
projects = list_projects()
print(f'Total projects: {len(projects)}')
for p in projects:
    print(f'  - {p[\"name\"]} ({p[\"id\"]})')
"
```

Expected: 打印创建的项目信息

---

### Task 4: 后端配音引擎

**Files:**
- Create: `backend/engines/__init__.py`
- Create: `backend/engines/voiceover.py`
- Modify: `backend/config.py` (确保 MANBO_API_KEY 已配置)

- [ ] **Step 1: 实现配音引擎**

```python
# backend/engines/voiceover.py
import re
import httpx
from pathlib import Path
from config import MANBO_API_KEY, MANBO_API_URL, MANBO_MAX_CHARS

def split_text(text: str, max_chars: int = MANBO_MAX_CHARS) -> list[str]:
    """按标点断句，每段不超过 max_chars 字符"""
    sentences = re.split(r'(?<=[。！？；\n])', text)
    chunks, current = [], ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if len(current) + len(s) <= max_chars:
            current += s
        else:
            if current:
                chunks.append(current)
            current = s if len(s) <= max_chars else ""
    if current:
        chunks.append(current)
    return chunks if chunks else [text[:max_chars]]

def synthesize_voice(text: str, speed: int = 0, fmt: str = "mp3") -> bytes:
    """调用曼波 VIP API 合成单段文本"""
    params = {"text": text, "key": MANBO_API_KEY, "speed": str(speed), "format": fmt}
    headers = {"Authorization": f"Bearer {MANBO_API_KEY}"}
    resp = httpx.get(MANBO_API_URL, params=params, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 200:
        raise RuntimeError(f"TTS API error: {data.get('msg', 'unknown')}")
    mp3_url = data.get("mp3") or data.get("data", {}).get("mp3")
    if not mp3_url:
        raise RuntimeError("No mp3 URL in API response")
    audio_resp = httpx.get(mp3_url, timeout=60)
    audio_resp.raise_for_status()
    return audio_resp.content

def generate_voiceover(text: str, output_dir: Path, speed: int = 0) -> tuple[Path, float]:
    """对长文本分段合成，拼接保存，返回 (音频路径, 总时长秒数)"""
    chunks = split_text(text)
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_parts = []
    total_duration = 0.0
    for i, chunk in enumerate(chunks):
        data = synthesize_voice(chunk, speed=speed)
        part_path = output_dir / f"voice_part_{i:03d}.mp3"
        part_path.write_bytes(data)
        audio_parts.append(part_path)
        estimated = len(chunk) * 0.25
        total_duration += estimated
    if len(audio_parts) == 1:
        final_path = output_dir / "voiceover.mp3"
        audio_parts[0].rename(final_path)
    else:
        final_path = output_dir / "voiceover.mp3"
        concat_list = output_dir / "concat_list.txt"
        concat_list.write_text("\n".join(f"file '{p.name}'" for p in audio_parts), encoding="utf-8")
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(final_path)],
            cwd=str(output_dir), capture_output=True, check=True
        )
    for p in audio_parts:
        if p != final_path and p.exists():
            p.unlink()
    return final_path, total_duration
```

- [ ] **Step 2: 验证配音引擎**

Run:
```bash
cd backend && python -c "
from engines.voiceover import split_text, synthesize_voice
text = '你好世界，这是一段测试文本。我们来验证配音API是否正常工作。'
chunks = split_text(text)
print(f'分段数: {len(chunks)}')
for i, c in enumerate(chunks):
    print(f'  段{i}: {c[:50]}...')
data = synthesize_voice(chunks[0])
print(f'合成成功, 音频大小: {len(data)} bytes')
"
```

Expected: 分段正常，合成返回音频字节流

---

### Task 5: 后端字幕引擎

**Files:**
- Create: `backend/engines/subtitle.py`

- [ ] **Step 1: 实现字幕引擎**

```python
# backend/engines/subtitle.py
import re

def text_to_sentences(text: str) -> list[str]:
    """按标点分句"""
    raw = re.split(r'(?<=[。！？；\n])', text)
    return [s.strip() for s in raw if s.strip()]

def sentences_to_srt(sentences: list[str], chars_per_sec: float = 4.0, gap: float = 0.3) -> str:
    """根据字数估算时长，生成 SRT 内容"""
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
    """解析 SRT 为字幕列表"""
    import re
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
    """输入文案 → 返回 (字幕列表, SRT内容, 总时长)"""
    sentences = text_to_sentences(text)
    srt = sentences_to_srt(sentences)
    subs = srt_to_subtitles(srt)
    total_duration = subs[-1]["end"] if subs else 0.0
    return subs, srt, total_duration
```

- [ ] **Step 2: 验证字幕引擎**

Run:
```bash
cd backend && python -c "
from engines.subtitle import generate_subtitles
text = '第一句话。第二句话很长很长，用来测试时长估算是否合理。第三句收尾。'
subs, srt, duration = generate_subtitles(text)
print(f'字幕条数: {len(subs)}, 总时长: {duration:.1f}s')
print('SRT 预览:')
print(srt[:300])
"
```

Expected: 输出 3 条字幕，SRT 格式正确

---

### Task 6: 后端剪映草稿适配器

**Files:**
- Create: `backend/adapters/__init__.py`
- Create: `backend/adapters/jianying.py`

- [ ] **Step 1: 实现剪映草稿适配器**

```python
# backend/adapters/jianying.py
from pathlib import Path
from pyjianyingdraft import ScriptFile, VideoSegment, AudioSegment, TextSegment, DraftFolder, trange

def generate_jianying_draft(project: dict) -> Path:
    """从 project.json 字典生成剪映草稿文件夹"""
    canvas = project["canvas"]
    script = ScriptFile(resolution=(canvas["width"], canvas["height"]))

    video_duration_us = _duration_to_us(project.get("_totalDuration", 30.0))

    # 1. 主图轨道
    segments = project.get("segments", [])
    if segments:
        main_track = script.add_track("video")
        for seg in segments:
            seg_end = seg.get("end", video_duration_us / 1_000_000)
            seg_start = seg.get("start", 0)
            t = seg.get("transform", {})
            v = VideoSegment(
                seg["assetPath"],
                target_timerange=trange(f"{seg_start}s", f"{seg_end - seg_start}s"),
            )
            main_track.add_segment(v)

    # 2. BGM 轨道
    bgm = project.get("audio", {}).get("bgm", {})
    if bgm.get("file"):
        bgm_track = script.add_track("audio")
        a = AudioSegment(bgm["file"], target_timerange=trange("0s", f"{video_duration_us / 1_000_000}s"))
        bgm_track.add_segment(a)

    # 3. 配音轨道
    voiceover_file = project.get("audio", {}).get("voiceover", {}).get("file", "")
    if voiceover_file:
        voice_track = script.add_track("audio")
        va = AudioSegment(voiceover_file)
        voice_track.add_segment(va)

    # 4. 字幕轨道（从 SRT）
    srt_path = project.get("_srtPath", "")
    if srt_path and Path(srt_path).exists():
        text_track = script.add_track("text")
        script.import_srt(srt_path, target_track=text_track)

    # 5. 标题文字
    overlays = project.get("overlays", {})
    title_cfg = overlays.get("title", {})
    if title_cfg.get("enabled") and title_cfg.get("text"):
        title_track = script.add_track("text")
        ts = TextSegment(title_cfg["text"], target_timerange=trange("0s", f"{video_duration_us / 1_000_000}s"))
        title_track.add_segment(ts)

    # 6. 水印文字
    watermark_cfg = overlays.get("watermark", {})
    if watermark_cfg.get("enabled") and watermark_cfg.get("text"):
        wm_track = script.add_track("text")
        ws = TextSegment(watermark_cfg["text"], target_timerange=trange("0s", f"{video_duration_us / 1_000_000}s"))
        wm_track.add_segment(ws)

    # 7. 输出草稿
    output_dir = Path(project.get("exportSettings", {}).get("outputDir", "projects/temp"))
    draft_dir = output_dir / "jianying_draft"
    draft = DraftFolder.create_new(project.get("name", "video"), output_dir=draft_dir)
    draft.save(script)
    return draft_dir

def _duration_to_us(seconds: float) -> int:
    return int(seconds * 1_000_000)
```

- [ ] **Step 2: 验证导入**

Run: `cd backend && python -c "from adapters.jianying import generate_jianying_draft; print('Adapter imported OK')"`

Expected: 无错误输出

---

### Task 7: 后端 API 路由

**Files:**
- Create: `backend/routers/__init__.py`
- Create: `backend/routers/project.py`
- Create: `backend/routers/voiceover.py`
- Create: `backend/routers/export.py`
- Create: `backend/routers/assets.py`
- Modify: `backend/main.py` (注册路由)

- [ ] **Step 1: 项目路由**

```python
# backend/routers/project.py
from fastapi import APIRouter, HTTPException
from models.project import Project
from services.project_service import create_project, get_project, update_project, list_projects, delete_project

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.post("")
def create(data: dict):
    p = create_project(data.get("name", "未命名"), data.get("canvas_ratio", "9:16"))
    return p.model_dump()

@router.get("")
def list_all():
    return list_projects()

@router.get("/{project_id}")
def get_one(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p.model_dump()

@router.put("/{project_id}")
def update(project_id: str, data: dict):
    p = update_project(project_id, data)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p.model_dump()

@router.delete("/{project_id}")
def delete(project_id: str):
    if not delete_project(project_id):
        raise HTTPException(404, "项目不存在")
    return {"ok": True}
```

- [ ] **Step 2: 素材路由**

```python
# backend/routers/assets.py
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from services.project_service import get_project, _project_dir

router = APIRouter(prefix="/api/projects/{project_id}/assets", tags=["assets"])

@router.post("")
async def upload_asset(project_id: str, file: UploadFile = File(...)):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    proj_dir = _project_dir(project_id)
    assets_dir = proj_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    dest = assets_dir / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"filename": file.filename, "path": str(dest)}
```

- [ ] **Step 3: 配音路由**

```python
# backend/routers/voiceover.py
from pathlib import Path
from fastapi import APIRouter, HTTPException
from services.project_service import get_project, update_project, _project_dir
from engines.voiceover import generate_voiceover
from engines.subtitle import generate_subtitles

router = APIRouter(prefix="/api/projects/{project_id}/voiceover", tags=["voiceover"])

@router.post("")
def generate(project_id: str, data: dict):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    text = data.get("text", "")
    if not text:
        raise HTTPException(400, "文案不能为空")
    speed = data.get("speed", 0)
    proj_dir = _project_dir(project_id)
    audio_path, duration = generate_voiceover(text, proj_dir, speed=speed)
    # 生成字幕
    subs, srt, sub_duration = generate_subtitles(text)
    srt_path = proj_dir / "subtitles.srt"
    srt_path.write_text(srt, encoding="utf-8")
    total_duration = max(duration, sub_duration)
    # 更新项目
    updated = update_project(project_id, {
        "audio": {
            **p.audio.model_dump(),
            "voiceover": {**p.audio.voiceover.model_dump(), "file": str(audio_path)}
        },
        "subtitles": [{
            "id": f"sub_{s['index']:03d}",
            "text": s["text"],
            "start": s["start"],
            "end": s["end"],
            "style": {"fontSize": 36, "color": "#ffffff", "strokeColor": "#000000", "strokeWidth": 2, "position": "bottom"}
        } for s in subs],
        "_totalDuration": total_duration,
        "_srtPath": str(srt_path)
    })
    return {
        "audioPath": str(audio_path),
        "duration": total_duration,
        "subtitleCount": len(subs),
        "subtitles": updated.subtitles if updated else []
    }
```

- [ ] **Step 4: 导出路由**

```python
# backend/routers/export.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from services.project_service import get_project, _project_dir
from adapters.jianying import generate_jianying_draft
import zipfile
import io

router = APIRouter(prefix="/api/projects/{project_id}/export", tags=["export"])

@router.post("/jianying")
def export_jianying(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    proj_dict = p.model_dump()
    try:
        draft_dir = generate_jianying_draft(proj_dict)
        # 打包成 zip 返回
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in draft_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(draft_dir.parent))
        buf.seek(0)
        from fastapi.responses import StreamingResponse
        return StreamingResponse(buf, media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={p.name}_jianying_draft.zip"})
    except Exception as e:
        raise HTTPException(500, f"导出失败: {str(e)}")
```

- [ ] **Step 5: 注册路由到 main.py**

```python
# backend/main.py — 在 app 定义后添加:
from routers import project, voiceover, export, assets
app.include_router(project.router)
app.include_router(voiceover.router)
app.include_router(export.router)
app.include_router(assets.router)
```

- [ ] **Step 6: 验证所有路由**

Run: `cd backend && python -m uvicorn main:app --reload --port 8000`

然后测试:
```bash
# 创建项目
curl -X POST http://localhost:8000/api/projects -H "Content-Type: application/json" -d '{"name":"测试","canvas_ratio":"9:16"}'

# 列出项目
curl http://localhost:8000/api/projects
```

Expected: 返回创建的项目 JSON 和项目列表

---

### Task 8: 前端项目初始化

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.app.json`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/styles/globals.css`

- [ ] **Step 1: 创建 package.json 并安装依赖**

```json
{
  "name": "video-forge-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0",
    "framer-motion": "^11.11.0",
    "@phosphor-icons/react": "^2.1.7"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "typescript": "~5.6.2",
    "vite": "^6.0.0",
    "tailwindcss": "^3.4.15",
    "postcss": "^8.4.49",
    "autoprefixer": "^10.4.20"
  }
}
```

Run: `cd frontend && npm install`

- [ ] **Step 2: 创建配置文件**

```javascript
// frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' }
  }
})
```

```javascript
// frontend/tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Geist', 'system-ui', 'sans-serif'],
        mono: ['Geist Mono', 'monospace'],
      },
      colors: {
        accent: { DEFAULT: '#10b981', 500: '#10b981', 600: '#059669' },
      },
    },
  },
  plugins: [],
}
```

```javascript
// frontend/postcss.config.js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [ ] **Step 3: 创建 index.html 和入口文件**

```html
<!-- frontend/index.html -->
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>VideoForge</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap" rel="stylesheet" />
  </head>
  <body class="bg-zinc-950 text-zinc-100 antialiased">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

```tsx
// frontend/src/main.tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles/globals.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>
)
```

```css
/* frontend/src/styles/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  * { @apply border-zinc-800; }
  body { @apply bg-zinc-950 text-zinc-100; }
}
```

- [ ] **Step 4: 验证前端启动**

Run: `cd frontend && npm run dev`

Expected: Vite 启动在 `http://localhost:5173`，浏览器打开显示空白页面但无错误

---

### Task 9: 前端核心基础设施

**Files:**
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/hooks/useProject.ts`

- [ ] **Step 1: App 路由入口**

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import Editor from './pages/Editor'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/editor/:id" element={<Editor />} />
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 2: API 客户端**

```tsx
// frontend/src/lib/api.ts
const BASE = '/api'

async function request<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  })
  if (!res.ok) {
    const e = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(e.detail || e.msg || 'Request failed')
  }
  return res.json()
}

export const api = {
  createProject: (name: string, canvasRatio = '9:16') =>
    request<any>('/projects', { method: 'POST', body: JSON.stringify({ name, canvas_ratio: canvasRatio }) }),
  getProject: (id: string) => request<any>(`/projects/${id}`),
  updateProject: (id: string, data: any) =>
    request<any>(`/projects/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  listProjects: () => request<any[]>('/projects'),
  uploadAsset: (projectId: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch(`${BASE}/projects/${projectId}/assets`, { method: 'POST', body: fd }).then(r => r.json())
  },
  generateVoiceover: (projectId: string, text: string, speed = 0) =>
    request<any>(`/projects/${projectId}/voiceover`, { method: 'POST', body: JSON.stringify({ text, speed }) }),
  exportJianying: (projectId: string) =>
    fetch(`${BASE}/projects/${projectId}/export/jianying`, { method: 'POST' }).then(async r => {
      if (!r.ok) throw new Error('Export failed')
      const blob = await r.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'jianying_draft.zip'; a.click()
      URL.revokeObjectURL(url)
    }),
}
```

- [ ] **Step 3: 项目 Hook**

```tsx
// frontend/src/hooks/useProject.ts
import { useState, useEffect, useCallback } from 'react'
import { api } from '../lib/api'

export function useProject(id: string) {
  const [project, setProject] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const p = await api.getProject(id)
      setProject(p)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  const update = useCallback(async (data: any) => {
    const updated = await api.updateProject(id, data)
    setProject(updated)
    return updated
  }, [id])

  return { project, loading, reload: load, update }
}
```

- [ ] **Step 4: 验证前端基础设施**

在 `App.tsx` 中临时添加测试代码,确认 API 调用正常:
```tsx
// 临时测试 — 在 Home 组件中
import { api } from '../lib/api'
// ...
useEffect(() => {
  api.listProjects().then(console.log).catch(console.error)
}, [])
```

Expected: 浏览器控制台输出项目列表

---

### Task 10: 前端首页

**Files:**
- Create: `frontend/src/pages/Home.tsx`

- [ ] **Step 1: 实现首页**

```tsx
// frontend/src/pages/Home.tsx
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Plus, FilmSlate, Clock } from '@phosphor-icons/react'
import { api } from '../lib/api'

export default function Home() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<any[]>([])
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    api.listProjects().then(setProjects).catch(console.error)
  }, [])

  const handleCreate = async () => {
    if (!name.trim()) return
    setCreating(true)
    try {
      const p = await api.createProject(name.trim())
      navigate(`/editor/${p.id}`)
    } catch (e) {
      console.error(e)
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="min-h-[100dvh] flex flex-col items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="text-center mb-10"
      >
        <FilmSlate size={48} className="text-zinc-400 mx-auto mb-4" weight="duotone" />
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-100">VideoForge</h1>
        <p className="text-zinc-500 mt-2 text-sm">自媒体视频自动化工作台</p>
      </motion.div>

      <div className="w-full max-w-md">
        <div className="flex gap-2">
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleCreate()}
            placeholder="输入项目名称..."
            className="flex-1 bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-emerald-500/50 transition-colors"
          />
          <button
            disabled={!name.trim() || creating}
            onClick={handleCreate}
            className="bg-emerald-500 hover:bg-emerald-600 disabled:bg-zinc-800 disabled:text-zinc-600 text-white rounded-xl px-5 py-3 flex items-center gap-2 text-sm font-medium transition-all active:scale-[0.98]"
          >
            <Plus size={18} weight="bold" />
            新建
          </button>
        </div>

        {projects.length > 0 && (
          <div className="mt-8">
            <h2 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3">最近项目</h2>
            <div className="space-y-1">
              {projects.slice(0, 5).map(p => (
                <button
                  key={p.id}
                  onClick={() => navigate(`/editor/${p.id}`)}
                  className="w-full text-left flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-zinc-900 transition-colors group"
                >
                  <Clock size={18} className="text-zinc-600 group-hover:text-zinc-400" />
                  <span className="text-sm text-zinc-300 group-hover:text-zinc-100">{p.name}</span>
                  <span className="ml-auto text-xs text-zinc-600">{p.created_at?.slice(0, 10)}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 验证首页**

Run: `cd frontend && npm run dev`

浏览器打开 `http://localhost:5173`，输入项目名点击新建，应跳转到 Editor 页（目前 404，下一步实现）

---

### Task 11: 前端编辑器页面 — 布局与面板

**Files:**
- Create: `frontend/src/pages/Editor.tsx`
- Create: `frontend/src/components/panels/AssetPanel.tsx`
- Create: `frontend/src/components/panels/ScriptPanel.tsx`
- Create: `frontend/src/components/panels/AudioPanel.tsx`
- Create: `frontend/src/components/panels/OverlayPanel.tsx`
- Create: `frontend/src/components/canvas/CanvasPreview.tsx`
- Create: `frontend/src/components/layout/TopBar.tsx`

- [ ] **Step 1: TopBar**

```tsx
// frontend/src/components/layout/TopBar.tsx
import { FilmSlate, ExportSquare } from '@phosphor-icons/react'

interface TopBarProps {
  projectName: string
  onExport: () => void
  exporting: boolean
}

export default function TopBar({ projectName, onExport, exporting }: TopBarProps) {
  return (
    <header className="h-14 border-b border-zinc-800 flex items-center justify-between px-4 shrink-0">
      <div className="flex items-center gap-3">
        <FilmSlate size={20} className="text-zinc-500" weight="duotone" />
        <span className="text-sm font-medium text-zinc-300 truncate max-w-[200px]">{projectName}</span>
      </div>
      <button
        onClick={onExport}
        disabled={exporting}
        className="bg-emerald-500 hover:bg-emerald-600 disabled:bg-zinc-800 disabled:text-zinc-600 text-white rounded-lg px-4 py-1.5 text-xs font-medium flex items-center gap-2 transition-all active:scale-[0.98]"
      >
        <ExportSquare size={14} weight="bold" />
        {exporting ? '导出中...' : '导出剪映草稿'}
      </button>
    </header>
  )
}
```

- [ ] **Step 2: AssetPanel**

```tsx
// frontend/src/components/panels/AssetPanel.tsx
import { useCallback } from 'react'
import { Image, Trash } from '@phosphor-icons/react'
import { api } from '../../lib/api'

interface Props {
  projectId: string
  assetPath: string | null
  onAssetChange: (path: string) => void
}

export default function AssetPanel({ projectId, assetPath, onAssetChange }: Props) {
  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file && file.type.startsWith('image/')) {
      const result = await api.uploadAsset(projectId, file)
      onAssetChange(result.path)
    }
  }, [projectId, onAssetChange])

  const handleSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      const result = await api.uploadAsset(projectId, file)
      onAssetChange(result.path)
    }
  }, [projectId, onAssetChange])

  return (
    <div className="bg-white rounded-[2rem] p-5 shadow-[0_20px_40px_-15px_rgba(0,0,0,0.05)]">
      <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-3">封面图</h3>
      {assetPath ? (
        <div className="relative group">
          <img src={`/${assetPath}`} alt="封面" className="w-full aspect-[9/16] object-cover rounded-xl" />
          <button
            onClick={() => onAssetChange('')}
            className="absolute top-2 right-2 bg-red-500 text-white p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <Trash size={14} weight="bold" />
          </button>
        </div>
      ) : (
        <label
          onDrop={handleDrop}
          onDragOver={e => e.preventDefault()}
          className="flex flex-col items-center justify-center aspect-[9/16] border-2 border-dashed border-zinc-200 rounded-xl cursor-pointer hover:border-emerald-500/50 transition-colors group"
        >
          <input type="file" accept="image/*" onChange={handleSelect} className="hidden" />
          <Image size={32} className="text-zinc-300 group-hover:text-emerald-400 mb-2" />
          <span className="text-xs text-zinc-400">拖拽或点击上传</span>
          <span className="text-[10px] text-zinc-300 mt-0.5">PNG, JPG, WEBP</span>
        </label>
      )}
    </div>
  )
}
```

- [ ] **Step 3: ScriptPanel**

```tsx
// frontend/src/components/panels/ScriptPanel.tsx
import { useState } from 'react'
import { Microphone, Check, Spinner } from '@phosphor-icons/react'

interface Props {
  onGenerate: (text: string) => Promise<void>
  generating: boolean
  generated: boolean
  subtitleCount: number
  duration: number
}

export default function ScriptPanel({ onGenerate, generating, generated, subtitleCount, duration }: Props) {
  const [text, setText] = useState('')

  return (
    <div className="bg-white rounded-[2rem] p-5 shadow-[0_20px_40px_-15px_rgba(0,0,0,0.05)]">
      <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-3">文案 & 配音</h3>
      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder="输入旁白文案..."
        rows={5}
        className="w-full bg-zinc-50 border border-zinc-100 rounded-xl p-3 text-sm text-zinc-800 placeholder-zinc-400 resize-none outline-none focus:border-emerald-500/50 transition-colors"
      />
      <div className="flex items-center justify-between mt-2">
        <span className="text-[11px] text-zinc-400">{text.length} 字</span>
        <button
          disabled={!text.trim() || generating}
          onClick={() => onGenerate(text)}
          className="bg-zinc-900 hover:bg-zinc-800 disabled:bg-zinc-200 disabled:text-zinc-400 text-white rounded-lg px-3 py-1.5 text-xs font-medium flex items-center gap-1.5 transition-all active:scale-[0.98]"
        >
          {generating ? (
            <Spinner size={14} className="animate-spin" weight="bold" />
          ) : generated ? (
            <Check size={14} weight="bold" className="text-emerald-400" />
          ) : (
            <Microphone size={14} weight="bold" />
          )}
          {generating ? '生成中...' : generated ? '重新生成' : '生成配音'}
        </button>
      </div>
      {generated && (
        <div className="mt-2 flex gap-3 text-[11px] text-zinc-400">
          <span>时长 {duration.toFixed(1)}s</span>
          <span>字幕 {subtitleCount} 条</span>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: AudioPanel**

```tsx
// frontend/src/components/panels/AudioPanel.tsx
import { MusicNote } from '@phosphor-icons/react'

interface Props {
  bgmPath: string
  bgmVolume: number
  onBgmChange: (path: string) => void
  onVolumeChange: (v: number) => void
}

export default function AudioPanel({ bgmPath, bgmVolume, onBgmChange, onVolumeChange }: Props) {
  return (
    <div className="bg-white rounded-[2rem] p-5 shadow-[0_20px_40px_-15px_rgba(0,0,0,0.05)]">
      <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-3">背景音乐</h3>
      <label className="flex items-center gap-2 cursor-pointer">
        <div className="bg-zinc-100 rounded-lg px-3 py-1.5 text-xs text-zinc-500 hover:bg-zinc-200 transition-colors flex items-center gap-1.5">
          <MusicNote size={14} />
          {bgmPath ? '已选择' : '选择文件'}
        </div>
        <input type="file" accept="audio/*" onChange={async (e) => {
          const file = e.target.files?.[0]
          if (file) onBgmChange(file.name)
        }} className="hidden" />
      </label>
      <div className="mt-3 flex items-center gap-2">
        <span className="text-[11px] text-zinc-400 w-8">音量</span>
        <input
          type="range" min="0" max="100" value={bgmVolume * 100}
          onChange={e => onVolumeChange(Number(e.target.value) / 100)}
          className="flex-1 accent-emerald-500 h-1"
        />
        <span className="text-[11px] text-zinc-400 w-8 text-right">{Math.round(bgmVolume * 100)}%</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: OverlayPanel**

```tsx
// frontend/src/components/panels/OverlayPanel.tsx
import { Toggle } from '../ui/Toggle'

interface Props {
  title: { text: string; enabled: boolean; position: string; fontSize: number; color: string }
  watermark: { text: string; enabled: boolean; position: string; fontSize: number; color: string }
  onTitleChange: (t: any) => void
  onWatermarkChange: (w: any) => void
}

export default function OverlayPanel({ title, watermark, onTitleChange, onWatermarkChange }: Props) {
  return (
    <div className="bg-white rounded-[2rem] p-5 shadow-[0_20px_40px_-15px_rgba(0,0,0,0.05)]">
      <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-3">标题 & 水印</h3>

      <div className="mb-3">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs text-zinc-500">标题文字</span>
          <Toggle checked={title.enabled} onChange={v => onTitleChange({ ...title, enabled: v })} />
        </div>
        <input
          value={title.text}
          onChange={e => onTitleChange({ ...title, text: e.target.value, enabled: true })}
          placeholder="输入标题..."
          className="w-full bg-zinc-50 border border-zinc-100 rounded-lg px-3 py-1.5 text-xs text-zinc-800 placeholder-zinc-400 outline-none focus:border-emerald-500/50 transition-colors"
          disabled={!title.enabled}
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs text-zinc-500">水印</span>
          <Toggle checked={watermark.enabled} onChange={v => onWatermarkChange({ ...watermark, enabled: v })} />
        </div>
        <input
          value={watermark.text}
          onChange={e => onWatermarkChange({ ...watermark, text: e.target.value, enabled: true })}
          placeholder="@你的ID..."
          className="w-full bg-zinc-50 border border-zinc-100 rounded-lg px-3 py-1.5 text-xs text-zinc-800 placeholder-zinc-400 outline-none focus:border-emerald-500/50 transition-colors"
          disabled={!watermark.enabled}
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 6: CanvasPreview**

```tsx
// frontend/src/components/canvas/CanvasPreview.tsx
import { useRef, useEffect } from 'react'

interface Props {
  imagePath: string | null
  scale: number
  fit: string
  canvasW: number
  canvasH: number
  subtitles: any[]
}

export default function CanvasPreview({ imagePath, scale, fit, canvasW, canvasH, subtitles }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const previewW = 280
  const previewH = (previewW / canvasW) * canvasH

  useEffect(() => {
    const ctx = canvasRef.current?.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, previewW, previewH)
    // 背景
    ctx.fillStyle = '#000000'
    ctx.fillRect(0, 0, previewW, previewH)
    // 图片
    if (imagePath) {
      const img = new Image()
      img.onload = () => {
        ctx.save()
        const iw = img.width * scale
        const ih = img.height * scale
        const x = (previewW - iw) / 2
        const y = (previewH - ih) / 2
        ctx.drawImage(img, x, y, iw, ih)
        ctx.restore()
        // 字幕位置指示
        if (subtitles.length > 0) {
          ctx.fillStyle = 'rgba(255,255,255,0.15)'
          ctx.fillRect(20, previewH - 60, previewW - 40, 40)
          ctx.fillStyle = 'rgba(255,255,255,0.4)'
          ctx.font = '11px Geist, sans-serif'
          ctx.textAlign = 'center'
          ctx.fillText('字幕区域', previewW / 2, previewH - 35)
        }
      }
      img.src = `/${imagePath}`
    }
  }, [imagePath, scale, previewW, previewH, subtitles])

  return (
    <div className="bg-white rounded-[2rem] p-6 shadow-[0_20px_40px_-15px_rgba(0,0,0,0.05)]">
      <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider mb-4">画布预览</h3>
      <div className="flex justify-center">
        <canvas
          ref={canvasRef}
          width={previewW}
          height={previewH}
          className="rounded-lg border border-zinc-100"
        />
      </div>
      <div className="mt-4 space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-zinc-400 w-10">缩放</span>
          <span className="text-[11px] text-zinc-500">{Math.round(scale * 100)}%</span>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 7: Editor 页面 — 组装所有面板**

```tsx
// frontend/src/pages/Editor.tsx
import { useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useProject } from '../hooks/useProject'
import { api } from '../lib/api'
import TopBar from '../components/layout/TopBar'
import AssetPanel from '../components/panels/AssetPanel'
import ScriptPanel from '../components/panels/ScriptPanel'
import AudioPanel from '../components/panels/AudioPanel'
import OverlayPanel from '../components/panels/OverlayPanel'
import CanvasPreview from '../components/canvas/CanvasPreview'

export default function Editor() {
  const { id } = useParams<{ id: string }>()
  const { project, loading, update } = useProject(id!)
  const [generating, setGenerating] = useState(false)
  const [generated, setGenerated] = useState(false)
  const [duration, setDuration] = useState(0)
  const [subtitleCount, setSubtitleCount] = useState(0)
  const [exporting, setExporting] = useState(false)

  const handleGenerate = useCallback(async (text: string) => {
    setGenerating(true)
    try {
      const result = await api.generateVoiceover(id!, text)
      setDuration(result.duration)
      setSubtitleCount(result.subtitleCount)
      setGenerated(true)
      await update({ subtitles: result.subtitles })
    } catch (e: any) {
      alert('配音生成失败: ' + e.message)
    } finally {
      setGenerating(false)
    }
  }, [id, update])

  const handleExport = useCallback(async () => {
    setExporting(true)
    try {
      await api.exportJianying(id!)
    } catch (e: any) {
      alert('导出失败: ' + e.message)
    } finally {
      setExporting(false)
    }
  }, [id])

  const handleAssetChange = useCallback(async (path: string) => {
    const seg = path ? [{
      id: 'seg_main',
      assetPath: path,
      type: 'image',
      start: 0,
      end: duration || 30,
      transform: { x: 0.5, y: 0.5, scale: 0.85, rotation: 0, fit: 'contain' }
    }] : []
    await update({ segments: seg })
  }, [duration, update])

  if (loading) {
    return (
      <div className="min-h-[100dvh] flex items-center justify-center">
        <div className="animate-pulse text-zinc-500 text-sm">加载中...</div>
      </div>
    )
  }
  if (!project) return <div className="min-h-[100dvh] flex items-center justify-center text-zinc-500">项目不存在</div>

  return (
    <div className="min-h-[100dvh] flex flex-col">
      <TopBar projectName={project.name} onExport={handleExport} exporting={exporting} />
      <div className="flex-1 flex overflow-hidden">
        {/* 左侧面板 */}
        <div className="w-[340px] shrink-0 p-4 space-y-3 overflow-y-auto bg-zinc-100/50">
          <AssetPanel
            projectId={id!}
            assetPath={project.segments?.[0]?.assetPath || null}
            onAssetChange={handleAssetChange}
          />
          <ScriptPanel
            onGenerate={handleGenerate}
            generating={generating}
            generated={generated}
            subtitleCount={subtitleCount}
            duration={duration}
          />
          <AudioPanel
            bgmPath={project.audio?.bgm?.file || ''}
            bgmVolume={project.audio?.bgm?.volume || 0.3}
            onBgmChange={async (path) => {
              await update({ audio: { ...project.audio, bgm: { ...project.audio.bgm, file: path } } })
            }}
            onVolumeChange={async (v) => {
              await update({ audio: { ...project.audio, bgm: { ...project.audio.bgm, volume: v } } })
            }}
          />
          <OverlayPanel
            title={project.overlays?.title || {}}
            watermark={project.overlays?.watermark || {}}
            onTitleChange={async (t) => await update({ overlays: { ...project.overlays, title: t } })}
            onWatermarkChange={async (w) => await update({ overlays: { ...project.overlays, watermark: w } })}
          />
        </div>
        {/* 右侧预览区 */}
        <div className="flex-1 p-4 overflow-y-auto">
          <CanvasPreview
            imagePath={project.segments?.[0]?.assetPath || null}
            scale={project.segments?.[0]?.transform?.scale || 0.85}
            fit={project.segments?.[0]?.transform?.fit || 'contain'}
            canvasW={project.canvas?.width || 1080}
            canvasH={project.canvas?.height || 1920}
            subtitles={project.subtitles || []}
          />
        </div>
      </div>
    </div>
  )
}
```

---

### Task 12: 前端 UI 基础组件

**Files:**
- Create: `frontend/src/components/ui/Toggle.tsx`
- Create: `frontend/src/components/ui/Slider.tsx`
- Create: `frontend/src/components/ui/ProgressBar.tsx`

- [ ] **Step 1: Toggle**

```tsx
// frontend/src/components/ui/Toggle.tsx
import { motion } from 'framer-motion'

interface Props {
  checked: boolean
  onChange: (v: boolean) => void
}

export function Toggle({ checked, onChange }: Props) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={`w-8 h-4.5 rounded-full p-0.5 transition-colors ${checked ? 'bg-emerald-500' : 'bg-zinc-200'}`}
    >
      <motion.div
        animate={{ x: checked ? 14 : 0 }}
        transition={{ type: 'spring', stiffness: 500, damping: 30 }}
        className="w-3.5 h-3.5 bg-white rounded-full shadow-sm"
      />
    </button>
  )
}
```

- [ ] **Step 2: 验证所有页面**

Run: `cd frontend && npm run dev`

完成以下操作验证：
1. 首页显示 → 输入项目名 → 创建跳转
2. 编辑器加载 → 上传图片
3. 输入文案 → 生成配音（需要后端运行）
4. 切换标题/水印开关

---

### Task 13: 模板系统

**Files:**
- Create: `templates/single_image_voiceover.json`

- [ ] **Step 1: 内置模板 JSON**

```json
{
  "id": "single_image_voiceover",
  "name": "单图贯穿旁白模板",
  "type": "workflow",
  "version": "0.1",
  "canvas": {
    "ratio": "9:16",
    "background": "#000000"
  },
  "segments": [
    {
      "type": "main_image",
      "durationRule": "full_video",
      "defaultTransform": {
        "x": 0.5,
        "y": 0.5,
        "scale": 0.85,
        "fit": "contain"
      }
    }
  ],
  "audio": {
    "voiceover": { "api": "manbo_vip", "speed": 0 },
    "bgm": { "volume": 0.3 }
  },
  "overlays": {
    "subtitle": { "position": "bottom" },
    "title": { "position": "top_center", "enabled": false },
    "watermark": { "position": "top_right", "enabled": false }
  }
}
```

- [ ] **Step 2: 验证模板可被项目引用**

Run:
```bash
cd backend && python -c "
import json
from models.template import Template
t = Template(**json.loads(open('../templates/single_image_voiceover.json', encoding='utf-8').read()))
print(f'Template: {t.name}, Canvas: {t.canvas[\"ratio\"]}')
"
```

Expected: `Template: 单图贯穿旁白模板, Canvas: 9:16`

---

### Task 14: 端到端验证

- [ ] **Step 1: 启动全栈**

Terminal 1: `cd backend && python -m uvicorn main:app --reload --port 8000`
Terminal 2: `cd frontend && npm run dev`

- [ ] **Step 2: 完整链路验证**

按以下顺序操作并确认每个步骤：

| 步骤 | 操作 | 验证点 |
|------|------|--------|
| 1 | 打开 `http://localhost:5173` | 首页正常渲染，Logo + 新建按钮可见 |
| 2 | 输入"测试" → 点新建 | 跳转到 `/editor/{id}`，编辑器正常加载 |
| 3 | 左侧素材面板 → 上传一张 PNG 图片 | 右侧画布显示图片预览 + 黑色背景 |
| 4 | 输入文案(≥50字) → 点"生成配音" | 按钮变 loading → 完成显示绿勾 + 时长 + 字幕条数 |
| 5 | BGM 面板 → 选择一个 mp3 文件 | 显示"已选择"，音量滑块可调 |
| 6 | 标题水印面板 → 开关打开 → 输入文字 | 开关动画正常，文字输入可用 |
| 7 | 点"导出剪映草稿" | 下载一个 zip 文件 |
| 8 | 解压 zip → 检查 `draft_content.json` | JSON 文件存在且可解析 |

---

### 完工标准

V0 视为完成当：
1. 上述 8 步端到端验证全部通过
2. 生成的 `draft_content.json` 可在剪映 5.x/6.x 中正常打开
3. 有基本的错误提示（配音失败、导出失败时有可见反馈）
4. 前后端分离部署，均可独立启动
