import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECTS_DIR = BASE_DIR / "projects"
TEMPLATES_DIR = BASE_DIR / "templates"
PROJECTS_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

MANBO_API_KEY = os.getenv("MANBO_API_KEY", "")  # Set via env var or TTS settings UI
MANBO_API_URL = "https://api.milorapart.top/apis/mbAIscvip"
MANBO_MAX_CHARS = 250

# CORS
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:5176",
    "http://localhost:5177",
    "http://localhost:5178",
    "http://localhost:5179",
]

# ── 剪映草稿目录自动检测 ──
_LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", ""))
_USERPROFILE_APP = Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Local"

_JIANYING_CANDIDATES = [
    _LOCALAPPDATA / "JianYingPro" / "User Data" / "Projects" / "com.lveditor.draft",
    _LOCALAPPDATA / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft",
    _USERPROFILE_APP / "JianYingPro" / "User Data" / "Projects" / "com.lveditor.draft",
    _USERPROFILE_APP / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft",
    _LOCALAPPDATA / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.cloud.draft_919662384391763",
]

JIANYING_DRAFT_DIR: Path | None = None
for _p in _JIANYING_CANDIDATES:
    if _p.exists():
        JIANYING_DRAFT_DIR = _p.resolve()
        break

# 用户可通过环境变量覆盖
_JIANYING_OVERRIDE = os.environ.get("JIANYING_DRAFT_DIR", "")
if _JIANYING_OVERRIDE:
    _ov = Path(_JIANYING_OVERRIDE)
    if _ov.exists():
        JIANYING_DRAFT_DIR = _ov.resolve()
