from __future__ import annotations
from ..internal import SemanticSceneGraph, StyleContract
from ..svg import arrow_head,circle,dot,group,line,path,rect
from .common import wrap
renderer_id="mechanism_diagram"; renderer_version="0.4.0"

def node(cx,cy,r,style,accent=False,opacity=1):
    c=style.palette.accent if accent else style.palette.foreground
    return circle(cx,cy,r,style,width=style.stroke.secondary,color=c,opacity=opacity)+dot(cx,cy,r*.18,style,color=c,opacity=opacity)

def link(x1,y1,x2,y2,style,accent=False,dash=None,opacity=1):
    c=style.palette.accent if accent else style.palette.secondary
    return line(x1,y1,x2,y2,style,width=style.stroke.secondary,color=c,dash=dash,opacity=opacity)+arrow_head(x2,y2,0 if x2>=x1 else 180,30,style,color=c)

def control(scene,style):
    controller=node(260,750,80,style,accent=True); target=node(820,1040,70,style)
    lever=path("M 350 760 C 500 650 590 990 740 1000",style,width=18,color=style.palette.accent)
    loop=path("M 790 940 C 650 820 570 1040 720 1180",style,width=style.stroke.secondary,color=style.palette.muted,dash="18 18")+arrow_head(720,1180,110,32,style,color=style.palette.muted)
    boxes=rect(160,610,200,280,style,rx=40,width=style.stroke.detail,color=style.palette.muted,opacity=.5)+rect(720,910,200,260,style,rx=40,width=style.stroke.detail,color=style.palette.muted,opacity=.5)
    return group("environment_primary",boxes+loop)+group("symbol_primary",lever)+group("actor_primary",controller)+group("actor_secondary",target),"control_loop",["environment_primary","symbol_primary","actor_primary","actor_secondary","scene_root"]

def anxiety(scene,style):
    center=node(540,970,70,style,accent=True)
    orbit=""; positions=[(260,590),(540,470),(820,590),(880,980),(740,1260),(340,1260),(200,980)]
    for x,y in positions:
        orbit+=node(x,y,42,style,opacity=.75)+link(x,y,500+(x-540)*.15,930+(y-970)*.15,style,opacity=.55)
    ring=circle(540,970,390,style,width=style.stroke.detail,color=style.palette.muted,opacity=.35)
    return group("environment_primary",ring+orbit)+group("actor_primary",center)+group("symbol_primary",""),"anxiety_feedback",["environment_primary","symbol_primary","scene_root"]

def people(scene,style):
    self_node=node(540,1120,72,style,accent=True)
    approval_nodes=""; lines=""
    for x,y in [(210,570),(540,440),(870,570)]:
        approval_nodes+=node(x,y,52,style)
        lines+=link(540,1050,x,y+60,style,opacity=.7)
    drain=path("M 500 1210 C 480 1350 600 1390 590 1510",style,width=18,color=style.palette.accent)+arrow_head(590,1510,80,35,style,color=style.palette.accent)
    return group("opposing_force",approval_nodes)+group("environment_primary",lines)+group("symbol_primary",drain)+group("actor_primary",self_node),"approval_drain",["opposing_force","environment_primary","symbol_primary","actor_primary","scene_root"]

def evidence(scene,style):
    start=node(180,1110,56,style); end=node(900,650,70,style,accent=True)
    stairs=""; x,y=300,1180
    for i in range(5):
        stairs+=rect(x+i*110,y-i*120,150,90,style,rx=14,width=style.stroke.secondary,color=style.palette.foreground)
    raise_line=path("M 280 1050 C 450 930 620 850 820 700",style,width=style.stroke.secondary,color=style.palette.accent)+arrow_head(820,700,-35,35,style,color=style.palette.accent)
    reset=path("M 870 760 C 980 920 890 1270 610 1370 C 400 1440 200 1340 160 1190",style,width=style.stroke.detail,color=style.palette.muted,dash="20 20")+arrow_head(160,1190,-110,30,style,color=style.palette.muted)
    return group("actor_primary",start)+group("actor_secondary",end)+group("symbol_primary",stairs+raise_line)+group("environment_primary",reset),"rising_threshold",["actor_primary","actor_secondary","symbol_primary","environment_primary","scene_root"]

