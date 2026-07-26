from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import primitives as p


@dataclass(frozen=True)
class StickmanTemplate:
    template_id: str
    draw: Callable
    template_version: str = "0.1.0"
    supported_actor_count: tuple[int, ...] = (1, 2)
    parameter_schema: dict = field(default_factory=dict)
    default_composition: dict = field(default_factory=lambda: {"anchor": "center", "recommendedScale": 0.9, "safeArea": "center"})
    default_motion_hint: dict = field(default_factory=lambda: {"type": "slow_zoom_in", "strength": 0.06})

    def validate_parameters(self, params: dict) -> dict:
        allowed = self.parameter_schema or BASE_SCHEMA
        clean = {}
        for key, spec in allowed.items():
            value = params.get(key, spec.get("default"))
            if spec["type"] == "number":
                value = max(spec["min"], min(spec["max"], float(value)))
            elif spec["type"] == "integer":
                value = max(spec["min"], min(spec["max"], int(value)))
            elif spec["type"] == "enum" and value not in spec["values"]:
                value = spec["default"]
            clean[key] = value
        return clean


BASE_SCHEMA = {
    "actors": {"type": "integer", "min": 1, "max": 4, "default": 1},
    "tension": {"type": "number", "min": 0.0, "max": 1.0, "default": 0.7},
    "direction": {"type": "enum", "values": ["left", "right", "center"], "default": "center"},
}


def _sw(style):
    return style.stroke, style.stroke_width


def red_string_control(g, style, params):
    s, w = _sw(style); p.stick_person(g, 360, 760, 1.25, "right", "pull_right", s, w); p.stick_person(g, 760, 790, 1.15, "left", "pull_left", s, w); p.control_line(g, 455, 900, 665, 895, params.get("tension", 0.8), s, w); p.rule_frame(g, 250, 1010, 580, 190, s, w, 0.85)


def relationship_tug(g, style, params):
    s, w = _sw(style); p.stick_person(g, 310, 800, 1.15, "right", "pull_left", s, w); p.stick_person(g, 790, 800, 1.15, "left", "pull_right", s, w); p.rope(g, [(410, 930), (540, 890), (670, 930)], s, w)


def people_pleaser_mask(g, style, params):
    s, w = _sw(style); p.stick_person(g, 540, 820, 1.25, "right", "neutral", s, w); p.mask(g, 540, 620, 1.25, s, w); p.crowd(g, 540, 1120, 0.9, s, w, 0.55)


def boundary_intrusion(g, style, params):
    s, w = _sw(style); p.boundary_circle(g, 540, 820, 280, s, w); p.stick_person(g, 500, 760, 1.05, "right", "neutral", s, w); p.stick_person(g, 830, 780, 1.0, "left", "reaching", s, w); p.arrow(g, 780, 850, 640, 850, s, w)


def inner_conflict(g, style, params):
    s, w = _sw(style); p.stick_person(g, 390, 800, 1.1, "left", "escaping", s, w); p.stick_person(g, 690, 800, 1.1, "right", "pull_right", s, w); p.crack(g, 540, 890, 1.45, s, w)


def anxiety_constriction(g, style, params):
    s, w = _sw(style); p.stick_person(g, 540, 820, 1.1, "right", "trapped", s, w)
    for r in (155, 215, 275): p.ellipse(g, 540, 890, r, r * 0.62, s, w * 0.8, opacity=0.9)


def burden_boulder(g, style, params):
    s, w = _sw(style); p.stick_person(g, 540, 870, 1.1, "right", "burdened", s, w); p.boulder(g, 610, 640, 1.15, s, w); p.shadow(g, 540, 1190, 1.15, s, w)


def evidence_mountain(g, style, params):
    s, w = _sw(style); p.stick_person(g, 310, 900, 0.95, "right", "reaching", s, w)
    for i in range(5): p.evidence_stack(g, 640, 1120 - i * 115, 0.75 + i * 0.08, s, w)


