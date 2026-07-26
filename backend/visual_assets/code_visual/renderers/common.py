from __future__ import annotations
from ..internal import SemanticSceneGraph, StyleContract
from ..svg import circle, dot, group, line, path, polygon, rect


def safe_zone(style: StyleContract) -> str:
    # Invisible geometry retained for downstream layout inspection.
    if style.subtitle_safe_zone == "none":
        return ""
    y = 1390 if style.subtitle_safe_zone == "bottom_24" else 1320
    return group("subtitle_safe_zone", rect(80,y,920,1920-y-80,style,rx=24,width=1,opacity=0))


def ip_motif(scene: SemanticSceneGraph, style: StyleContract) -> str:
    fg=style.palette.foreground; acc=style.palette.accent; muted=style.palette.muted
    pack=scene.ip_pack
    if pack == "xuanqi":
        door=path("M 465 310 V520 M 615 310 V520 M 465 310 Q 540 220 615 310",style,width=style.stroke.detail,color=muted,opacity=.48)
        seal=circle(540,265,28,style,width=style.stroke.detail,color=acc,opacity=.7)+path("M 525 265 H555 M 540 250 V280",style,width=style.stroke.detail,color=acc,opacity=.7)
        return group("ip_motif",door+seal)
    if pack == "huicewolf":
        trail="".join(circle(170+i*46,360+i*28,10+i%2*3,style,width=0,color=muted,fill=muted,opacity=.45) for i in range(4))
        wind=path("M 760 300 C 850 250 920 290 960 245",style,width=style.stroke.detail,color=acc,opacity=.55)
        return group("ip_motif",trail+wind)
    if pack == "ayin":
        eyes=ellipse_eye(890,300,style)
        moon=path("M 160 255 Q 230 330 300 250 Q 225 300 160 255 Z",style,width=style.stroke.detail,color=muted,fill="none",opacity=.45)
        return group("ip_motif",eyes+moon)
    return ""


def ellipse_eye(cx: float, cy: float, style: StyleContract) -> str:
    eye=path(f"M {cx-55} {cy} Q {cx} {cy-42} {cx+55} {cy} Q {cx} {cy+42} {cx-55} {cy} Z",style,width=style.stroke.detail,color=style.palette.muted,opacity=.58)
    eye+=dot(cx,cy,10,style,color=style.palette.accent,opacity=.75)
    return eye


def wrap(body: str, scene: SemanticSceneGraph, style: StyleContract, renderer_id: str, template_id: str, layers: list[str]) -> str:
    from ..svg import svg_document
    meta={"renderer":renderer_id,"template":template_id,"scene":scene.scene_id,"theme":style.theme_mode,"pack":scene.ip_pack}
    return svg_document(group("scene_root",body+ip_motif(scene,style)+safe_zone(style)),style,meta)
