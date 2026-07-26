from __future__ import annotations
from ..internal import SemanticSceneGraph, StyleContract
from ..svg import group, svg_document

renderer_id="pixel_rules"; renderer_version="0.4.0"
S=8

def pr(x,y,w,h,color,opacity=1):
    return f'<rect x="{int(x*S)}" y="{int(y*S)}" width="{int(w*S)}" height="{int(h*S)}" fill="{color}" opacity="{opacity}"/>'

def sprite(x,y,style,gid="actor_primary",direction=1,pose="stand"):
    fg=style.palette.foreground; acc=style.palette.accent
    b=[]
    b += [pr(x+3,y,4,4,fg),pr(x+2,y+4,6,5,fg),pr(x+1,y+9,8,2,fg)]
    if direction>0: b += [pr(x+7,y+1,2,1,acc)]
    else: b += [pr(x+1,y+1,2,1,acc)]
    if pose=="run": b += [pr(x-1,y+10,4,2,fg),pr(x+7,y+8,4,2,fg),pr(x+2,y+11,2,6,fg),pr(x+7,y+11,2,4,fg),pr(x+8,y+15,4,2,fg)]
    elif pose=="pull": b += [pr(x-2,y+8,5,2,fg),pr(x+7,y+8,6,2,fg),pr(x+2,y+11,2,6,fg),pr(x+7,y+11,2,6,fg)]
    elif pose=="crouch": b += [pr(x+1,y+10,8,3,fg),pr(x,y+13,4,3,fg),pr(x+7,y+13,4,3,fg)]
    else: b += [pr(x-1,y+8,4,2,fg),pr(x+7,y+8,4,2,fg),pr(x+2,y+11,2,7,fg),pr(x+7,y+11,2,7,fg)]
    return group(gid,"".join(b),shape_rendering="crispEdges")

def cat_sprite(x,y,style,gid="actor_primary"):
    fg=style.palette.foreground; acc=style.palette.accent
    b=[pr(x+2,y+5,10,5,fg),pr(x+3,y+1,5,5,fg),pr(x+2,y,y+0 and 2,2,fg)]
    b=[pr(x+2,y+5,10,5,fg),pr(x+4,y+2,4,4,fg),pr(x+4,y+1,1,2,fg),pr(x+7,y+1,1,2,fg),pr(x+10,y+6,4,2,fg),pr(x+12,y+4,4,2,fg),pr(x+1,y+8,2,6,fg),pr(x+4,y+9,2,6,fg),pr(x+8,y+9,2,6,fg),pr(x+11,y+8,2,6,fg),pr(x+15,y+3,2,6,fg),pr(x+5,y+4,1,1,acc),pr(x+7,y+4,1,1,acc)]
    return group(gid,"".join(b),shape_rendering="crispEdges")

def wolf_sprite(x,y,style,gid="actor_primary"):
    fg=style.palette.foreground; acc=style.palette.accent
    b=[pr(x+2,y+6,14,5,fg),pr(x+6,y+2,8,5,fg),pr(x+12,y+1,3,3,fg),pr(x+14,y+2,4,2,fg),pr(x+17,y+3,2,2,fg),pr(x+1,y+7,2,3,fg),pr(x+4,y+10,2,7,fg),pr(x+8,y+10,2,7,fg),pr(x+12,y+10,2,6,fg),pr(x+15,y+9,2,7,fg),pr(x,y+3,3,2,fg),pr(x-2,y+1,3,2,fg),pr(x+13,y+4,1,1,acc)]
    return group(gid,"".join(b),shape_rendering="crispEdges")

def box(x,y,w,h,style,color=None,fill=None,th=1):
    c=color or style.palette.foreground
    body=pr(x,y,w,th,c)+pr(x,y+h-th,w,th,c)+pr(x,y,th,h,c)+pr(x+w-th,y,th,h,c)
    if fill: body=pr(x,y,w,h,fill)+body
    return body

def stairs(x,y,steps,style):
    fg=style.palette.foreground; out=[]
    for i in range(steps): out.append(pr(x+i*10,y-i*10,24,8,fg,.85-i*.06))
    return "".join(out)

