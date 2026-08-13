from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from vforge import client as vforge_client


@dataclass(frozen=True)
class ToolSpec:
    name: str
    mode: str
    risk: str
    idempotent: bool
    requiredPolicy: str | None
    allowedStates: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


TOOL_SPECS: dict[str, ToolSpec] = {
    "inspect_video_project": ToolSpec("inspect_video_project", "inspect", "low", True, None, produces=["project_inspection"]),
    "inspect_video_readiness": ToolSpec("inspect_video_readiness", "inspect", "low", True, None, produces=["readiness_report"]),
    "validate_video_readiness": ToolSpec("validate_video_readiness", "inspect", "low", True, None, produces=["readiness_report"]),
    "prepare_structured_script": ToolSpec("prepare_structured_script", "plan", "low", True, None, produces=["structured_episode_proposal"]),
    "create_video_factory_job": ToolSpec("create_video_factory_job", "execute", "medium", True, "paid_operation_if_selected", produces=["batch"], errors=["paid_tts_concurrency", "unsupported_combination"]),
    "review_visual_scene_plan": ToolSpec("review_visual_scene_plan", "plan", "low", True, None, produces=["scene_plan"], errors=["visual_plan_stale", "block_boundary_crossed"]),
    "prepare_visual_generation_pack": ToolSpec("prepare_visual_generation_pack", "execute", "low", True, None, produces=["visual_generation_pack"], errors=["visual_plan_stale"]),
    "inspect_pending_visuals": ToolSpec("inspect_pending_visuals", "inspect", "low", True, None, produces=["pending_visuals"]),
    "bind_scene_assets": ToolSpec("bind_scene_assets", "execute", "medium", True, "replace_asset_if_needed", produces=["visual_binding"], errors=["asset_conflict", "scene_not_found"]),
    "validate_video_assets": ToolSpec("validate_video_assets", "inspect", "low", True, None, produces=["asset_validation"], errors=["visual_coverage_incomplete"]),
    "build_video_preview": ToolSpec("build_video_preview", "execute", "medium", True, None, ["ready_to_resume", "failed"], ["preview"], ["visual_coverage_incomplete", "visual_plan_stale"]),
    "audit_video_preview": ToolSpec("audit_video_preview", "inspect", "low", True, None, produces=["qa_report"]),
    "export_editable_draft": ToolSpec("export_editable_draft", "execute", "medium", True, "create_new_only", produces=["jianying_draft"], errors=["draft_export_failed"]),
    "recover_video_job": ToolSpec("recover_video_job", "execute", "medium", True, None, ["recoverable", "failed"], ["recovery"], ["item_not_ready_to_resume"]),
    "get_video_job_status": ToolSpec("get_video_job_status", "inspect", "low", True, None, produces=["job_status"]),
}


class ToolRegistry:
    def __init__(self, tools: dict[str, Callable[..., Any]] | None = None):
        self.specs = dict(TOOL_SPECS)
        self.tools = tools or {
            "inspect_video_project": vforge_client.inspect_video_project,
            "inspect_video_readiness": vforge_client.inspect_video_readiness,
            "validate_video_readiness": vforge_client.validate_video_readiness,
            "prepare_structured_script": vforge_client.prepare_structured_script,
            "create_video_factory_job": vforge_client.create_video_factory_job,
            "review_visual_scene_plan": vforge_client.review_visual_scene_plan,
            "prepare_visual_generation_pack": vforge_client.prepare_visual_generation_pack,
            "inspect_pending_visuals": vforge_client.inspect_pending_visuals,
            "bind_scene_assets": vforge_client.bind_scene_assets,
            "validate_video_assets": vforge_client.validate_video_assets,
            "build_video_preview": vforge_client.build_video_preview,
            "audit_video_preview": vforge_client.audit_video_preview,
            "export_editable_draft": vforge_client.export_editable_draft,
            "recover_video_job": vforge_client.recover_video_job,
            "get_video_job_status": vforge_client.get_video_job_status,
        }

    def has(self, name: str) -> bool:
        return name in self.specs and name in self.tools

    def spec(self, name: str) -> ToolSpec:
        return self.specs[name]

    def call(self, name: str, **kwargs: Any) -> Any:
        return self.tools[name](**kwargs)
