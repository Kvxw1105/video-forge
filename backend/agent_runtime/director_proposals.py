"""Parse Pi planning output into VideoForge-owned approval proposals.

Pi is not an executor.  This module accepts a deliberately small JSON envelope
from an assistant's final message and maps it to the recipe's existing approval
contract.  Unknown fields or operations are ignored instead of becoming tools.
"""
from __future__ import annotations

import json
from typing import Any, Iterable
from uuid import uuid4


PROPOSAL_ENVELOPE = "videoforgeActionProposals"
_ALLOWED_OPERATION = "replace_scene_asset"


def proposal_instruction(scene_id: str = "scene_001") -> str:
    """Tell Pi how to propose a reviewable operation without granting tools."""
    example = json.dumps({PROPOSAL_ENVELOPE: [{"operation": _ALLOWED_OPERATION, "sceneId": scene_id, "reason": "short evidence-based reason"}]}, ensure_ascii=False)
    return (
        "VideoForge action-proposal output contract:\n"
        "You cannot execute or write anything. If, and only if, your plan needs user\n"
        "approval to replace the generated asset, finish with one JSON object in a fenced\n"
        f"json block: {example}. Do not propose any other operation."
    )


def proposals_from_agent_end(event: dict[str, Any], *, scene_id: str = "scene_001") -> list[dict[str, Any]]:
    """Extract valid proposals from a normalized Pi ``agent_end`` event."""
    raw = event.get("piEvent") if isinstance(event.get("piEvent"), dict) else {}
    messages = raw.get("messages") if isinstance(raw.get("messages"), list) else []
    proposals: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        for payload in _json_payloads(_message_text(message)):
            candidate_rows = payload.get(PROPOSAL_ENVELOPE)
            if not isinstance(candidate_rows, list):
                continue
            for candidate in candidate_rows:
                proposal = _normalize_candidate(candidate, scene_id=scene_id)
                if proposal:
                    proposals.append(proposal)
    return proposals


def merge_action_proposals(run: dict[str, Any], proposals: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Persist proposals and attach compatible ones to the existing approval.

    The v1 Director flow has one real operation: binding the generated vector
    card.  A Pi proposal enriches that pending approval rather than creating a
    second action that could accidentally bypass the existing settled gate.
    """
    added: list[dict[str, Any]] = []
    known = run.setdefault("actionProposals", [])
    approvals = run.setdefault("approvals", [])
    for proposal in proposals:
        fingerprint = (proposal["operation"], proposal["sceneId"], proposal["reason"])
        if any((row.get("operation"), row.get("sceneId"), row.get("reason")) == fingerprint for row in known):
            continue
        item = {"proposalId": f"proposal_{uuid4().hex[:10]}", "status": "pending_approval", "source": "pi", **proposal}
        known.append(item)
        for approval in approvals:
            if approval.get("status") == "pending" and approval.get("operation") == item["operation"] and approval.get("sceneId") == item["sceneId"]:
                approval["actionProposal"] = item
                item["approvalId"] = approval.get("approvalId")
                break
        added.append(item)
    return added


def _normalize_candidate(candidate: Any, *, scene_id: str) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    if candidate.get("operation") != _ALLOWED_OPERATION or candidate.get("sceneId") != scene_id:
        return None
    reason = str(candidate.get("reason") or "").strip()
    if not reason:
        return None
    return {
        "operation": _ALLOWED_OPERATION,
        "sceneId": scene_id,
        "reason": reason[:400],
        "risk": "medium",
        "recipeStepId": "bind_assets",
        "recipeTool": "bind_scene_assets",
    }


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(str(part.get("text") or "") for part in content if isinstance(part, dict) and part.get("type") == "text")


def _json_payloads(text: str) -> Iterable[dict[str, Any]]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield value
