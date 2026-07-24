from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass

ET.register_namespace("", "http://www.w3.org/2000/svg")


@dataclass(frozen=True)
class FigureScale:
    head_radius: float = 42
    torso: float = 155
    arm: float = 105
    leg: float = 125
    person_gap: float = 320


def attrs(stroke="#FFFFFF", stroke_width=12, fill="none", opacity=1.0):
    return {"stroke": stroke, "stroke-width": str(round(stroke_width, 3)), "stroke-linecap": "round", "stroke-linejoin": "round", "fill": fill, "opacity": str(round(opacity, 3))}


def pt(x, y) -> str:
    return f"{round(x, 3)},{round(y, 3)}"


def line(g, x1, y1, x2, y2, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    ET.SubElement(g, "line", {"x1": str(round(x1, 3)), "y1": str(round(y1, 3)), "x2": str(round(x2, 3)), "y2": str(round(y2, 3)), **attrs(stroke, stroke_width, opacity=opacity)})


def path(g, d, stroke="#FFFFFF", stroke_width=12, fill="none", opacity=1.0):
    ET.SubElement(g, "path", {"d": d, **attrs(stroke, stroke_width, fill, opacity)})


def circle(g, cx, cy, r, stroke="#FFFFFF", stroke_width=12, fill="none", opacity=1.0):
    ET.SubElement(g, "circle", {"cx": str(round(cx, 3)), "cy": str(round(cy, 3)), "r": str(round(r, 3)), **attrs(stroke, stroke_width, fill, opacity)})


def ellipse(g, cx, cy, rx, ry, stroke="#FFFFFF", stroke_width=12, fill="none", opacity=1.0):
    ET.SubElement(g, "ellipse", {"cx": str(round(cx, 3)), "cy": str(round(cy, 3)), "rx": str(round(rx, 3)), "ry": str(round(ry, 3)), **attrs(stroke, stroke_width, fill, opacity)})


def rect(g, x, y, width, height, stroke="#FFFFFF", stroke_width=12, fill="none", opacity=1.0, rx=0):
    a = {"x": str(round(x, 3)), "y": str(round(y, 3)), "width": str(round(width, 3)), "height": str(round(height, 3)), **attrs(stroke, stroke_width, fill, opacity)}
    if rx:
        a["rx"] = str(round(rx, 3))
    ET.SubElement(g, "rect", a)


def polyline(g, points, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    ET.SubElement(g, "polyline", {"points": " ".join(pt(x, y) for x, y in points), **attrs(stroke, stroke_width, opacity=opacity)})


def polygon(g, points, stroke="#FFFFFF", stroke_width=12, fill="none", opacity=1.0):
    ET.SubElement(g, "polygon", {"points": " ".join(pt(x, y) for x, y in points), **attrs(stroke, stroke_width, fill, opacity)})


def head(g, x, y, scale=1.0, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    circle(g, x, y, FigureScale().head_radius * scale, stroke, stroke_width, opacity=opacity)


def torso(g, x, y, scale=1.0, lean=0.0, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    fs = FigureScale()
    line(g, x, y + fs.head_radius * scale, x + lean * scale, y + (fs.head_radius + fs.torso) * scale, stroke, stroke_width, opacity)


def arm(g, shoulder, elbow, hand, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    polyline(g, [shoulder, elbow, hand], stroke, stroke_width, opacity)


def leg(g, hip, knee, foot, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    polyline(g, [hip, knee, foot], stroke, stroke_width, opacity)


POSES = {
    "neutral": {"arm": (-70, 70), "leg": (-55, 55), "lean": 0},
    "pull_left": {"arm": (-105, 35), "leg": (-80, 40), "lean": -25},
    "pull_right": {"arm": (-35, 105), "leg": (-40, 80), "lean": 25},
    "burdened": {"arm": (-55, 55), "leg": (-35, 35), "lean": 18},
    "conflicted": {"arm": (-95, 95), "leg": (-65, 65), "lean": 0},
    "trapped": {"arm": (-45, 45), "leg": (-30, 30), "lean": 0},
    "reaching": {"arm": (-35, 125), "leg": (-50, 70), "lean": 12},
    "escaping": {"arm": (-115, 75), "leg": (-105, 115), "lean": -30},
}


def stick_person(g, x, y, scale=1.0, facing="right", pose="neutral", stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    fs = FigureScale()
    p = POSES.get(pose, POSES["neutral"])
    mirror = -1 if facing == "left" else 1
    lean = p["lean"] * mirror
    head(g, x, y, scale, stroke, stroke_width, opacity)
    torso(g, x, y, scale, lean, stroke, stroke_width, opacity)
    shoulder = (x, y + fs.head_radius * scale + 30 * scale)
    hip = (x + lean * scale, y + (fs.head_radius + fs.torso) * scale)
    for value in p["arm"]:
        arm(g, shoulder, (x + value * mirror * scale, shoulder[1] + 55 * scale), (x + (value + (25 if value > 0 else -25)) * mirror * scale, shoulder[1] + 115 * scale), stroke, stroke_width, opacity)
    for value in p["leg"]:
        leg(g, hip, (x + value * mirror * scale, hip[1] + 80 * scale), (x + (value + (25 if value > 0 else -25)) * mirror * scale, hip[1] + fs.leg * scale), stroke, stroke_width, opacity)


def person_pose(*args, **kwargs):
    return stick_person(*args, **kwargs)


def mask(g, x, y, scale=1.0, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    path(g, f"M {pt(x-75*scale,y)} Q {pt(x,y+70*scale)} {pt(x+75*scale,y)} Q {pt(x,y+25*scale)} {pt(x-75*scale,y)}", stroke, stroke_width, opacity=opacity)
    circle(g, x - 28 * scale, y + 12 * scale, 6 * scale, stroke, max(2, stroke_width / 2), fill=stroke, opacity=opacity)
    circle(g, x + 28 * scale, y + 12 * scale, 6 * scale, stroke, max(2, stroke_width / 2), fill=stroke, opacity=opacity)


def rope(g, points, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    polyline(g, points, stroke, stroke_width, opacity)


def control_line(g, x1, y1, x2, y2, tension=0.7, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    path(g, f"M {pt(x1,y1)} Q {pt((x1+x2)/2,y1+(1-tension)*120)} {pt(x2,y2)}", stroke, stroke_width, opacity=opacity)


def cage(g, x, y, width, height, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    rect(g, x, y, width, height, stroke, stroke_width, opacity=opacity, rx=18)
    for i in range(1, 4):
        line(g, x + width * i / 4, y, x + width * i / 4, y + height, stroke, stroke_width * 0.75, opacity)
    line(g, x, y + height / 2, x + width, y + height / 2, stroke, stroke_width * 0.75, opacity)


def wall(g, x, y, width, height, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    rect(g, x, y, width, height, stroke, stroke_width, opacity=opacity)
    for i in range(1, 4):
        line(g, x, y + height*i/4, x + width, y + height*i/4, stroke, stroke_width*0.45, opacity)


def boulder(g, x, y, scale=1.0, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    path(g, f"M {pt(x-120*scale,y+15*scale)} Q {pt(x-95*scale,y-115*scale)} {pt(x+25*scale,y-120*scale)} Q {pt(x+150*scale,y-75*scale)} {pt(x+135*scale,y+55*scale)} Q {pt(x+10*scale,y+110*scale)} {pt(x-120*scale,y+15*scale)}", stroke, stroke_width, opacity=opacity)


def evidence_stack(g, x, y, scale=1.0, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    for i in range(4):
        rect(g, x - 95*scale + i*10*scale, y - i*42*scale, 190*scale, 32*scale, stroke, stroke_width*0.7, opacity=opacity, rx=4)


def arrow(g, x1, y1, x2, y2, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    line(g, x1, y1, x2, y2, stroke, stroke_width, opacity)
    angle = math.atan2(y2 - y1, x2 - x1)
    for delta in (2.5, -2.5):
        line(g, x2, y2, x2 - 45 * math.cos(angle + delta), y2 - 45 * math.sin(angle + delta), stroke, stroke_width, opacity)


def crack(g, x, y, scale=1.0, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    polyline(g, [(x, y-90*scale), (x-30*scale, y-25*scale), (x+22*scale, y+18*scale), (x-12*scale, y+95*scale)], stroke, stroke_width, opacity)


def shadow(g, x, y, scale=1.0, stroke="#FFFFFF", stroke_width=12, opacity=0.35):
    ellipse(g, x, y, 115 * scale, 36 * scale, stroke, stroke_width * 0.7, opacity=opacity)


def heart(g, x, y, scale=1.0, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    path(g, f"M {pt(x,y+70*scale)} C {pt(x-120*scale,y)} {pt(x-65*scale,y-95*scale)} {pt(x,y-35*scale)} C {pt(x+65*scale,y-95*scale)} {pt(x+120*scale,y)} {pt(x,y+70*scale)}", stroke, stroke_width, opacity=opacity)


def spikes(g, x, y, count=7, scale=1.0, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    for i in range(count):
        xx = x + (i - (count - 1) / 2) * 42 * scale
        polygon(g, [(xx-18*scale, y+45*scale), (xx, y-45*scale), (xx+18*scale, y+45*scale)], stroke, stroke_width*0.55, opacity=opacity)


def boundary_circle(g, x, y, r, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    circle(g, x, y, r, stroke, stroke_width, opacity=opacity)


def comparison_scale(g, x, y, scale=1.0, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    line(g, x, y-110*scale, x, y+90*scale, stroke, stroke_width, opacity)
    line(g, x-150*scale, y, x+150*scale, y, stroke, stroke_width, opacity)
    polyline(g, [(x-150*scale,y), (x-220*scale,y+85*scale), (x-80*scale,y+85*scale), (x-150*scale,y)], stroke, stroke_width*0.7, opacity)
    polyline(g, [(x+150*scale,y), (x+80*scale,y+85*scale), (x+220*scale,y+85*scale), (x+150*scale,y)], stroke, stroke_width*0.7, opacity)


def crowd(g, x, y, scale=1.0, stroke="#FFFFFF", stroke_width=12, opacity=0.75):
    for i in range(5):
        stick_person(g, x + (i - 2) * 95 * scale, y + (i % 2) * 30 * scale, scale * 0.45, "right", "neutral", stroke, stroke_width * 0.6, opacity)


def rule_frame(g, x, y, width, height, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    rect(g, x, y, width, height, stroke, stroke_width, opacity=opacity, rx=14)
    line(g, x+35, y+70, x+width-35, y+70, stroke, stroke_width*0.65, opacity)


def scissors(g, x, y, scale=1.0, stroke="#FFFFFF", stroke_width=12, opacity=1.0):
    circle(g, x-42*scale, y+42*scale, 28*scale, stroke, stroke_width*0.7, opacity=opacity)
    circle(g, x+42*scale, y+42*scale, 28*scale, stroke, stroke_width*0.7, opacity=opacity)
    line(g, x-18*scale, y+22*scale, x+92*scale, y-92*scale, stroke, stroke_width, opacity)
    line(g, x+18*scale, y+22*scale, x-92*scale, y-92*scale, stroke, stroke_width, opacity)


PRIMITIVE_NAMES = {"stick_person", "head", "torso", "arm", "leg", "person_pose", "mask", "rope", "control_line", "cage", "wall", "boulder", "evidence_stack", "arrow", "crack", "shadow", "heart", "spikes", "boundary_circle", "comparison_scale", "crowd", "rule_frame", "scissors"}
