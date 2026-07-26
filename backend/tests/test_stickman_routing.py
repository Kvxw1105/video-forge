from visual_assets.contracts import RoutingOptions, VisualAssetSourceItem
from visual_assets.stickman.routing import route_item


def item(text="x", semantic=None):
    return VisualAssetSourceItem(id="s1", order=1, start=0, end=1, text=text, semantic=semantic or {})


def test_routing_priority_explicit_visual_intent_over_keyword():
    route = route_item(item("背着压力", {"visualIntent": "red_string_pull", "actors": 2}), RoutingOptions())
    assert route.templateId == "red_string_control"


def test_routing_topic_emotion_keyword_and_fallback():
    assert route_item(item("x", {"topic": "relationship_control"}), RoutingOptions()).templateId == "red_string_control"
    assert route_item(item("x", {"emotion": "anxiety"}), RoutingOptions()).templateId == "anxiety_constriction"
    assert route_item(item("他背着整个家庭期待"), RoutingOptions()).templateId == "burden_boulder"
    low = route_item(item("unknown", {"actors": 1}), RoutingOptions(minimumConfidence=0.9))
    assert low.needsReview is True
    assert low.templateId == "generic_symbolic_pressure"
