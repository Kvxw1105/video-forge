"""Private Skill and Director Pack registry for the local VideoForge workspace.

The registry stores declarative methods and pack manifests.  It never loads
user supplied Python/JS code: execution remains limited to the established
Recipe/Capability contracts owned by VideoForge.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.lab_runner.recipe_loader import RecipeValidationError, load_recipe_by_id
from agent.lab_runner.tool_registry import TOOL_SPECS

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 1
DEFAULT_RECIPE_ID = "structured-knowledge-video"
DEFAULT_CAPABILITIES = ["review_visual_scene_plan", "prepare_visual_generation_pack", "bind_scene_assets"]


class StudioValidationError(ValueError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _slug(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:56] or fallback


class DirectorStudioRegistry:
    """File-backed private registry with immutable Skill versions and Pack pins."""

    def __init__(self, root: str | Path | None = None, *, recipes_root: str | Path | None = None):
        configured = os.getenv("VIDEOFORGE_DIRECTOR_STUDIO_DIR")
        self.root = Path(root or configured or (REPO_ROOT / "config" / "director_studio"))
        self.skills_root = self.root / "skills"
        self.packs_root = self.root / "packs"
        self.recipes_root = Path(recipes_root or (REPO_ROOT / "agent" / "recipes"))
        self.skills_root.mkdir(parents=True, exist_ok=True)
        self.packs_root.mkdir(parents=True, exist_ok=True)
        self._ensure_seed_skill()

    # ---- Skills ---------------------------------------------------------
    def list_skills(self, *, include_disabled: bool = True) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for directory in sorted(path for path in self.skills_root.iterdir() if path.is_dir()):
            index = self._read(directory / "index.json", default=None)
            if not isinstance(index, dict):
                continue
            current = self._load_skill_version(directory.name, int(index.get("currentVersion") or 1))
            if current and (include_disabled or current.get("status") != "disabled"):
                rows.append(self._skill_summary(current))
        return sorted(rows, key=lambda item: item.get("updatedAt", ""), reverse=True)

    def get_skill(self, skill_id: str, version: int | None = None) -> dict[str, Any]:
        index = self._skill_index(skill_id)
        target = int(version or index["currentVersion"])
        skill = self._load_skill_version(skill_id, target)
        if skill is None:
            raise KeyError("skill_version_not_found")
        return deepcopy(skill)

    def import_gpt_draft(self, text: str, *, name: str | None = None) -> dict[str, Any]:
        source = str(text or "").strip()
        if len(source) < 24:
            raise StudioValidationError("请粘贴至少一段完整的 GPT 讨论成果。")
        if len(source) > 40_000:
            raise StudioValidationError("讨论成果过长，请先压缩到 40000 字符以内。")
        title = str(name or self._infer_name(source)).strip()
        skill_id = f"skill_{_slug(title, 'director-method')}_{uuid4().hex[:6]}"
        now = _now()
        skill = {
            "schemaVersion": SCHEMA_VERSION,
            "skillId": skill_id,
            "version": 1,
            "name": title[:120],
            "description": self._infer_description(source),
            "status": "draft",
            "source": {"type": "gpt_discussion", "text": source, "importedAt": now},
            "directives": self._infer_directives(source),
            "requiredCapabilities": self._infer_capabilities(source),
            "outputContract": {"type": "scene_plan", "fields": ["sceneId", "start", "end", "direction", "visualStyle"]},
            "createdAt": now,
            "updatedAt": now,
        }
        self._write_skill(skill, current=True)
        return deepcopy(skill)

    def update_skill(self, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_skill(skill_id)
        if current.get("status") == "published":
            # Published versions remain immutable. Editing creates an explicit draft version.
            current["version"] = int(current["version"]) + 1
            current["status"] = "draft"
            current["derivedFromVersion"] = int(current["version"]) - 1
        for key in ("name", "description", "directives", "requiredCapabilities", "outputContract"):
            if key in payload:
                current[key] = payload[key]
        current["updatedAt"] = _now()
        current["name"] = str(current.get("name") or "").strip()[:120]
        self._write_skill(current, current=True)
        return deepcopy(current)

    def validate_skill(self, skill_id: str, version: int | None = None) -> dict[str, Any]:
        skill = self.get_skill(skill_id, version)
        errors: list[str] = []
        if not skill.get("name"):
            errors.append("Skill 名称不能为空。")
        directives = skill.get("directives")
        if not isinstance(directives, dict) or not any(str(value).strip() for value in directives.values()):
            errors.append("至少需要一条导演规则。")
        capabilities = skill.get("requiredCapabilities")
        if not isinstance(capabilities, list) or not capabilities:
            errors.append("至少选择一个已注册能力。")
        else:
            unknown = sorted(str(item) for item in capabilities if item not in TOOL_SPECS)
            if unknown:
                errors.append(f"包含未注册能力：{', '.join(unknown)}")
        output = skill.get("outputContract")
        if not isinstance(output, dict) or output.get("type") != "scene_plan":
            errors.append("当前 V1 Skill 必须输出 scene_plan。")
        return {"ok": not errors, "skill": skill, "errors": errors, "capabilities": self.capabilities()}

    def trial_skill(self, skill_id: str, *, version: int | None = None, subtitles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        checked = self.validate_skill(skill_id, version)
        if not checked["ok"]:
            raise StudioValidationError("Skill 未通过校验，不能试跑。")
        timeline = subtitles or [
            {"id": "sub_001", "start": 0, "end": 2.8, "text": "先把信息拆成可理解的画面。"},
            {"id": "sub_002", "start": 2.8, "end": 6.2, "text": "再用统一的视觉规则组织镜头。"},
        ]
        return {"skill": checked["skill"], "scenePlan": self.build_scene_plan(timeline, [checked["skill"]], None), "mode": "synthetic_trial"}

    def publish_skill(self, skill_id: str) -> dict[str, Any]:
        checked = self.validate_skill(skill_id)
        if not checked["ok"]:
            raise StudioValidationError("；".join(checked["errors"]))
        skill = checked["skill"]
        skill["status"] = "published"
        skill["publishedAt"] = _now()
        skill["updatedAt"] = skill["publishedAt"]
        self._write_skill(skill, current=True)
        return deepcopy(skill)

    def set_skill_status(self, skill_id: str, status: str) -> dict[str, Any]:
        if status not in {"published", "disabled"}:
            raise StudioValidationError("Skill 状态只支持 published 或 disabled。")
        skill = self.get_skill(skill_id)
        if status == "published":
            checked = self.validate_skill(skill_id)
            if not checked["ok"]:
                raise StudioValidationError("；".join(checked["errors"]))
        skill["status"] = status
        skill["updatedAt"] = _now()
        self._write_skill(skill, current=True)
        return deepcopy(skill)

    def rollback_skill(self, skill_id: str, version: int) -> dict[str, Any]:
        target = self.get_skill(skill_id, version)
        self._write_index(skill_id, {"skillId": skill_id, "currentVersion": int(target["version"]), "updatedAt": _now()})
        return deepcopy(target)

    # ---- Packs ----------------------------------------------------------
    def list_packs(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted(self.packs_root.glob("*.json")):
            pack = self._read(path, default=None)
            if isinstance(pack, dict):
                rows.append(deepcopy(pack))
        return sorted(rows, key=lambda item: item.get("updatedAt", ""), reverse=True)

    def get_pack(self, pack_id: str) -> dict[str, Any]:
        pack = self._read(self.packs_root / f"{pack_id}.json", default=None)
        if not isinstance(pack, dict):
            raise KeyError("pack_not_found")
        return deepcopy(pack)

    def save_pack(self, payload: dict[str, Any], *, imported: bool = False) -> dict[str, Any]:
        now = _now()
        pack_id = str(payload.get("packId") or f"pack_{_slug(str(payload.get('name') or 'director-pack'), 'director-pack')}_{uuid4().hex[:6]}")
        existing = self._read(self.packs_root / f"{pack_id}.json", default={})
        pack = {
            "schemaVersion": SCHEMA_VERSION,
            "packId": pack_id,
            "version": int(payload.get("version") or (int(existing.get("version") or 0) + 1) or 1),
            "name": str(payload.get("name") or existing.get("name") or "未命名导演包").strip()[:120],
            "description": str(payload.get("description") or existing.get("description") or "").strip()[:800],
            "recipeId": str(payload.get("recipeId") or existing.get("recipeId") or DEFAULT_RECIPE_ID),
            "skillPins": self._normalize_skill_pins(payload.get("skillPins") or existing.get("skillPins") or []),
            "style": self._normalize_style(payload.get("style") or existing.get("style") or {}),
            "templates": [str(item) for item in (payload.get("templates") or existing.get("templates") or [])][:20],
            "capabilityIds": [str(item) for item in (payload.get("capabilityIds") or existing.get("capabilityIds") or [])][:30],
            "status": "installed",
            "createdAt": existing.get("createdAt") or now,
            "updatedAt": now,
            "imported": bool(imported or existing.get("imported")),
        }
        checked = self.validate_pack_manifest(pack)
        if not checked["ok"]:
            raise StudioValidationError("；".join(checked["errors"]))
        self._write(self.packs_root / f"{pack_id}.json", pack)
        return deepcopy(pack)

    def validate_pack_manifest(self, pack: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        if not str(pack.get("name") or "").strip():
            errors.append("Director Pack 名称不能为空。")
        recipe_id = str(pack.get("recipeId") or DEFAULT_RECIPE_ID)
        try:
            load_recipe_by_id(recipe_id, self.recipes_root)
        except RecipeValidationError:
            errors.append(f"Recipe 不存在：{recipe_id}")
        pins = pack.get("skillPins")
        if not isinstance(pins, list) or not pins:
            errors.append("Director Pack 至少固定一个已发布 Skill。")
        else:
            for pin in pins:
                try:
                    skill = self.get_skill(str(pin.get("skillId")), int(pin.get("version")))
                    if skill.get("status") != "published":
                        errors.append(f"Skill 未发布：{skill.get('name')}")
                except (KeyError, TypeError, ValueError):
                    errors.append("包含不存在的 Skill 版本。")
        unknown = sorted(item for item in pack.get("capabilityIds", []) if item not in TOOL_SPECS)
        if unknown:
            errors.append(f"包含未注册能力：{', '.join(unknown)}")
        return {"ok": not errors, "errors": errors, "manifest": deepcopy(pack)}

    def export_pack(self, pack_id: str) -> dict[str, Any]:
        pack = self.get_pack(pack_id)
        skills = [self.get_skill(str(pin["skillId"]), int(pin["version"])) for pin in pack["skillPins"]]
        return {"format": "videoforge-director-pack", "formatVersion": 1, "pack": pack, "skills": skills}

    def import_pack(self, document: dict[str, Any]) -> dict[str, Any]:
        if document.get("format") != "videoforge-director-pack" or int(document.get("formatVersion") or 0) != 1:
            raise StudioValidationError("不是有效的 VideoForge Director Pack 文件。")
        skills = document.get("skills")
        pack = document.get("pack")
        if not isinstance(skills, list) or not isinstance(pack, dict):
            raise StudioValidationError("Director Pack 文件缺少 Skill 或 manifest。")
        for skill in skills:
            if not isinstance(skill, dict):
                raise StudioValidationError("Director Pack 内含无效 Skill。")
            skill = deepcopy(skill)
            skill["status"] = "published"
            skill["updatedAt"] = _now()
            self._write_skill(skill, current=True)
        imported = deepcopy(pack)
        imported.pop("packId", None)  # Avoid overwriting an existing private Pack.
        return self.save_pack(imported, imported=True)

    def uninstall_pack(self, pack_id: str) -> None:
        path = self.packs_root / f"{pack_id}.json"
        if not path.is_file():
            raise KeyError("pack_not_found")
        path.unlink()

    # ---- Director integration ------------------------------------------
    def resolve_pack(self, pack_id: str) -> dict[str, Any]:
        pack = self.get_pack(pack_id)
        checked = self.validate_pack_manifest(pack)
        if not checked["ok"]:
            raise StudioValidationError("；".join(checked["errors"]))
        skills = [self.get_skill(str(pin["skillId"]), int(pin["version"])) for pin in pack["skillPins"]]
        return {"pack": pack, "skills": skills}

    def build_scene_plan(self, subtitles: list[dict[str, Any]], skills: list[dict[str, Any]], pack: dict[str, Any] | None) -> dict[str, Any]:
        directives = self._merged_directives(skills, pack)
        signature = " | ".join(filter(None, [str(directives.get("visualStyle") or ""), str(directives.get("sceneRule") or "")]))[:220]
        scenes: list[dict[str, Any]] = []
        for index, subtitle in enumerate(subtitles[:80], start=1):
            text = str(subtitle.get("text") or "").strip()
            if not text:
                continue
            scene_id = str(subtitle.get("id") or f"scene_{index:03d}")
            scenes.append({
                "sceneId": scene_id,
                "start": float(subtitle.get("start") or 0),
                "end": float(subtitle.get("end") or 0),
                "text": text,
                "direction": self._scene_direction(text, directives),
                "visualStyle": directives.get("visualStyle") or "清晰的信息画面",
                "assetStrategy": directives.get("assetStrategy") or "优先复用已有素材",
            })
        return {"version": 1, "packId": (pack or {}).get("packId"), "styleSignature": signature, "directives": directives, "scenes": scenes}

    def capabilities(self) -> list[dict[str, Any]]:
        return [{"id": name, "risk": spec.risk, "approvalPolicy": spec.requiredPolicy, "produces": spec.produces} for name, spec in sorted(TOOL_SPECS.items())]

    # ---- internals ------------------------------------------------------
    def _ensure_seed_skill(self) -> None:
        skill_id = "subtitle_scene_director"
        if (self.skills_root / skill_id / "index.json").is_file():
            return
        now = _now()
        seed = {
            "schemaVersion": SCHEMA_VERSION,
            "skillId": skill_id,
            "version": 1,
            "name": "字幕场景导演",
            "description": "把字幕时间轴转为不跨越字幕边界的可审阅 Scene Plan。",
            "status": "published",
            "source": {"type": "built_in", "text": "subtitle_scene_director", "importedAt": now},
            "directives": {
                "sceneRule": "一条字幕对应一个 Scene，不跨越字幕时间边界。",
                "visualStyle": "信息清晰、节奏克制、重点用可读信息卡。",
                "assetStrategy": "先复用已有素材，缺失时提出生成建议。",
                "approvalRule": "替换已有素材或付费生成必须等待审批。",
            },
            "requiredCapabilities": list(DEFAULT_CAPABILITIES),
            "outputContract": {"type": "scene_plan", "fields": ["sceneId", "start", "end", "direction", "visualStyle"]},
            "createdAt": now,
            "updatedAt": now,
            "publishedAt": now,
        }
        self._write_skill(seed, current=True)

    def _write_skill(self, skill: dict[str, Any], *, current: bool) -> None:
        skill_id = str(skill["skillId"])
        version = int(skill["version"])
        directory = self.skills_root / skill_id
        directory.mkdir(parents=True, exist_ok=True)
        self._write(directory / f"v{version}.json", skill)
        if current:
            self._write_index(skill_id, {"skillId": skill_id, "currentVersion": version, "updatedAt": skill.get("updatedAt") or _now()})

    def _skill_index(self, skill_id: str) -> dict[str, Any]:
        index = self._read(self.skills_root / skill_id / "index.json", default=None)
        if not isinstance(index, dict):
            raise KeyError("skill_not_found")
        return index

    def _write_index(self, skill_id: str, index: dict[str, Any]) -> None:
        directory = self.skills_root / skill_id
        directory.mkdir(parents=True, exist_ok=True)
        self._write(directory / "index.json", index)

    def _load_skill_version(self, skill_id: str, version: int) -> dict[str, Any] | None:
        value = self._read(self.skills_root / skill_id / f"v{version}.json", default=None)
        return value if isinstance(value, dict) else None

    def _normalize_skill_pins(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise StudioValidationError("skillPins 必须是数组。")
        pins: list[dict[str, Any]] = []
        for row in value[:12]:
            if not isinstance(row, dict):
                continue
            skill_id = str(row.get("skillId") or "")
            if not skill_id:
                continue
            version = int(row.get("version") or self._skill_index(skill_id)["currentVersion"])
            pins.append({"skillId": skill_id, "version": version})
        return pins

    @staticmethod
    def _normalize_style(value: Any) -> dict[str, str]:
        source = value if isinstance(value, dict) else {}
        return {key: str(source.get(key) or "").strip()[:240] for key in ("name", "palette", "mood", "layout")}

    def _infer_name(self, source: str) -> str:
        if "纪录片" in source:
            return "低饱和纪录片导演"
        if "知识" in source:
            return "知识短视频导演"
        return "我的导演方法"

    @staticmethod
    def _infer_description(source: str) -> str:
        first = re.sub(r"\s+", " ", source).strip()
        return first[:180]

    @staticmethod
    def _infer_directives(source: str) -> dict[str, str]:
        lowered = source.lower()
        return {
            "sceneRule": "一条字幕对应一个 Scene，不跨越字幕时间边界。" if any(token in source for token in ("字幕", "一句", "场景")) else "按语义拆分 Scene，并保持时间轴连续。",
            "visualStyle": "暖棕、低饱和金色、纪录片质感。" if any(token in source for token in ("纪录片", "低饱和", "暖棕", "金色")) else "清晰、克制、与内容主题一致的视觉表达。",
            "assetStrategy": "优先复用真实素材，缺失时再提出生成建议。" if any(token in source for token in ("复用", "真实素材", "素材")) else "优先复用已有素材，缺失时提出生成建议。",
            "approvalRule": "替换已有素材、付费调用和覆盖草稿必须等待审批。" if any(token in lowered for token in ("审批", "确认", "付费", "替换")) else "替换已有素材必须等待审批。",
        }

    @staticmethod
    def _infer_capabilities(source: str) -> list[str]:
        capabilities = list(DEFAULT_CAPABILITIES)
        if any(token in source for token in ("剪映", "导出")):
            capabilities.append("export_editable_draft")
        return capabilities

    @staticmethod
    def _merged_directives(skills: list[dict[str, Any]], pack: dict[str, Any] | None) -> dict[str, str]:
        result: dict[str, str] = {}
        for skill in skills:
            directives = skill.get("directives")
            if isinstance(directives, dict):
                result.update({key: str(value) for key, value in directives.items() if str(value).strip()})
        style = (pack or {}).get("style")
        if isinstance(style, dict):
            pieces = [str(style.get(key) or "").strip() for key in ("name", "palette", "mood", "layout")]
            if any(pieces):
                result["visualStyle"] = "；".join(piece for piece in pieces if piece)
        return result

    @staticmethod
    def _scene_direction(text: str, directives: dict[str, str]) -> str:
        rule = str(directives.get("sceneRule") or "")
        style = str(directives.get("visualStyle") or "")
        return f"{rule} 画面围绕“{text[:58]}”展开；{style}".strip()

    @staticmethod
    def _skill_summary(skill: dict[str, Any]) -> dict[str, Any]:
        return {key: deepcopy(skill.get(key)) for key in ("skillId", "version", "name", "description", "status", "directives", "requiredCapabilities", "createdAt", "updatedAt", "publishedAt")}

    @staticmethod
    def _read(path: Path, *, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    @staticmethod
    def _write(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)


__all__ = ["DirectorStudioRegistry", "StudioValidationError"]
