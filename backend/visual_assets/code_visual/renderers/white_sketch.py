from __future__ import annotations
from ..internal import SemanticSceneGraph, StyleContract
from ..svg import arrow_head, circle, dot, ellipse, figure, group, line, path, polygon, rect
from ..actors import cat_actor, crowd_actor, human_actor, wolf_actor
from .common import wrap

renderer_id="white_sketch"
renderer_version="0.4.0"


def control(scene,style):
    left=human_actor(335,990,.92,"pull_right",style,"actor_primary",facing="right")
    right=human_actor(755,1000,.92,"withdraw",style,"actor_secondary",facing="left")
    rope=path("M 450 820 C 510 735 590 925 665 820",style,width=21,color=style.palette.accent)
    knot=circle(555,830,24,style,width=style.stroke.secondary,color=style.palette.accent)
    tension=path("M 530 745 L 555 690 M 580 755 L 620 710",style,width=style.stroke.detail,color=style.palette.muted,opacity=.7)
    floor=path("M 170 1320 Q 540 1265 910 1320",style,width=style.stroke.detail,color=style.palette.muted,opacity=.35)
    body=group("actors",left+right)+group("symbol_primary",rope+knot+tension)+group("environment_primary",floor)
    return body,"control_tension",["actor_primary","actor_secondary","symbol_primary","environment_primary","scene_root"]


def anxiety(scene,style):
    actor = crowd_actor(540,1080,1.0,style,"actor_primary") if scene.subject.type=="group" or scene.metadata.get("actor_pack")=="crowd" else human_actor(540,1050,.9,"crouch",style,"actor_primary",facing="right")
    walls=path("M 120 470 V1320 Q 250 1220 350 1080",style,width=19)+path("M 960 470 V1320 Q 830 1220 730 1080",style,width=19)
    ceiling=path("M 265 520 Q 540 370 815 520",style,width=style.stroke.secondary,color=style.palette.secondary,opacity=.6)
    arrows=line(170,820,345,820,style,width=style.stroke.secondary,color=style.palette.muted,opacity=.7)+arrow_head(345,820,0,36,style,color=style.palette.muted)
    arrows+=line(910,820,735,820,style,width=style.stroke.secondary,color=style.palette.muted,opacity=.7)+arrow_head(735,820,180,36,style,color=style.palette.muted)
    ring=ellipse(540,1040,265,365,style,width=style.stroke.detail,color=style.palette.muted,opacity=.26)
    body=group("environment_primary",walls+ceiling+arrows+ring)+actor
    return body,"anxiety_constriction",["actor_primary","environment_primary","scene_root"]


def people_pleasing(scene,style):
    actor=human_actor(380,1050,.9,"reach",style,"actor_primary",facing="right")
    mx,my=735,700
    mask=path(f"M {mx-120} {my-55} Q {mx} {my-150} {mx+120} {my-55} Q {mx+90} {my+150} {mx} {my+180} Q {mx-90} {my+150} {mx-120} {my-55} Z",style,width=style.stroke.primary)
    mask+=dot(mx-38,my,8,style)+dot(mx+38,my,8,style)+path(f"M {mx-48} {my+82} Q {mx} {my+120} {mx+48} {my+82}",style,width=style.stroke.secondary)
    eyes="".join(path(f"M {x-45} {y} Q {x} {y-30} {x+45} {y} Q {x} {y+30} {x-45} {y} Z",style,width=style.stroke.detail,color=style.palette.muted,opacity=.65)+dot(x,y,7,style,color=style.palette.accent,opacity=.8) for x,y in [(240,500),(510,420),(830,470),(920,700)])
    fading=path("M 250 690 Q 380 560 510 690",style,width=style.stroke.detail,color=style.palette.muted,opacity=.26,dash="18 22")
    body=actor+group("symbol_primary",mask)+group("opposing_force",eyes)+group("environment_primary",fading)
    return body,"people_pleaser_mask",["actor_primary","symbol_primary","opposing_force","environment_primary","scene_root"]


def evidence(scene,style):
    actor=human_actor(310,1090,.82,"reach",style,"actor_primary",facing="right")
    cards=""
    for i in range(6):
        x=540+(i%2)*32; y=1200-i*128; w=300-(i%3)*25
        cards+=rect(x,y,w,100,style,rx=12,width=style.stroke.secondary,color=style.palette.foreground)
        cards+=line(x+30,y+35,x+w-28,y+35,style,width=style.stroke.detail,color=style.palette.muted,opacity=.65)
    gate=path("M 850 520 V1260 M 980 520 V1260 M 850 520 Q 915 435 980 520",style,width=style.stroke.primary)
    threshold=line(850,890,980,890,style,width=style.stroke.secondary,color=style.palette.accent)
    loop=path("M 820 540 C 735 600 735 1210 820 1290",style,width=style.stroke.detail,color=style.palette.muted,opacity=.5,dash="18 18")+arrow_head(820,1290,125,36,style,color=style.palette.muted)
    body=actor+group("symbol_primary",cards)+group("environment_primary",gate+threshold+loop)
    return body,"evidence_gate",["actor_primary","symbol_primary","environment_primary","scene_root"]


