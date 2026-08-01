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
from .production_packs import (PACK_EXPORT_FORMAT, PACK_EXPORT_VERSION, ProductionPackCompiler, ProductionPackError, builtin_packs, new_eval_run_id, render_eval_artifact)

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
        self.eval_root = self.root / "evals"
        self.compiler = ProductionPackCompiler()
        self.skills_root.mkdir(parents=True, exist_ok=True)
        self.packs_root.mkdir(parents=True, exist_ok=True)
        self.eval_root.mkdir(parents=True, exist_ok=True)
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
        """List installed private packs plus immutable first-party Packs."""
        rows: dict[str, dict[str, Any]] = {pack_id: deepcopy(pack) for pack_id, pack in builtin_packs().items()}
        for path in sorted(self.packs_root.glob("*.json")):
            raw = self._read(path, default=None)
            if not isinstance(raw, dict):
                continue
            try:
                pack, migration_warnings = self.compiler.normalize(raw)
            except ProductionPackError:
                continue
            if migration_warnings:
                pack.setdefault("migration", {})["warnings"] = migration_warnings
            rows[pack["packId"]] = pack
        return sorted(rows.values(), key=lambda item: (item.get("source", {}).get("type") != "built_in", item.get("updatedAt", ""), item.get("name", "")), reverse=True)

    def get_pack(self, pack_id: str) -> dict[str, Any]:
        builtin = builtin_packs().get(pack_id)
        raw = self._read(self.packs_root / f"{pack_id}.json", default=None)
        if raw is None and builtin is None:
            raise KeyError("pack_not_found")
        source = raw if isinstance(raw, dict) else builtin
        try:
            pack, migration_warnings = self.compiler.normalize(source or {})
        except ProductionPackError as exc:
            raise StudioValidationError(str(exc)) from exc
        if migration_warnings:
            pack.setdefault("migration", {})["warnings"] = migration_warnings
        return deepcopy(pack)

    def save_pack(self, payload: dict[str, Any], *, imported: bool = False) -> dict[str, Any]:
        now = _now()
        requested_id = str(payload.get("packId") or "").strip()
        pack_id = requested_id or f"pack_{_slug(str(payload.get('name') or 'production-pack'), 'production-pack')}_{uuid4().hex[:6]}"
        existing = self._read(self.packs_root / f"{pack_id}.json", default=None)
        base = deepcopy(existing) if isinstance(existing, dict) else deepcopy(builtin_packs().get(pack_id) or {})
        candidate = {**base, **deepcopy(payload), "packId": pack_id}
        # A V1-form payload is migrated in memory, then written back as V2 only on this explicit save.
        candidate["schemaVersion"] = 2 if candidate.get("rendererBindings") and candidate.get("sceneArchetypes") else int(candidate.get("schemaVersion") or 1)
        if not candidate.get("createdAt"):
            candidate["createdAt"] = now
        candidate["updatedAt"] = now
        candidate["imported"] = bool(imported or candidate.get("imported"))
        try:
            pack, migration_warnings = self.compiler.normalize(candidate)
        except ProductionPackError as exc:
            raise StudioValidationError(str(exc)) from exc
        if migration_warnings:
            pack.setdefault("migration", {})["warnings"] = migration_warnings
        checked = self.validate_pack_manifest(pack, require_eval_cases=False)
        if not checked["ok"]:
            raise StudioValidationError("；".join(item["message"] for item in checked["errors"]))
        self._write(self.packs_root / f"{pack_id}.json", pack)
        return deepcopy(pack)

    def validate_pack_manifest(self, pack: dict[str, Any], *, require_eval_cases: bool = False) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        recipe_id = str(pack.get("recipeId") or DEFAULT_RECIPE_ID)
        try:
            load_recipe_by_id(recipe_id, self.recipes_root)
        except RecipeValidationError:
            errors.append({"code": "recipe_not_found", "message": f"Recipe 不存在：{recipe_id}"})
        checked = self.compiler.validate(
            pack,
            capabilities=set(TOOL_SPECS),
            skill_lookup=lambda skill_id, version: self.get_skill(skill_id, version),
            require_eval_cases=require_eval_cases,
        )
        return {
            "ok": not errors and bool(checked["ok"]),
            "errors": [*errors, *list(checked["errors"])],
            "warnings": list(checked["warnings"]),
            "manifest": deepcopy(checked["pack"] or pack),
            "registry": checked.get("registry"),
        }

    def export_pack(self, pack_id: str) -> dict[str, Any]:
        pack = self.get_pack(pack_id)
        skills = [self.get_skill(str(pin["skillId"]), int(pin["version"])) for pin in pack["skillPins"]]
        return {
            # Keep the established envelope so V1 consumers can still import a
            # Pack.  The manifest inside is explicitly V2, and the additional
            # fields let newer clients identify the richer contract without a
            # flag day for existing exports.
            "format": "videoforge-director-pack",
            "formatVersion": 1,
            "productionPackFormat": PACK_EXPORT_FORMAT,
            "productionPackFormatVersion": PACK_EXPORT_VERSION,
            "pack": pack,
            "skills": skills,
            "fingerprint": pack["fingerprint"],
        }

    def import_pack(self, document: dict[str, Any]) -> dict[str, Any]:
        source_format = str(document.get("format") or "")
        source_version = int(document.get("formatVersion") or 0)
        if (source_format, source_version) not in {(PACK_EXPORT_FORMAT, PACK_EXPORT_VERSION), ("videoforge-director-pack", 1)}:
            raise StudioValidationError("不是有效的 VideoForge Production Pack 文件。")
        skills = document.get("skills")
        imported_pack = document.get("pack")
        if not isinstance(skills, list) or not isinstance(imported_pack, dict):
            raise StudioValidationError("Production Pack 文件缺少 Skill 或 manifest。")
        for skill in skills:
            if not isinstance(skill, dict):
                raise StudioValidationError("Production Pack 内含无效 Skill。")
            pinned = deepcopy(skill)
            pinned["status"] = "published"
            pinned["updatedAt"] = _now()
            self._write_skill(pinned, current=True)
        candidate = deepcopy(imported_pack)
        candidate.pop("packId", None)  # An import must never overwrite a private Pack.
        candidate["migration"] = {
            "sourceFormat": source_format,
            "sourceFormatVersion": source_version,
            "warnings": ["导入包已隔离为新的私有实例。"] if source_format != PACK_EXPORT_FORMAT else [],
        }
        return self.save_pack(candidate, imported=True)

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
            raise StudioValidationError("；".join(item["message"] for item in checked["errors"]))
        skills = [self.get_skill(str(pin["skillId"]), int(pin["version"])) for pin in pack["skillPins"]]
        return {"pack": checked["manifest"], "skills": skills, "health": {"status": "ready" if not checked["warnings"] else "warning", "warnings": checked["warnings"], "rendererRegistry": checked.get("registry")}}

    def build_scene_plan(
        self,
        subtitles: list[dict[str, Any]],
        skills: list[dict[str, Any]],
        pack: dict[str, Any] | None,
        *,
        visual_scenes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        directives = self._merged_directives(skills, pack)
        source_scenes: list[dict[str, Any]] = []
        if visual_scenes:
            subtitle_map = {str(item.get("id")): item for item in subtitles if isinstance(item, dict)}
            for index, visual_scene in enumerate(visual_scenes, start=1):
                ids = [str(item) for item in visual_scene.get("subtitleIds") or []]
                selected = [subtitle_map[item] for item in ids if item in subtitle_map]
                source_scenes.append({
                    "sceneId": str(visual_scene.get("id") or f"scene_{index:03d}"),
                    "start": float(selected[0].get("start") if selected else visual_scene.get("start") or 0),
                    "end": float(selected[-1].get("end") if selected else visual_scene.get("end") or 0),
                    "text": "".join(str(item.get("text") or "") for item in selected) or str(visual_scene.get("summary") or ""),
                    "direction": self._scene_direction(str(visual_scene.get("summary") or ""), directives),
                    "metadata": deepcopy(visual_scene.get("metadata") or {}),
                    "blockType": visual_scene.get("blockType"),
                })
        else:
            for index, subtitle in enumerate(subtitles[:80], start=1):
                text = str(subtitle.get("text") or "").strip()
                if not text:
                    continue
                source_scenes.append({
                    "sceneId": str(subtitle.get("id") or f"scene_{index:03d}"),
                    "start": float(subtitle.get("start") or 0),
                    "end": float(subtitle.get("end") or 0),
                    "text": text,
                    "direction": self._scene_direction(text, directives),
                    "metadata": deepcopy(subtitle.get("metadata") or {}),
                })
        if pack:
            compiled = self.compiler.compile(
                pack,
                source_scenes,
                capabilities=set(TOOL_SPECS),
                skill_lookup=lambda skill_id, version: self.get_skill(skill_id, version),
            )
            scene_plan = compiled["scenePlan"]
            scene_plan["directives"] = directives
            scene_plan["styleSignature"] = " | ".join(filter(None, [str(directives.get("visualStyle") or ""), str(directives.get("sceneRule") or "")]))[:220]
            scene_plan["warnings"] = compiled["warnings"]
            return scene_plan
        return {"version": 1, "packId": None, "styleSignature": " | ".join(filter(None, [str(directives.get("visualStyle") or ""), str(directives.get("sceneRule") or "")]))[:220], "directives": directives, "scenes": source_scenes}

    def capabilities(self) -> list[dict[str, Any]]:
        return [{"id": name, "risk": spec.risk, "approvalPolicy": spec.requiredPolicy, "produces": spec.produces} for name, spec in sorted(TOOL_SPECS.items())]

    def renderer_registry(self) -> dict[str, Any]:
        return self.compiler.registry_loader()

    def migration_preview(self, pack_id: str) -> dict[str, Any]:
        raw = self._read(self.packs_root / f"{pack_id}.json", default=None)
        if raw is None:
            raw = builtin_packs().get(pack_id)
        if not isinstance(raw, dict):
            raise KeyError("pack_not_found")
        pack, warnings = self.compiler.normalize(raw)
        return {"pack": pack, "warnings": warnings, "willPersistOnSave": bool(warnings)}

    def compile_pack(self, pack_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        resolved = self.resolve_pack(pack_id)
        subtitles = payload.get("subtitles") if isinstance(payload.get("subtitles"), list) else []
        visual_scenes = payload.get("visualScenes") if isinstance(payload.get("visualScenes"), list) else None
        plan = self.build_scene_plan(subtitles, resolved["skills"], resolved["pack"], visual_scenes=visual_scenes)
        return {"pack": resolved["pack"], "packFingerprint": resolved["pack"]["fingerprint"], "scenePlan": plan, "warnings": [*resolved["health"]["warnings"], *list(plan.get("warnings") or [])], "errors": []}

    def run_pack_eval(self, pack_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        resolved = self.resolve_pack(pack_id)
        checked = self.validate_pack_manifest(resolved["pack"], require_eval_cases=True)
        if not checked["ok"]:
            raise StudioValidationError("；".join(item["message"] for item in checked["errors"]))
        cases = list(resolved["pack"].get("evalCases") or [])
        selected_case_id = str(payload.get("caseId") or "").strip()
        if selected_case_id:
            cases = [item for item in cases if str(item.get("caseId")) == selected_case_id]
        if not cases:
            raise StudioValidationError("找不到请求的 Eval Case。")
        run_id = new_eval_run_id()
        run_root = self.eval_root / run_id
        run_root.mkdir(parents=True, exist_ok=False)
        result: dict[str, Any] = {"runId": run_id, "packId": resolved["pack"]["packId"], "packVersion": resolved["pack"]["version"], "packFingerprint": resolved["pack"]["fingerprint"], "status": "running", "startedAt": _now(), "cases": [], "warnings": [], "errors": []}
        for index, case in enumerate(cases, start=1):
            scene = {"sceneId": f"eval_{index:03d}", "start": 0, "end": 3.2, "text": str(case.get("text") or "")}
            try:
                compiled = self.compiler.compile(resolved["pack"], [scene], capabilities=set(TOOL_SPECS), skill_lookup=lambda skill_id, version: self.get_skill(skill_id, version))
                spec = compiled["scenePlan"]["scenes"][0]["visualSpec"]
                artifact = render_eval_artifact(spec, scene, run_root / str(case.get("caseId") or f"case_{index:03d}"))
                row = {"case": deepcopy(case), "visualSpec": spec, "artifact": artifact, "warnings": artifact.get("warnings") or []}
                result["cases"].append(row)
                result["warnings"].extend(row["warnings"])
            except Exception as exc:
                result["errors"].append({"code": "eval_renderer_failed", "message": str(exc), "recoverable": True, "details": {"caseId": case.get("caseId")}})
        result["status"] = "succeeded" if result["cases"] and not result["errors"] else ("partial" if result["cases"] else "failed")
        result["finishedAt"] = _now()
        self._write(run_root / "result.json", result)
        return deepcopy(result)

    def get_pack_eval(self, pack_id: str, run_id: str) -> dict[str, Any]:
        if Path(run_id).name != run_id or not run_id.startswith("pack_eval_"):
            raise StudioValidationError("无效的 Eval Run ID。")
        result = self._read(self.eval_root / run_id / "result.json", default=None)
        if not isinstance(result, dict) or result.get("packId") != pack_id:
            raise KeyError("pack_eval_not_found")
        return deepcopy(result)

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
        style = (pack or {}).get("styleKit") or (pack or {}).get("style")
        if isinstance(style, dict):
            if "identity" in style:
                identity = style.get("identity") if isinstance(style.get("identity"), dict) else {}
                palette = style.get("palette") if isinstance(style.get("palette"), dict) else {}
                composition = style.get("composition") if isinstance(style.get("composition"), dict) else {}
                pieces = [str(identity.get("name") or "").strip(), str(palette.get("background") or "").strip(), str(composition.get("informationHierarchy") or "").strip()]
            else:
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