def control(scene,style):
    a=sprite(28,125,style,"actor_primary",1,"pull"); b=sprite(92,125,style,"actor_secondary",-1,"stand")
    rope="".join(pr(x,126+((x//5)%2),5,1,style.palette.accent) for x in range(38,93,5))
    warning=box(52,70,30,18,style,color=style.palette.accent)+pr(66,74,2,8,style.palette.accent)+pr(66,84,2,2,style.palette.accent)
    zone=pr(83,110,25,34,style.palette.accent,.12)
    body=group("environment_primary",zone+warning,shape_rendering="crispEdges")+group("symbol_primary",rope,shape_rendering="crispEdges")+a+b
    return body,"chain_zone",["environment_primary","symbol_primary","actor_primary","actor_secondary","scene_root"]

def anxiety(scene,style):
    actor=group("actor_primary", sprite(40,132,style,"crowd_a",-1,"stand").replace('id="crowd_a"','')+sprite(58,128,style,"crowd_b",1,"stand").replace('id="crowd_b"','')+sprite(77,133,style,"crowd_c",1,"crouch").replace('id="crowd_c"',''), shape_rendering="crispEdges") if scene.subject.type=="group" or scene.metadata.get("actor_pack")=="crowd" else sprite(63,130,style,"actor_primary",1,"crouch")
    wall_l=pr(10,45,8,125,style.palette.foreground,.82)+pr(18,70,18,6,style.palette.foreground,.35)
    wall_r=pr(117,45,8,125,style.palette.foreground,.82)+pr(99,70,18,6,style.palette.foreground,.35)
    danger=pr(38,115,59,45,style.palette.accent,.12)
    arrows=pr(25,118,12,3,style.palette.accent)+pr(31,115,3,9,style.palette.accent)+pr(98,118,12,3,style.palette.accent)+pr(101,115,3,9,style.palette.accent)
    return group("environment_primary",wall_l+wall_r+danger+arrows,shape_rendering="crispEdges")+actor,"shrinking_room",["environment_primary","actor_primary","scene_root"]

def people(scene,style):
    actor=sprite(45,132,style,"actor_primary",1,"stand")
    mask=box(82,72,28,26,style,color=style.palette.foreground)+pr(88,78,4,3,style.palette.accent)+pr(100,78,4,3,style.palette.accent)+pr(92,88,8,2,style.palette.foreground)
    eyes="".join(pr(x,y,8,4,style.palette.secondary,.6)+pr(x+3,y+1,2,2,style.palette.accent) for x,y in [(18,62),(52,52),(103,48),(112,91)])
    inventory=box(20,174,95,14,style,color=style.palette.muted)+"".join(pr(24+i*14,177,9,8,style.palette.foreground,.75-i*.08) for i in range(6))
    return actor+group("symbol_primary",mask,shape_rendering="crispEdges")+group("opposing_force",eyes,shape_rendering="crispEdges")+group("environment_primary",inventory,shape_rendering="crispEdges"),"mask_inventory",["actor_primary","symbol_primary","opposing_force","environment_primary","scene_root"]

def evidence(scene,style):
    actor=sprite(18,135,style,"actor_primary",1,"run")
    gate=box(102,58,22,112,style,color=style.palette.foreground)+pr(105,98,16,4,style.palette.accent)
    docs=stairs(42,160,6,style)
    belt=pr(8,185,119,5,style.palette.secondary,.5)+"".join(pr(x,184,5,7,style.palette.foreground,.55) for x in range(10,126,12))
    counter=box(84,34,40,15,style,color=style.palette.accent)+pr(90,39,6,5,style.palette.accent)+pr(101,39,6,5,style.palette.accent)+pr(112,39,6,5,style.palette.accent)
    return group("environment_primary",gate+belt+counter,shape_rendering="crispEdges")+group("symbol_primary",docs,shape_rendering="crispEdges")+actor,"proof_gate",["environment_primary","symbol_primary","actor_primary","scene_root"]

def awakening(scene,style):
    actor=sprite(55,132,style,"actor_primary",1,"run")
    chain="".join(pr(x,115+(x%3),5,2,style.palette.accent) for x in range(5,76,5))+"".join(pr(x,125+(x%3),5,2,style.palette.accent) for x in range(82,132,5))
    burst="".join(pr(x,y,2,7,style.palette.foreground) for x,y in [(78,98),(72,106),(84,106),(69,117),(87,117)])
    door=box(103,54,24,112,style,color=style.palette.foreground)+pr(106,58,18,104,style.palette.secondary,.15)
    pathlight=pr(83,151,20,5,style.palette.accent,.65)+pr(98,146,5,15,style.palette.accent,.65)
    return actor+group("symbol_primary",chain,shape_rendering="crispEdges")+group("symbol_secondary",burst,shape_rendering="crispEdges")+group("environment_primary",door+pathlight,shape_rendering="crispEdges"),"break_chain_exit",["actor_primary","symbol_primary","symbol_secondary","environment_primary","scene_root"]

def hidden(scene,style):
    actor=cat_sprite(18,142,style,"actor_primary")
    maze=pr(10,50,6,125,style.palette.foreground,.65)+pr(16,50,45,6,style.palette.foreground,.65)+pr(55,50,6,55,style.palette.foreground,.65)+pr(40,99,21,6,style.palette.foreground,.65)+pr(40,99,6,55,style.palette.foreground,.65)+pr(40,148,40,6,style.palette.foreground,.65)+pr(75,90,6,64,style.palette.foreground,.65)+pr(75,90,40,6,style.palette.foreground,.65)+pr(109,90,6,75,style.palette.foreground,.65)
    pathdots="".join(pr(x,y,3,3,style.palette.accent) for x,y in [(30,155),(42,148),(52,138),(63,124),(76,110),(88,93),(101,76),(116,62)])
    door=box(113,48,14,24,style,color=style.palette.accent)+pr(116,52,8,16,style.palette.accent,.2)
    eye=pr(91,39,20,3,style.palette.secondary,.6)+pr(99,38,4,5,style.palette.accent)
    return actor+group("environment_primary",maze+eye,shape_rendering="crispEdges")+group("symbol_primary",pathdots+door,shape_rendering="crispEdges"),"hidden_door",["actor_primary","environment_primary","symbol_primary","scene_root"]

def trap_detection(scene,style):
    actor=wolf_sprite(20,140,style,"actor_primary")
    field=box(94,105,30,30,style,color=style.palette.secondary)+pr(95,118,28,2,style.palette.accent,.9)
    bait=pr(115,112,5,5,style.palette.accent)+pr(112,109,11,11,style.palette.accent,.18)
    scent="".join(pr(x,y,3,2,style.palette.secondary,.8) for x,y in [(54,124),(66,120),(78,116),(89,114),(99,112)])
    alert=pr(85,90,2,8,style.palette.accent)+pr(84,100,4,3,style.palette.accent)
    return actor+group("environment_primary",field,shape_rendering="crispEdges")+group("symbol_primary",scent+bait,shape_rendering="crispEdges")+group("symbol_secondary",alert,shape_rendering="crispEdges"),"wolf_trap_pixel",["actor_primary","environment_primary","symbol_primary","symbol_secondary","scene_root"]

def pixel_motif(scene,style):
    if scene.ip_pack == "xuanqi":
        return group("ip_motif", box(58,24,19,19,style,color=style.palette.muted)+pr(66,20,3,3,style.palette.accent), shape_rendering="crispEdges")
    if scene.ip_pack == "ayin":
        return group("ip_motif", pr(108,29,18,2,style.palette.muted,.7)+pr(115,28,4,4,style.palette.accent), shape_rendering="crispEdges")
    if scene.ip_pack == "huicewolf":
        return group("ip_motif", pr(15,30,4,4,style.palette.muted,.6)+pr(22,34,4,4,style.palette.muted,.5)+pr(29,38,4,4,style.palette.muted,.4), shape_rendering="crispEdges")
    return ""

MAP={"control":control,"anxiety":anxiety,"people_pleasing":people,"evidence":evidence,"awakening":awakening,"hidden_path":hidden,"trap_detection":trap_detection}
def render_svg(scene:SemanticSceneGraph,style:StyleContract):
    body,t,l=MAP[scene.visual_family](scene,style)
    meta={"renderer":renderer_id,"template":t,"scene":scene.scene_id,"theme":style.theme_mode,"pack":scene.ip_pack}
    svg=svg_document(group("scene_root",body+pixel_motif(scene,style),shape_rendering="crispEdges"),style,meta)
    return svg,t,l
