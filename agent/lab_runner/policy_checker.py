from __future__ import annotations

from typing import Any

from .models import PolicyDecision


AUTO_ALLOW = {
    "read_project",
    "view_scene",
    "read_batch_status",
    "read_coverage",
    "read_preview_status",
    "analyze_script",
    "inspect_video_project",
    "inspect_video_readiness",
    "validate_video_readiness",
    "inspect_pending_visuals",
    "get_video_job_status",
}

APPROVAL_REQUIRED = {
    "paid_image_generation": ("paid-operation-policy", "medium", []),
    "paid_video_generation": ("paid-operation-policy", "high", []),
    "regenerate_voiceover": ("paid-operation-policy", "medium", ["alignment", "subtitles", "visual_plan", "preview", "jianying_draft"]),
    "replace_scene_asset": ("default-policy", "medium", ["preview", "jianying_draft"]),
    "replace_successful_preview": ("default-policy", "medium", ["preview", "jianying_draft"]),
    "script_content_change": ("default-policy", "medium", []),
}

DENY = {
    "delete_project": ("destructive-operation-policy", "high", "Project deletion is outside Phase 0 Lab Runner scope."),
    "overwrite_jianying_draft": ("destructive-operation-policy", "high", "Editable draft export must use create_new."),
    "modify_subtitle_time": ("destructive-operation-policy", "high", "Subtitle timing is VideoForge-owned and read-only for the agent."),
    "modify_alignment": ("destructive-operation-policy", "high", "Alignment is VideoForge-owned and read-only for the agent."),
    "execute_shell": ("destructive-operation-policy", "high", "Recipes cannot execute shell commands."),
}


class PolicyChecker:
    def decide(self, operation: str, context: dict[str, Any] | None = None) -> PolicyDecision:
        context = context or {}
        if operation in AUTO_ALLOW:
            return PolicyDecision("allow", "default-policy", "low", f"{operation} is read-only or local analysis.")
        if operation in APPROVAL_REQUIRED:
            policy_id, risk, invalidated = APPROVAL_REQUIRED[operation]
            cost = context.get("estimatedCost")
            return PolicyDecision("approval_required", policy_id, risk, f"{operation} requires explicit approval.", list(invalidated), cost)
        if operation in DENY:
            policy_id, risk, reason = DENY[operation]
            return PolicyDecision("deny", policy_id, risk, reason)
        return PolicyDecision("allow", "default-policy", "low", f"{operation} has no additional Phase 0 restriction.")
