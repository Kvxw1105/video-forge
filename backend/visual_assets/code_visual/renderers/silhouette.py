from __future__ import annotations
from ..internal import SemanticSceneGraph, StyleContract
from ..svg import circle,dot,figure,group,line,path,polygon,rect
from ..actors import cat_actor, crowd_actor, wolf_actor
from .common import wrap
renderer_id="silhouette"; renderer_version="0.4.0"

def _fig(x,y,s,pose,style,gid,facing="right",opacity=1): return figure(x,y,s,pose,style,gid,mode="silhouette",facing=facing,opacity=opacity)

def control(scene,style):
    a=_fig(315,1040,.95,"pull_right",style,"actor_primary"); b=_fig(765,1040,.95,"withdraw",style,"actor_secondary",facing="left")
    hand=path("M 60 350 C 280 320 420 430 490 620 C 540 760 600 790 720 790",style,width=46,color=style.palette.foreground)
    rope=path("M 430 840 C 510 760 590 930 665 840",style,width=25,color=style.palette.accent)
    moon=circle(850,350,125,style,width=0,color=style.palette.secondary,fill=style.palette.secondary,opacity=.18)
    body=group("environment_primary",hand+moon)+group("symbol_primary",rope)+a+b
    return body,"giant_hand_control",["environment_primary","symbol_primary","actor_primary","actor_secondary","scene_root"]

def anxiety(scene,style):
    actor=crowd_actor(540,1130,.92,style,"actor_primary",mode="silhouette") if scene.subject.type=="group" or scene.metadata.get("actor_pack")=="crowd" else _fig(540,1110,.9,"crouch",style,"actor_primary")
    mountain=polygon([(90,1320),(330,720),(470,1080),(620,560),(970,1320)],style,width=0,color=style.palette.foreground,fill=style.palette.foreground,opacity=.18)
    slit=polygon([(470,1320),(540,720),(610,1320)],style,width=0,color=style.palette.accent,fill=style.palette.accent,opacity=.65)
    ceiling=polygon([(70,120),(1010,120),(1010,450),(760,520),(540,420),(290,530),(70,440)],style,width=0,color=style.palette.foreground,fill=style.palette.foreground,opacity=.12)
    return group("environment_primary",mountain+ceiling)+group("symbol_primary",slit)+actor,"pressure_valley",["environment_primary","symbol_primary","actor_primary","scene_root"]

def people(scene,style):
    actor=_fig(430,1120,.9,"reach",style,"actor_primary")
    mask=path("M 650 520 Q 790 390 930 520 Q 900 850 790 900 Q 680 850 650 520 Z",style,width=0,color=style.palette.foreground,fill=style.palette.foreground)
    void=circle(750,620,28,style,width=0,color=style.palette.background,fill=style.palette.background)+circle(835,620,28,style,width=0,color=style.palette.background,fill=style.palette.background)
    crowd="".join(circle(x,450+(x%3)*55,48,style,width=0,color=style.palette.secondary,fill=style.palette.secondary,opacity=.25) for x in [120,240,360,520,960])
    return actor+group("symbol_primary",mask+void)+group("opposing_force",crowd),"mask_crowd",["actor_primary","symbol_primary","opposing_force","scene_root"]

def evidence(scene,style):
    actor=_fig(250,1130,.78,"carry",style,"actor_primary")
    stack="".join(rect(420+i*36,1230-i*130,350-i*20,100,style,rx=4,width=0,color=style.palette.foreground,fill=style.palette.foreground,opacity=.9-i*.07) for i in range(6))
    gate=polygon([(860,400),(1010,400),(1010,1320),(860,1320),(860,980),(935,920),(860,860)],style,width=0,color=style.palette.foreground,fill=style.palette.foreground,opacity=.22)
    eye=path("M 680 400 Q 800 300 920 400 Q 800 500 680 400 Z",style,width=0,color=style.palette.accent,fill=style.palette.accent,opacity=.6)
    return actor+group("symbol_primary",stack)+group("environment_primary",gate)+group("opposing_force",eye),"proof_monument",["actor_primary","symbol_primary","environment_primary","opposing_force","scene_root"]

def awakening(scene,style):
    actor=_fig(500,1120,.92,"cut",style,"actor_primary")
    chain=path("M 0 560 C 260 650 470 730 630 860",style,width=34,color=style.palette.accent)+path("M 690 920 C 820 1030 940 1160 1080 1250",style,width=34,color=style.palette.accent)
    opening=polygon([(780,300),(1080,190),(1080,1510),(780,1320)],style,width=0,color=style.palette.foreground,fill=style.palette.foreground,opacity=.15)
    sun=circle(940,540,100,style,width=0,color=style.palette.foreground,fill=style.palette.foreground,opacity=.72)
    return actor+group("symbol_primary",chain)+group("symbol_secondary",sun)+group("environment_primary",opening),"break_the_seal",["actor_primary","symbol_primary","symbol_secondary","environment_primary","scene_root"]

def hidden(scene,style):
    cat=cat_actor(350,1170,.86,style,"actor_primary",mode="silhouette")
    maze=polygon([(520,400),(980,400),(980,1320),(780,1320),(780,1120),(650,1120),(650,850),(820,850),(820,620),(520,620)],style,width=0,color=style.palette.foreground,fill=style.palette.foreground,opacity=.16)
    pathlight=path("M 420 1250 C 600 1180 610 970 745 880 C 830 820 880 710 970 620",style,width=18,color=style.palette.accent,dash="28 20")
    return cat+group("environment_primary",maze)+group("symbol_primary",pathlight),"ayin_hidden_door",["actor_primary","environment_primary","symbol_primary","scene_root"]

def trap_detection(scene,style):
    actor=wolf_actor(340,1160,.82,style,"actor_primary",mode="silhouette")
    field=polygon([(760,900),(1025,900),(1005,1160),(780,1160)],style,width=0,color=style.palette.foreground,fill=style.palette.foreground,opacity=.18)
    bait=dot(965,1010,20,style,color=style.palette.accent,opacity=.9)+circle(965,1010,42,style,width=0,color=style.palette.accent,fill=style.palette.accent,opacity=.18)
    beam=path("M 640 960 C 740 930 820 955 940 1000",style,width=16,color=style.palette.accent,dash="24 18")
    triangle=polygon([(735,870),(775,790),(815,870)],style,width=0,color=style.palette.accent,fill=style.palette.accent,opacity=.72)
    return actor+group("environment_primary",field)+group("symbol_primary",beam+bait)+group("symbol_secondary",triangle),"wolf_warning_field",["actor_primary","environment_primary","symbol_primary","symbol_secondary","scene_root"]
MAP={"control":control,"anxiety":anxiety,"people_pleasing":people,"evidence":evidence,"awakening":awakening,"hidden_path":hidden,"trap_detection":trap_detection}
def render_svg(scene:SemanticSceneGraph,style:StyleContract):
    body,t,l=MAP[scene.visual_family](scene,style); return wrap(body,scene,style,renderer_id,t,l),t,l
