"""Agent-backed, confirmation-only organizer for unstructured source scripts."""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .provider_settings import load_agent_provider

BLOCK_TYPES = {
    "HOOK", "CTA_TAG", "PROBLEM", "STORY", "MECHANISM", "JUDGMENT",
    "METHOD", "SHORT_OUTRO", "BRIDGE_IN", "BRIDGE_OUT", "COMMENT_CTA",
}


class OrganizerError(RuntimeError):
    pass


def organize_source(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise OrganizerError("请先粘贴原始文案。")
    return _request(_source_instruction(text))


def organize_block(text: str, current_type: str | None = None) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise OrganizerError("这个 Block 没有可整理的文字。")
    result = _request(_block_instruction(text, current_type))
    if len(result["blocks"]) != 1:
        raise OrganizerError("上游返回的单 Block 整理结果不完整，请重试。")
    return result


def _request(instruction: str) -> dict[str, Any]:
    settings = load_agent_provider()
    if not settings.enabled or not settings.baseUrl or not settings.model:
        raise OrganizerError("Agent 模型服务尚未配置。请先在 Agent 设置中保存并测试连接，或使用手动分段。")
    base = settings.baseUrl.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.apiKey}", "Content-Type": "application/json"}
    try:
        if settings.apiType == "openai-responses":
            response = httpx.post(f"{base}/responses", headers=headers, json={"model": settings.model, "input": instruction}, timeout=settings.timeoutSeconds)
        else:
            response = httpx.post(f"{base}/chat/completions", headers=headers, json={"model": settings.model, "messages": [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": instruction}], "temperature": 0.2, "response_format": {"type": "json_object"}}, timeout=settings.timeoutSeconds)
        response.raise_for_status()
        return _validate(_content(response.json(), settings.apiType))
    except httpx.HTTPStatusError as exc:
        raise OrganizerError(f"Agent 整理请求失败：上游返回 HTTP {exc.response.status_code}。可检查模型、余额或服务地址后重试。") from exc
    except httpx.HTTPError as exc:
        raise OrganizerError(f"Agent 整理请求未完成：{exc}。原文已保留，可使用手动分段。") from exc
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise OrganizerError("Agent 返回的结构草案不符合 VideoForge 格式。原文已保留，可重试或使用手动分段。") from exc


def _content(raw: dict[str, Any], api_type: str) -> str:
    if api_type == "openai-responses":
        if isinstance(raw.get("output_text"), str):
            return raw["output_text"]
        for output in raw.get("output") or []:
            for content in output.get("content") or []:
                if isinstance(content.get("text"), str):
                    return content["text"]
    choices = raw.get("choices") or []
    content = ((choices[0].get("message") or {}).get("content")) if choices else None
    if isinstance(content, list):
        content = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    if not isinstance(content, str):
        raise ValueError("missing response content")
    return content


def _validate(content: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", content, re.S)
    data = json.loads(match.group(0) if match else content)
    title = str(data.get("title") or "").strip()[:160]
    blocks = []
    for index, raw in enumerate(data.get("blocks") or [], 1):
        kind = str(raw.get("type") or "").upper()
        text = str(raw.get("text") or "").strip()
        if kind not in BLOCK_TYPES or not text:
            continue
        block_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(raw.get("id") or f"{kind.lower()}_{index:02d}")).strip("_")[:64] or f"{kind.lower()}_{index:02d}"
        blocks.append({"id": block_id, "type": kind, "text": text, "enabled": True, "revision": 1, "metadata": {"semantic": raw.get("semantic") if isinstance(raw.get("semantic"), dict) else {}, "confidence": max(0, min(1, float(raw.get("confidence", 0.5) or 0.5))), "warnings": [str(item)[:160] for item in (raw.get("warnings") or []) if str(item).strip()]}})
    if not blocks:
        raise ValueError("no valid blocks")
    # IDs must be stable and unique before the user reaches the confirmation UI.
    seen: set[str] = set()
    for index, block in enumerate(blocks, 1):
        base = block["id"]
        block["id"] = base if base not in seen else f"{base}_{index:02d}"
        seen.add(block["id"])
    return {"title": title, "blocks": blocks, "summary": str(data.get("summary") or "已按视频叙事节奏整理为可编辑 Blocks。").strip()[:400], "warnings": [str(item)[:160] for item in (data.get("warnings") or []) if str(item).strip()]}


_SYSTEM = """You organize raw Chinese scripts for VideoForge. Return JSON only. Never create files, projects, media, or execute tools. The user will review every result before project creation."""


def _source_instruction(text: str) -> str:
    return f"""Convert this raw script into a draft VideoForge episode. Preserve every important idea and original title if present. Split by narrative meaning, not arbitrary sentence count. Use only these block types: {', '.join(sorted(BLOCK_TYPES))}. Return JSON: {{\"title\":string,\"summary\":string,\"warnings\":[string],\"blocks\":[{{\"id\":string,\"type\":one allowed type,\"text\":string,\"semantic\":object,\"confidence\":0..1,\"warnings\":[string]}}]}}.\n\nRAW SCRIPT:\n{text}"""


def _block_instruction(text: str, current_type: str | None) -> str:
    return f"""Reorganize exactly one editable VideoForge block. Keep its meaning, improve its type and semantic metadata, and return exactly one block in the same JSON shape. Current type: {current_type or 'unknown'}.\n\nBLOCK TEXT:\n{text}"""