def awakening(scene,style):
    chain=""; pts=[(170,1050),(350,900),(540,1000),(700,780),(900,620)]
    for i,(x,y) in enumerate(pts): chain+=node(x,y,45,style,accent=i==2)+ (link(x,y,pts[i+1][0]-48,pts[i+1][1],style,accent=i==2) if i<len(pts)-1 else "")
    breakmark=path("M 515 935 L 560 1020 M 560 935 L 515 1020",style,width=style.stroke.primary,color=style.palette.accent)
    openpath=path("M 540 1000 C 620 1160 760 1260 960 1240",style,width=style.stroke.primary,color=style.palette.foreground)+arrow_head(960,1240,0,38,style)
    return group("environment_primary",chain)+group("symbol_primary",breakmark)+group("symbol_secondary",openpath),"break_feedback_loop",["environment_primary","symbol_primary","symbol_secondary","scene_root"]

def hidden(scene,style):
    grid="".join(line(x,460,x,1320,style,width=style.stroke.detail,color=style.palette.muted,opacity=.2) for x in range(180,901,120))+"".join(line(180,y,900,y,style,width=style.stroke.detail,color=style.palette.muted,opacity=.2) for y in range(480,1321,120))
    false=path("M 220 1240 L 360 1120 L 500 1180 L 620 900 L 780 980",style,width=style.stroke.secondary,color=style.palette.secondary,dash="18 18",opacity=.65)
    true=path("M 220 1240 C 400 1250 510 1030 620 960 C 740 880 800 650 930 540",style,width=style.stroke.primary,color=style.palette.accent)+arrow_head(930,540,-35,36,style,color=style.palette.accent)
    key=node(930,540,46,style,accent=True)
    cat_hint=circle(220,1240,34,style,width=style.stroke.detail,color=style.palette.foreground)+dot(212,1234,4,style,color=style.palette.accent)+dot(228,1234,4,style,color=style.palette.accent)
    return group("actor_primary",cat_hint)+group("environment_primary",grid+false)+group("symbol_primary",true+key),"hidden_route_map",["environment_primary","symbol_primary","scene_root"]

def trap_detection(scene,style):
    wolf=node(220,1100,58,style,accent=True)
    scent=path("M 300 1060 C 430 1000 520 990 640 1010 C 760 1030 830 1025 920 980",style,width=style.stroke.secondary,color=style.palette.secondary,dash="16 16")
    bait=node(940,970,42,style,accent=True)
    field=rect(760,860,230,230,style,rx=22,width=style.stroke.detail,color=style.palette.muted,opacity=.55)+line(760,975,990,975,style,width=style.stroke.secondary,color=style.palette.accent,dash="18 18",opacity=.8)
    safe=path("M 210 1185 C 300 1280 430 1340 600 1310",style,width=style.stroke.primary,color=style.palette.foreground)+arrow_head(600,1310,0,38,style)
    return group("actor_primary",wolf)+group("environment_primary",field)+group("symbol_primary",scent+bait)+group("symbol_secondary",safe),"predator_risk_map",["actor_primary","environment_primary","symbol_primary","symbol_secondary","scene_root"]
MAP={"control":control,"anxiety":anxiety,"people_pleasing":people,"evidence":evidence,"awakening":awakening,"hidden_path":hidden,"trap_detection":trap_detection}
def render_svg(scene:SemanticSceneGraph,style:StyleContract):
    body,t,l=MAP[scene.visual_family](scene,style); return wrap(body,scene,style,renderer_id,t,l),t,l