def approval_chase(g, style, params):
    s, w = _sw(style); p.stick_person(g, 360, 860, 1.0, "right", "reaching", s, w); p.heart(g, 760, 700, 0.75, s, w); p.arrow(g, 455, 850, 690, 740, s, w)


def approach_retreat(g, style, params):
    s, w = _sw(style); p.stick_person(g, 380, 820, 1.0, "right", "reaching", s, w); p.stick_person(g, 735, 820, 1.0, "left", "escaping", s, w); p.arrow(g, 475, 880, 625, 880, s, w); p.arrow(g, 680, 1015, 520, 1015, s, w)


def trapped_cage(g, style, params):
    s, w = _sw(style); p.cage(g, 345, 520, 390, 620, s, w); p.stick_person(g, 540, 790, 1.05, "right", "trapped", s, w)


def face_reading(g, style, params):
    s, w = _sw(style); p.stick_person(g, 360, 840, 1.0, "right", "neutral", s, w); p.mask(g, 735, 690, 1.25, s, w); p.arrow(g, 455, 745, 640, 690, s, w)


def shadow_self(g, style, params):
    s, w = _sw(style); p.stick_person(g, 440, 820, 1.1, "right", "neutral", s, w); p.stick_person(g, 675, 850, 1.25, "left", "conflicted", s, w, 0.35); p.shadow(g, 650, 1190, 1.5, s, w, 0.35)


def comparison_trap(g, style, params):
    s, w = _sw(style); p.comparison_scale(g, 540, 735, 1.0, s, w); p.stick_person(g, 335, 960, 0.75, "right", "neutral", s, w); p.stick_person(g, 760, 900, 1.15, "left", "neutral", s, w)


def cut_control_line(g, style, params):
    s, w = _sw(style); p.stick_person(g, 350, 820, 1.0, "right", "neutral", s, w); p.stick_person(g, 760, 820, 1.0, "left", "pull_left", s, w); p.control_line(g, 435, 910, 675, 910, 0.6, s, w, 0.75); p.scissors(g, 545, 855, 0.95, s, w)


def escape_enclosure(g, style, params):
    s, w = _sw(style); p.wall(g, 300, 570, 380, 520, s, w, 0.75); p.stick_person(g, 730, 820, 1.05, "right", "escaping", s, w); p.arrow(g, 600, 900, 800, 820, s, w)


def generic_single_person(g, style, params):
    s, w = _sw(style); p.stick_person(g, 540, 820, 1.2, "right", "neutral", s, w); p.boundary_circle(g, 540, 850, 300, s, w, 0.5)


def generic_two_person_relation(g, style, params):
    s, w = _sw(style); p.stick_person(g, 380, 820, 1.05, "right", "neutral", s, w); p.stick_person(g, 710, 820, 1.05, "left", "neutral", s, w); p.control_line(g, 470, 900, 620, 900, 0.45, s, w)


def generic_symbolic_pressure(g, style, params):
    s, w = _sw(style); p.stick_person(g, 540, 900, 1.05, "right", "burdened", s, w); p.spikes(g, 540, 610, 7, 1.2, s, w); p.boulder(g, 540, 710, 0.75, s, w, 0.6)


CORE_TEMPLATE_IDS = ["red_string_control", "relationship_tug", "people_pleaser_mask", "boundary_intrusion", "inner_conflict", "anxiety_constriction", "burden_boulder", "evidence_mountain", "approval_chase", "approach_retreat", "trapped_cage", "face_reading", "shadow_self", "comparison_trap", "cut_control_line", "escape_enclosure"]
FALLBACK_TEMPLATE_IDS = ["generic_single_person", "generic_two_person_relation", "generic_symbolic_pressure"]
_DRAW = {name: globals()[name] for name in CORE_TEMPLATE_IDS + FALLBACK_TEMPLATE_IDS}
TEMPLATES = {name: StickmanTemplate(name, draw, supported_actor_count=(1,) if name in {"people_pleaser_mask", "anxiety_constriction", "burden_boulder", "trapped_cage", "shadow_self", "generic_single_person", "generic_symbolic_pressure"} else (1, 2)) for name, draw in _DRAW.items()}
