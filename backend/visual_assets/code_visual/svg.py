from __future__ import annotations

from dataclasses import dataclass
from html import escape
from math import cos, sin, radians
from .internal import StyleContract


def _attrs(**kwargs: object) -> str:
    out = []
    for key, value in kwargs.items():
        if value is None:
            continue
        key = key.replace("_", "-")
        out.append(f'{key}="{escape(str(value), quote=True)}"')
    return " ".join(out)


def group(group_id: str, body: str, **kwargs: object) -> str:
    return f'<g id="{escape(group_id)}" {_attrs(**kwargs)}>{body}</g>'


def line(x1, y1, x2, y2, style: StyleContract, width=None, color=None, opacity=1, dash=None) -> str:
    return f'<line {_attrs(x1=round(x1,2),y1=round(y1,2),x2=round(x2,2),y2=round(y2,2),stroke=color or style.palette.foreground,stroke_width=width or style.stroke.primary,stroke_linecap="round",stroke_dasharray=dash,opacity=opacity)}/>'


def circle(cx, cy, r, style: StyleContract, width=None, color=None, fill="none", opacity=1) -> str:
    return f'<circle {_attrs(cx=round(cx,2),cy=round(cy,2),r=round(r,2),stroke=color or style.palette.foreground,stroke_width=width or style.stroke.primary,fill=fill,opacity=opacity)}/>'


def ellipse(cx, cy, rx, ry, style: StyleContract, width=None, color=None, fill="none", opacity=1) -> str:
    return f'<ellipse {_attrs(cx=round(cx,2),cy=round(cy,2),rx=round(rx,2),ry=round(ry,2),stroke=color or style.palette.foreground,stroke_width=width or style.stroke.primary,fill=fill,opacity=opacity)}/>'


def rect(x,y,w,h,style:StyleContract,rx=20,width=None,color=None,fill="none",opacity=1) -> str:
    return f'<rect {_attrs(x=round(x,2),y=round(y,2),width=round(w,2),height=round(h,2),rx=round(rx,2),stroke=color or style.palette.foreground,stroke_width=width or style.stroke.primary,fill=fill,opacity=opacity)}/>'


def path(d, style: StyleContract, width=None, color=None, fill="none", opacity=1, dash=None) -> str:
    return f'<path {_attrs(d=d,stroke=color or style.palette.foreground,stroke_width=width or style.stroke.primary,stroke_linecap="round",stroke_linejoin="round",fill=fill,opacity=opacity,stroke_dasharray=dash)}/>'


def polygon(points,style:StyleContract,width=None,color=None,fill="none",opacity=1) -> str:
    p = " ".join(f"{round(x,2)},{round(y,2)}" for x,y in points)
    return f'<polygon {_attrs(points=p,stroke=color or style.palette.foreground,stroke_width=width or style.stroke.primary,stroke_linejoin="round",fill=fill,opacity=opacity)}/>'


def dot(cx,cy,r,style:StyleContract,color=None,opacity=1) -> str:
    return f'<circle {_attrs(cx=round(cx,2),cy=round(cy,2),r=round(r,2),fill=color or style.palette.foreground,opacity=opacity)}/>'


def arrow_head(x,y,angle_deg,size,style:StyleContract,color=None) -> str:
    a = radians(angle_deg)
    left=(x-size*cos(a-.55),y-size*sin(a-.55)); right=(x-size*cos(a+.55),y-size*sin(a+.55))
    return path(f"M {left[0]:.2f} {left[1]:.2f} L {x:.2f} {y:.2f} L {right[0]:.2f} {right[1]:.2f}",style,width=style.stroke.secondary,color=color)


def svg_document(body: str, style: StyleContract, metadata: dict[str,str]) -> str:
    data = " ".join(f'data-{escape(k)}="{escape(str(v), quote=True)}"' for k,v in metadata.items())
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {style.width} {style.height}" width="{style.width}" height="{style.height}" fill="none" {data}>{body}</svg>'


POSES = {
    "stand": dict(head=(0,-250), neck=(0,-185), hip=(0,80), lh=(-155,-65), rh=(155,-65), lf=(-105,290), rf=(105,290)),
    "withdraw": dict(head=(28,-250), neck=(16,-180), hip=(-28,88), lh=(-115,5), rh=(125,-100), lf=(-145,275), rf=(68,305)),
    "pull_left": dict(head=(-20,-246), neck=(-8,-180), hip=(35,85), lh=(-220,-115), rh=(110,5), lf=(-145,292), rf=(105,255)),
    "pull_right": dict(head=(20,-246), neck=(8,-180), hip=(-35,85), lh=(-110,5), rh=(220,-115), lf=(-105,255), rf=(145,292)),
    "crouch": dict(head=(0,-205), neck=(0,-142), hip=(0,65), lh=(-115,20), rh=(115,20), lf=(-145,230), rf=(145,230)),
    "reach": dict(head=(-15,-246), neck=(-8,-180), hip=(15,88), lh=(-125,15), rh=(230,-105), lf=(-100,295), rf=(110,285)),
    "carry": dict(head=(20,-238), neck=(8,-176), hip=(-15,92), lh=(-112,-28), rh=(120,-40), lf=(-100,300), rf=(120,286)),
    "run": dict(head=(30,-242), neck=(8,-176), hip=(-22,92), lh=(-165,-15), rh=(170,-115), lf=(-188,265), rf=(165,230)),
    "cut": dict(head=(-22,-242), neck=(-12,-176), hip=(18,92), lh=(-115,0), rh=(198,-125), lf=(-100,300), rf=(120,275)),
    "look_up": dict(head=(0,-265), neck=(0,-190), hip=(0,80), lh=(-132,-25), rh=(132,-25), lf=(-100,290), rf=(100,290)),
}


