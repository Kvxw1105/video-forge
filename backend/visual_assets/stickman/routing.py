from __future__ import annotations

from typing import Protocol

from visual_assets.contracts import RoutingOptions, VisualAssetRoute, VisualAssetSourceItem
from .templates import TEMPLATES


class SemanticRouter(Protocol):
    def route(self, item: VisualAssetSourceItem, options: RoutingOptions) -> VisualAssetRoute:
        ...


VISUAL_INTENT_MAP = {"red_string_pull": "red_string_control", "relationship_tug": "relationship_tug", "mask": "people_pleaser_mask", "boundary_intrusion": "boundary_intrusion", "inner_conflict": "inner_conflict", "burden": "burden_boulder", "escape": "escape_enclosure"}
TOPIC_MAP = {"relationship_control": "red_string_control", "people_pleasing": "people_pleaser_mask", "boundary": "boundary_intrusion", "inner_conflict": "inner_conflict", "pressure": "burden_boulder", "comparison": "comparison_trap", "approval": "approval_chase"}
EMOTION_MAP = {"anxiety": "anxiety_constriction", "trapped": "trapped_cage", "shame": "shadow_self"}
KEYWORD_MAP = [(("控制", "牵", "关系", "control"), "red_string_control"), (("背", "压力", "期待", "burden", "boulder"), "burden_boulder"), (("冲突", "自己", "逃", "conflict"), "inner_conflict"), (("讨好", "面具", "pleaser"), "people_pleaser_mask"), (("边界", "boundary"), "boundary_intrusion"), (("笼", "困", "trapped"), "trapped_cage")]


def route_item(item: VisualAssetSourceItem, options: RoutingOptions) -> VisualAssetRoute:
    sem = item.semantic
    if sem.templateId:
        return _make(sem.templateId, 0.99, "explicit_template", False, options)
    if sem.visualIntent and sem.visualIntent in VISUAL_INTENT_MAP:
        return _make(VISUAL_INTENT_MAP[sem.visualIntent], 0.95, "explicit_visual_intent", False, options)
    if sem.topic and sem.topic in TOPIC_MAP:
        return _make(TOPIC_MAP[sem.topic], 0.86, "semantic_topic", False, options)
    if sem.emotion and sem.emotion in EMOTION_MAP:
        return _make(EMOTION_MAP[sem.emotion], 0.75, "semantic_emotion", False, options)
    keyword = _keyword_route(item.text, options)
    if keyword:
        return keyword
    if sem.actors >= 2:
        return _make("generic_two_person_relation", 0.62, "actor_fallback", True, options)
    return _make("generic_symbolic_pressure", 0.55, "generic_fallback", True, options)


def _keyword_route(text: str, options: RoutingOptions) -> VisualAssetRoute | None:
    lower = text.lower()
    for words, template_id in KEYWORD_MAP:
        if any(word in lower for word in words):
            return _make(template_id, 0.70, "keyword", False, options)
    return None


def _make(template_id: str, confidence: float, reason: str, fallback: bool, options: RoutingOptions) -> VisualAssetRoute:
    if template_id not in TEMPLATES:
        template_id, confidence, fallback, reason = "generic_symbolic_pressure", 0.0, True, "unknown_template"
    needs_review = confidence < options.minimumConfidence and options.lowConfidencePolicy == "needs_review"
    if needs_review:
        fallback = False
    template = TEMPLATES[template_id]
    return VisualAssetRoute(templateId=template_id, templateVersion=template.template_version, confidence=confidence, parameters=template.validate_parameters({}), fallbackUsed=fallback, needsReview=needs_review, reason=reason)
