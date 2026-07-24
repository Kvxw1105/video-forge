"""Persistence and built-ins for Structure Profiles."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import re
from uuid import uuid4

from config import CONFIG_DIR
from models.structure_profile import (
    StructureProfile,
    StructureProfileSnapshot,
    snapshot_profile,
)


PROFILES_DIR = CONFIG_DIR / "structure_profiles"
_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


BUILTIN_PROFILES: tuple[dict, ...] = (
    {
        "id": "knowledge_explainer",
        "name": "知识口播",
        "description": "适合观点、方法和解释型口播；主体按语义聚类为多个画面。",
        "version": 1,
        "builtin": True,
        "blocks": [
            {"id": "hook", "type": "HOOK", "label": "开头钩子", "targetChars": 60,
             "guidance": "一句话说明值得继续看的原因。",
             "visualPolicy": {"style": "black_screen_text", "scenePolicy": "single_clip"}},
            {"id": "problem", "type": "PROBLEM", "label": "问题展开", "targetChars": 160,
             "guidance": "定义用户正在面对的问题。",
             "visualPolicy": {"style": "cinematic_images", "scenePolicy": "split_by_semantic_cluster"}},
            {"id": "method", "type": "METHOD", "label": "方法拆解", "targetChars": 300,
             "guidance": "分步骤给出可执行的方法。",
             "visualPolicy": {"style": "diagram_or_steps", "scenePolicy": "one_scene_per_step"}},
            {"id": "cta", "type": "COMMENT_CTA", "label": "结尾互动", "required": False, "targetChars": 50,
             "guidance": "给出简短的评论或关注引导。",
             "visualPolicy": {"style": "color_card", "scenePolicy": "single_clip"}},
        ],
    },
    {
        "id": "story_narrative",
        "name": "故事叙事",
        "description": "适合案例、人物经历和情绪递进的短视频故事。",
        "version": 1,
        "builtin": True,
        "blocks": [
            {"id": "hook", "type": "HOOK", "label": "悬念开场", "targetChars": 70,
             "guidance": "给出冲突、反差或未解问题。",
             "visualPolicy": {"style": "black_screen_text", "scenePolicy": "single_clip"}},
            {"id": "story", "type": "STORY", "label": "主体故事", "targetChars": 500,
             "guidance": "按事件推进叙事，保留因果和情绪变化。",
             "visualPolicy": {"style": "cinematic_images", "scenePolicy": "split_by_semantic_cluster"}},
            {"id": "judgment", "type": "JUDGMENT", "label": "观点落点", "targetChars": 140,
             "guidance": "说明故事带来的判断或启发。",
             "visualPolicy": {"style": "color_card", "scenePolicy": "single_clip"}},
            {"id": "outro", "type": "SHORT_OUTRO", "label": "结尾", "required": False, "targetChars": 50,
             "guidance": "简短收束。",
             "visualPolicy": {"style": "black_screen_text", "scenePolicy": "single_clip"}},
        ],
    },
    {
        "id": "product_recommendation",
        "name": "种草推荐",
        "description": "适合产品体验、卖点说明和轻量转化内容。",
        "version": 1,
        "builtin": True,
        "blocks": [
            {"id": "hook", "type": "HOOK", "label": "需求钩子", "targetChars": 60,
             "guidance": "直接点出用户场景或痛点。",
             "visualPolicy": {"style": "black_screen_text", "scenePolicy": "single_clip"}},
            {"id": "problem", "type": "PROBLEM", "label": "使用场景", "targetChars": 120,
             "guidance": "描述用户原本的困扰或限制。",
             "visualPolicy": {"style": "cinematic_images", "scenePolicy": "split_by_semantic_cluster"}},
            {"id": "mechanism", "type": "MECHANISM", "label": "核心卖点", "targetChars": 260,
             "guidance": "解释关键特点和它解决问题的方式。",
             "visualPolicy": {"style": "cinematic_images", "scenePolicy": "split_by_semantic_cluster"}},
            {"id": "cta", "type": "CTA_TAG", "label": "行动引导", "required": False, "targetChars": 50,
             "guidance": "自然说明下一步行动。",
             "visualPolicy": {"style": "color_card", "scenePolicy": "single_clip"}},
        ],
    },
)


def _ensure_dir() -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def _file_for(profile_id: str) -> Path:
    return PROFILES_DIR / f"{profile_id}.json"


def _valid_profile_id(profile_id: str) -> bool:
    return bool(_PROFILE_ID_RE.fullmatch(profile_id))


def _builtin(profile_id: str) -> StructureProfile | None:
    for item in BUILTIN_PROFILES:
        if item["id"] == profile_id:
            return StructureProfile.model_validate(deepcopy(item))
    return None


def _load_user(profile_id: str) -> StructureProfile | None:
    if not _valid_profile_id(profile_id):
        return None
    file_path = _file_for(profile_id)
    if not file_path.exists():
        return None
    try:
        profile = StructureProfile.model_validate_json(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return None if profile.builtin else profile


def list_profiles() -> list[StructureProfile]:
    _ensure_dir()
    profiles = [StructureProfile.model_validate(deepcopy(item)) for item in BUILTIN_PROFILES]
    for file_path in sorted(PROFILES_DIR.glob("*.json")):
        profile = _load_user(file_path.stem)
        if profile is not None:
            profiles.append(profile)
    return profiles


def get_profile(profile_id: str) -> StructureProfile | None:
    builtin = _builtin(profile_id)
    return builtin if builtin is not None else _load_user(profile_id)


def _new_profile_id() -> str:
    return f"profile_{uuid4().hex[:12]}"


def _write(profile: StructureProfile) -> StructureProfile:
    _ensure_dir()
    target = _file_for(profile.id)
    temporary = target.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(profile.model_dump_json(indent=2))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return profile


def create_profile(data: dict) -> StructureProfile:
    requested_id = str(data.get("id") or "").strip()
    profile_id = requested_id or _new_profile_id()
    if not _valid_profile_id(profile_id):
        raise ValueError("structure profile id is invalid")
    if _builtin(profile_id) is not None or _load_user(profile_id) is not None:
        raise ValueError("structure profile id already exists")
    profile = StructureProfile.model_validate({**data, "id": profile_id, "builtin": False, "version": 1})
    return _write(profile)


def update_profile(profile_id: str, data: dict) -> StructureProfile | None:
    if _builtin(profile_id) is not None:
        raise PermissionError("built-in structure profiles are read-only")
    existing = _load_user(profile_id)
    if existing is None:
        return None
    if "id" in data and str(data["id"]) != profile_id:
        raise ValueError("structure profile id is immutable")
    candidate = StructureProfile.model_validate({
        **existing.model_dump(),
        **data,
        "id": profile_id,
        "builtin": False,
        "version": existing.version + 1,
    })
    return _write(candidate)


def delete_profile(profile_id: str) -> bool:
    if _builtin(profile_id) is not None:
        return False
    path = _file_for(profile_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def profile_snapshot(profile_id: str) -> StructureProfileSnapshot | None:
    profile = get_profile(profile_id)
    return snapshot_profile(profile) if profile is not None else None