def awakening(scene,style):
    actor=human_actor(490,1050,.92,"cut",style,"actor_primary",facing="right")
    cord1=path("M 80 610 C 260 640 400 730 590 840",style,width=22,color=style.palette.accent)
    cord2=path("M 680 900 C 800 980 900 1110 1030 1210",style,width=22,color=style.palette.accent)
    scissors=path("M 590 790 L 695 900 M 700 790 L 590 900",style,width=style.stroke.secondary)+circle(575,770,28,style,width=style.stroke.detail)+circle(715,770,28,style,width=style.stroke.detail)
    rays="".join(line(646,850,646+dx,850+dy,style,width=style.stroke.detail,color=style.palette.secondary,opacity=.65) for dx,dy in [(-90,-80),(0,-125),(95,-75),(120,15),(-105,20)])
    door=path("M 790 520 H965 V1280 H790",style,width=style.stroke.primary)
    opening=polygon([(965,520),(1070,430),(1070,1370),(965,1280)],style,width=0,color=style.palette.secondary,fill=style.palette.secondary,opacity=.18)
    body=actor+group("symbol_primary",cord1+cord2+scissors)+group("symbol_secondary",rays)+group("environment_primary",door+opening)
    return body,"cut_and_open",["actor_primary","symbol_primary","symbol_secondary","environment_primary","scene_root"]


def hidden_path(scene,style):
    actor=cat_actor(330,1125,.84,style,"actor_primary",mode="contour",eye_glow=True)
    maze=path("M 120 450 H470 V720 H290 V990 H520 V1270 H120 Z M 600 450 H960 V780 H800 V1040 H980 V1320 H600",style,width=style.stroke.secondary,color=style.palette.secondary,opacity=.78)
    hidden=path("M 360 1250 C 520 1180 610 980 690 820 C 760 680 830 630 965 610",style,width=style.stroke.primary,color=style.palette.accent,dash="24 18")+arrow_head(965,610,-15,40,style,color=style.palette.accent)
    eyes=path("M 720 460 Q 790 405 860 460 Q 790 515 720 460 Z",style,width=style.stroke.detail,color=style.palette.muted,opacity=.7)+dot(790,460,10,style,color=style.palette.accent,opacity=.8)
    body=actor+group("environment_primary",maze)+group("symbol_primary",hidden)+group("opposing_force",eyes)
    return body,"hidden_path_cat",["actor_primary","environment_primary","symbol_primary","opposing_force","scene_root"]


def trap_detection(scene,style):
    actor=wolf_actor(350,1120,.86,style,"actor_primary",mode="contour")
    scent=path("M 640 960 C 705 920 750 915 818 950 C 875 980 915 1018 986 1002",style,width=style.stroke.detail,color=style.palette.secondary,opacity=.68,dash="18 16")
    bait=dot(982,1002,16,style,color=style.palette.accent,opacity=.92)+circle(982,1002,28,style,width=style.stroke.detail,color=style.palette.accent,opacity=.55)
    trap=rect(790,880,220,210,style,rx=12,width=style.stroke.secondary,color=style.palette.secondary,opacity=.7)+line(790,985,1010,985,style,width=style.stroke.detail,color=style.palette.accent,opacity=.85,dash="18 12")
    claws="".join(line(820+i*48,1090,800+i*48,1140,style,width=style.stroke.detail,color=style.palette.muted,opacity=.6) for i in range(4))
    alert=path("M 715 880 L 742 820 L 767 880 Z",style,width=style.stroke.detail,color=style.palette.accent,fill="none",opacity=.85)+line(742,842,742,866,style,width=style.stroke.detail,color=style.palette.accent,opacity=.85)
    body=actor+group("symbol_primary",scent+bait)+group("symbol_secondary",alert)+group("environment_primary",trap+claws)
    return body,"wolf_trap_detection",["actor_primary","symbol_primary","symbol_secondary","environment_primary","scene_root"]

MAP={"control":control,"anxiety":anxiety,"people_pleasing":people_pleasing,"evidence":evidence,"awakening":awakening,"hidden_path":hidden_path,"trap_detection":trap_detection}

def render_svg(scene:SemanticSceneGraph,style:StyleContract):
    body,template,layers=MAP[scene.visual_family](scene,style)
    return wrap(body,scene,style,renderer_id,template,layers),template,layers
