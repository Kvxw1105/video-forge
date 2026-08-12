from __future__ import annotations

from dataclasses import dataclass
import re

from shared.director_intents import SCENE_INTENTS
from .contracts import SceneRequest


@dataclass(frozen=True)
class ProviderRoute:
    provider_id: str
    reason: str
    confidence: float
    rules_hit: tuple[str, ...] = ()


_STICKMAN_RULES = {
    "relationship": ("关系", "relationship", "朋友", "伴侣", "人物", "person", "character", "对话", "冲突", "心理", "情绪", "焦虑", "压力", "控制", "选择"),
    "human_action": ("走", "跑", "握手", "拉", "推", "逃", "离开", "面对", "人", "human", "emotion"),
}
_CODE_RULES = {
    "causal": ("因果", "原因", "结果", "导致", "因为", "所以", "cause", "effect", "consequence"),
    "process": ("流程", "步骤", "阶段", "进展", "progression", "process", "step", "pipeline", "first", "then", "finally"),
    "comparison": ("比较", "对比", "区别", "优劣", "versus", "compare", "contrast", "不同"),
    "data": ("排名", "排行", "数字", "数据", "比例", "百分比", "ranking", "score", "number", "data", "percent", "top"),
    "topology": ("节点", "关系图", "网络", "拓扑", "知识", "连接", "node", "link", "network", "topology", "knowledge"),
    "mechanism": ("机制", "结构", "原理", "系统", "机制图", "mechanism", "diagram", "system", "architecture"),
    "keyword": ("关键词", "概念", "核心", "重点", "keyword", "concept", "definition", "highlight"),
}

# Rule keys are the single Scene intent vocabulary; a key outside the shared
# enum would make ProviderRoute.rules_hit useless to the policy resolver.
assert set(_STICKMAN_RULES) | set(_CODE_RULES) <= set(SCENE_INTENTS), "router rules must use shared scene intents"


def _contains(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)


def route_scene(request: SceneRequest, mode: str = "auto", override: str = "") -> ProviderRoute:
    if override and override not in {"auto", ""}:
        return ProviderRoute(override, "scene_override", 1.0, ("override",))
    if mode in {"stickman", "code_visual"}:
        return ProviderRoute(mode, "batch_mode", 1.0, (mode,))
    hints = request.options.get("routeHints") or {}
    raw = " ".join(str(value) for value in [request.text, request.options.get("finalPrompt", ""), request.options.get("semanticIntent", ""), hints.get("visualIntent", ""), hints.get("visualFamily", "")]).lower()
    code_hits = tuple(name for name, terms in _CODE_RULES.items() if _contains(raw, terms))
    stick_hits = tuple(name for name, terms in _STICKMAN_RULES.items() if _contains(raw, terms))
    requested = str(request.options.get("requestedMediaType") or "").lower()
    if requested == "video" and code_hits:
        return ProviderRoute("code_visual", "requested_video_with_structured_semantics", 0.95, code_hits)
    if code_hits and len(code_hits) >= len(stick_hits):
        return ProviderRoute("code_visual", "semantic_rule_match", min(0.96, 0.68 + 0.06 * len(code_hits)), code_hits)
    if stick_hits:
        return ProviderRoute("stickman", "semantic_rule_match", min(0.94, 0.7 + 0.06 * len(stick_hits)), stick_hits)
    return ProviderRoute("stickman", "fallback_provider", 0.35, ("generic",))