def figure(x:float,y:float,scale:float,pose:str,style:StyleContract,group_id="actor_primary",mode="contour",facing="right",opacity=1) -> str:
    p=POSES.get(pose,POSES["stand"])
    X=lambda k:x+p[k][0]*scale; Y=lambda k:y+p[k][1]*scale
    fg=style.palette.foreground
    sec=style.palette.secondary
    head_r=55*scale
    neck=(X("neck"),Y("neck")); hip=(X("hip"),Y("hip"))
    shoulder_y=neck[1]+66*scale; shoulder_x=neck[0]
    parts=[]
    if mode == "silhouette":
        parts.append(circle(X("head"),Y("head"),head_r,style,width=0,color=fg,fill=fg,opacity=opacity))
        torso=f"M {shoulder_x-58*scale:.1f} {shoulder_y-8*scale:.1f} Q {shoulder_x:.1f} {neck[1]-8*scale:.1f} {shoulder_x+58*scale:.1f} {shoulder_y-8*scale:.1f} L {hip[0]+45*scale:.1f} {hip[1]:.1f} Q {hip[0]:.1f} {hip[1]+28*scale:.1f} {hip[0]-45*scale:.1f} {hip[1]:.1f} Z"
        parts.append(path(torso,style,width=0,color=fg,fill=fg,opacity=opacity))
        limb_w=max(20,style.stroke.primary*1.35)*scale
        parts += [line(shoulder_x,shoulder_y,X("lh"),Y("lh"),style,width=limb_w,opacity=opacity),line(shoulder_x,shoulder_y,X("rh"),Y("rh"),style,width=limb_w,opacity=opacity),line(hip[0],hip[1],X("lf"),Y("lf"),style,width=limb_w*1.08,opacity=opacity),line(hip[0],hip[1],X("rf"),Y("rf"),style,width=limb_w*1.08,opacity=opacity)]
    else:
        # More anatomical contour than a plain stickman: oval skull, shoulder line, tapered torso, hands and feet.
        parts.append(ellipse(X("head"),Y("head"),head_r*.88,head_r,style,width=style.stroke.primary*.86,opacity=opacity))
        shoulder_l=(shoulder_x-62*scale, shoulder_y); shoulder_r=(shoulder_x+62*scale, shoulder_y)
        torso=f"M {shoulder_l[0]:.1f} {shoulder_l[1]:.1f} Q {shoulder_x-32*scale:.1f} {hip[1]-110*scale:.1f} {hip[0]-38*scale:.1f} {hip[1]:.1f} M {shoulder_r[0]:.1f} {shoulder_r[1]:.1f} Q {shoulder_x+32*scale:.1f} {hip[1]-110*scale:.1f} {hip[0]+38*scale:.1f} {hip[1]:.1f} M {shoulder_l[0]:.1f} {shoulder_l[1]:.1f} Q {shoulder_x:.1f} {neck[1]-8*scale:.1f} {shoulder_r[0]:.1f} {shoulder_r[1]:.1f}"
        parts.append(path(torso,style,width=style.stroke.primary,opacity=opacity))
        parts += [path(f"M {shoulder_l[0]:.1f} {shoulder_l[1]:.1f} Q {(shoulder_l[0]+X('lh'))/2:.1f} {(shoulder_l[1]+Y('lh'))/2-12*scale:.1f} {X('lh'):.1f} {Y('lh'):.1f}",style,width=style.stroke.primary,opacity=opacity),path(f"M {shoulder_r[0]:.1f} {shoulder_r[1]:.1f} Q {(shoulder_r[0]+X('rh'))/2:.1f} {(shoulder_r[1]+Y('rh'))/2-12*scale:.1f} {X('rh'):.1f} {Y('rh'):.1f}",style,width=style.stroke.primary,opacity=opacity),path(f"M {hip[0]-20*scale:.1f} {hip[1]:.1f} Q {(hip[0]+X('lf'))/2:.1f} {(hip[1]+Y('lf'))/2:.1f} {X('lf'):.1f} {Y('lf'):.1f}",style,width=style.stroke.primary*1.06,opacity=opacity),path(f"M {hip[0]+20*scale:.1f} {hip[1]:.1f} Q {(hip[0]+X('rf'))/2:.1f} {(hip[1]+Y('rf'))/2:.1f} {X('rf'):.1f} {Y('rf'):.1f}",style,width=style.stroke.primary*1.06,opacity=opacity)]
        parts.append(circle(X("lh"),Y("lh"),10*scale,style,width=style.stroke.detail,fill="none",opacity=opacity))
        parts.append(circle(X("rh"),Y("rh"),10*scale,style,width=style.stroke.detail,fill="none",opacity=opacity))
        parts.append(line(X("lf")-20*scale,Y("lf")+3*scale,X("lf")+20*scale,Y("lf")+3*scale,style,width=style.stroke.secondary,opacity=opacity))
        parts.append(line(X("rf")-20*scale,Y("rf")+3*scale,X("rf")+20*scale,Y("rf")+3*scale,style,width=style.stroke.secondary,opacity=opacity))
        # Face direction gives the character intent without adding a full face.
        nose_dir=1 if facing=="right" else -1
        parts.append(path(f"M {X('head')+nose_dir*head_r*.64:.1f} {Y('head')-2*scale:.1f} l {nose_dir*13*scale:.1f} {8*scale:.1f}",style,width=style.stroke.detail,color=sec,opacity=opacity*.9))
        parts.append(dot(X("head")+nose_dir*head_r*.22,Y("head")-10*scale,4.5*scale,style,color=fg,opacity=opacity))
    return group(group_id,"".join(parts),opacity=opacity)
