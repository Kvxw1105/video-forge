from __future__ import annotations
from .internal import StyleContract
from .svg import circle, dot, ellipse, figure, group, line, path, polygon


def human_actor(x: float, y: float, scale: float, pose: str, style: StyleContract, group_id: str = "actor_primary", mode: str = "contour", facing: str = "right", opacity: float = 1) -> str:
    return figure(x, y, scale, pose, style, group_id=group_id, mode=mode, facing=facing, opacity=opacity)


def crowd_actor(x: float, y: float, scale: float, style: StyleContract, group_id: str = "actor_primary", mode: str = "contour") -> str:
    specs=[(-170,80,0.72,'withdraw','left'),(-65,20,0.8,'stand','right'),(75,0,0.84,'reach','left'),(190,95,0.72,'stand','left')]
    out=[]
    for i,(dx,dy,s,pose,facing) in enumerate(specs):
        out.append(figure(x+dx*scale,y+dy*scale,s*scale,pose,style,group_id=f'{group_id}_{i}',mode='silhouette' if mode=='silhouette' else 'contour',facing=facing,opacity=.95 if i==2 else .72))
    # retain animation target layer by grouping the crowd as actor_primary
    return group(group_id, ''.join(out))


def cat_actor(x: float, y: float, scale: float, style: StyleContract, group_id: str = "actor_primary", mode: str = "contour", pose: str = "prowl", eye_glow: bool = True, opacity: float = 1) -> str:
    fg=style.palette.foreground; acc=style.palette.accent; sec=style.palette.secondary
    if mode=='silhouette':
        body=path(f"M {x-150*scale:.1f} {y+25*scale:.1f} Q {x-128*scale:.1f} {y-45*scale:.1f} {x-74*scale:.1f} {y-58*scale:.1f} Q {x-25*scale:.1f} {y-115*scale:.1f} {x+58*scale:.1f} {y-108*scale:.1f} Q {x+138*scale:.1f} {y-95*scale:.1f} {x+165*scale:.1f} {y-10*scale:.1f} Q {x+172*scale:.1f} {y+60*scale:.1f} {x+135*scale:.1f} {y+95*scale:.1f} Q {x+58*scale:.1f} {y+130*scale:.1f} {x-35*scale:.1f} {y+125*scale:.1f} Q {x-122*scale:.1f} {y+118*scale:.1f} {x-150*scale:.1f} {y+25*scale:.1f} Z",style,width=0,color=fg,fill=fg,opacity=opacity)
        ears=polygon([(x-22*scale,y-98*scale),(x+3*scale,y-158*scale),(x+24*scale,y-95*scale)],style,width=0,color=fg,fill=fg,opacity=opacity)+polygon([(x+36*scale,y-92*scale),(x+63*scale,y-150*scale),(x+84*scale,y-82*scale)],style,width=0,color=fg,fill=fg,opacity=opacity)
        tail=path(f"M {x+150*scale:.1f} {y+5*scale:.1f} C {x+250*scale:.1f} {y-110*scale:.1f} {x+260*scale:.1f} {y+48*scale:.1f} {x+198*scale:.1f} {y+82*scale:.1f}",style,width=28*scale,color=fg,opacity=opacity)
        eyes=dot(x+10*scale,y-45*scale,9*scale,style,color=acc,opacity=.88)+dot(x+52*scale,y-47*scale,9*scale,style,color=acc,opacity=.88) if eye_glow else ''
        return group(group_id, body+ears+tail+eyes)
    # contour
    body=path(f"M {x-142*scale:.1f} {y+25*scale:.1f} Q {x-126*scale:.1f} {y-42*scale:.1f} {x-75*scale:.1f} {y-54*scale:.1f} Q {x-20*scale:.1f} {y-118*scale:.1f} {x+60*scale:.1f} {y-104*scale:.1f} Q {x+144*scale:.1f} {y-90*scale:.1f} {x+162*scale:.1f} {y-4*scale:.1f} Q {x+162*scale:.1f} {y+82*scale:.1f} {x+92*scale:.1f} {y+108*scale:.1f} Q {x-40*scale:.1f} {y+132*scale:.1f} {x-124*scale:.1f} {y+100*scale:.1f} Q {x-150*scale:.1f} {y+78*scale:.1f} {x-142*scale:.1f} {y+25*scale:.1f} Z",style,width=style.stroke.primary*.92,color=fg,opacity=opacity)
    legs=''.join(path(f"M {x+lx1*scale:.1f} {y+ly1*scale:.1f} Q {x+lx2*scale:.1f} {y+ly2*scale:.1f} {x+lx3*scale:.1f} {y+ly3*scale:.1f}",style,width=style.stroke.secondary,color=fg,opacity=opacity) for lx1,ly1,lx2,ly2,lx3,ly3 in [(-95,55,-90,112,-104,132),(-12,64,-4,120,-18,140),(78,52,72,114,60,132),(123,40,118,106,111,126)])
    paws=''.join(line(x+px1*scale,y+py*scale,x+px2*scale,y+py*scale,style,width=style.stroke.detail,color=fg,opacity=opacity) for px1,px2,py in [(-117,-94,134),(-31,-8,142),(46,72,134),(95,122,128)])
    head_ears=polygon([(x-20*scale,y-95*scale),(x+4*scale,y-158*scale),(x+28*scale,y-92*scale)],style,width=style.stroke.secondary,color=fg,opacity=opacity)+polygon([(x+34*scale,y-89*scale),(x+61*scale,y-150*scale),(x+85*scale,y-82*scale)],style,width=style.stroke.secondary,color=fg,opacity=opacity)
    face=ellipse(x+24*scale,y-42*scale,48*scale,34*scale,style,width=style.stroke.secondary,color=sec,opacity=.8*opacity)
    eyes=(dot(x+7*scale,y-46*scale,5*scale,style,color=acc,opacity=.9)+dot(x+43*scale,y-48*scale,5*scale,style,color=acc,opacity=.9)) if eye_glow else (dot(x+7*scale,y-46*scale,4*scale,style,color=fg,opacity=opacity)+dot(x+43*scale,y-48*scale,4*scale,style,color=fg,opacity=opacity))
    whiskers=''.join(line(x+a*scale,y+b*scale,x+c*scale,y+d*scale,style,width=style.stroke.detail,color=sec,opacity=.75*opacity) for a,b,c,d in [(-8,-28,-45,-34),(-4,-18,-50,-8),(51,-28,95,-36),(53,-18,97,-8)])
    tail=path(f"M {x+150*scale:.1f} {y+6*scale:.1f} C {x+246*scale:.1f} {y-124*scale:.1f} {x+258*scale:.1f} {y+44*scale:.1f} {x+196*scale:.1f} {y+78*scale:.1f}",style,width=style.stroke.primary*.86,color=fg,opacity=opacity)
    return group(group_id, body+legs+paws+head_ears+face+eyes+whiskers+tail)


def wolf_actor(x: float, y: float, scale: float, style: StyleContract, group_id: str = "actor_primary", mode: str = "contour", pose: str = "sniff", opacity: float = 1) -> str:
    fg=style.palette.foreground; sec=style.palette.secondary; acc=style.palette.accent
    if mode=='silhouette':
        body=path(f"M {x-190*scale:.1f} {y+18*scale:.1f} Q {x-165*scale:.1f} {y-22*scale:.1f} {x-128*scale:.1f} {y-46*scale:.1f} Q {x-42*scale:.1f} {y-170*scale:.1f} {x+92*scale:.1f} {y-120*scale:.1f} Q {x+144*scale:.1f} {y-110*scale:.1f} {x+176*scale:.1f} {y-84*scale:.1f} L {x+225*scale:.1f} {y-104*scale:.1f} L {x+246*scale:.1f} {y-64*scale:.1f} L {x+220*scale:.1f} {y-18*scale:.1f} Q {x+194*scale:.1f} {y+46*scale:.1f} {x+150*scale:.1f} {y+92*scale:.1f} Q {x+88*scale:.1f} {y+128*scale:.1f} {x+12*scale:.1f} {y+130*scale:.1f} Q {x-146*scale:.1f} {y+118*scale:.1f} {x-190*scale:.1f} {y+18*scale:.1f} Z",style,width=0,color=fg,fill=fg,opacity=opacity)
        ears=polygon([(x+126*scale,y-108*scale),(x+158*scale,y-174*scale),(x+182*scale,y-98*scale)],style,width=0,color=fg,fill=fg,opacity=opacity)+polygon([(x+88*scale,y-118*scale),(x+106*scale,y-172*scale),(x+129*scale,y-110*scale)],style,width=0,color=fg,fill=fg,opacity=opacity)
        tail=path(f"M {x-165*scale:.1f} {y-12*scale:.1f} C {x-264*scale:.1f} {y-124*scale:.1f} {x-286*scale:.1f} {y+30*scale:.1f} {x-210*scale:.1f} {y+52*scale:.1f}",style,width=34*scale,color=fg,opacity=opacity)
        eye=dot(x+158*scale,y-72*scale,8*scale,style,color=acc,opacity=.88)
        return group(group_id, body+ears+tail+eye)
    body=path(f"M {x-186*scale:.1f} {y+22*scale:.1f} Q {x-164*scale:.1f} {y-18*scale:.1f} {x-126*scale:.1f} {y-42*scale:.1f} Q {x-46*scale:.1f} {y-164*scale:.1f} {x+92*scale:.1f} {y-118*scale:.1f} Q {x+154*scale:.1f} {y-110*scale:.1f} {x+180*scale:.1f} {y-84*scale:.1f} L {x+226*scale:.1f} {y-104*scale:.1f} L {x+244*scale:.1f} {y-66*scale:.1f} L {x+218*scale:.1f} {y-20*scale:.1f} Q {x+196*scale:.1f} {y+50*scale:.1f} {x+154*scale:.1f} {y+92*scale:.1f} Q {x+96*scale:.1f} {y+126*scale:.1f} {x+6*scale:.1f} {y+128*scale:.1f} Q {x-144*scale:.1f} {y+118*scale:.1f} {x-186*scale:.1f} {y+22*scale:.1f} Z",style,width=style.stroke.primary*.94,color=fg,opacity=opacity)
    spine=path(f"M {x-138*scale:.1f} {y-22*scale:.1f} C {x-54*scale:.1f} {y-145*scale:.1f} {x+74*scale:.1f} {y-116*scale:.1f} {x+154*scale:.1f} {y-92*scale:.1f}",style,width=style.stroke.detail,color=sec,opacity=.8*opacity)
    chest=path(f"M {x+44*scale:.1f} {y-108*scale:.1f} Q {x+4*scale:.1f} {y-4*scale:.1f} {x+10*scale:.1f} {y+126*scale:.1f}",style,width=style.stroke.secondary,color=fg,opacity=opacity)
    legs=''.join(path(f"M {x+a*scale:.1f} {y+b*scale:.1f} Q {x+c*scale:.1f} {y+d*scale:.1f} {x+e*scale:.1f} {y+f*scale:.1f}",style,width=style.stroke.secondary,color=fg,opacity=opacity) for a,b,c,d,e,f in [(-110,30,-112,106,-120,136),(-24,42,-20,108,-30,142),(78,26,68,102,54,134),(132,8,124,90,114,126)])
    paws=''.join(line(x+px1*scale,y+py*scale,x+px2*scale,y+py*scale,style,width=style.stroke.detail,color=fg,opacity=opacity) for px1,px2,py in [(-132,-110,138),(-42,-18,144),(40,64,136),(100,124,128)])
    ears=polygon([(x+124*scale,y-108*scale),(x+156*scale,y-174*scale),(x+178*scale,y-98*scale)],style,width=style.stroke.secondary,color=fg,opacity=opacity)+polygon([(x+84*scale,y-114*scale),(x+102*scale,y-170*scale),(x+126*scale,y-104*scale)],style,width=style.stroke.secondary,color=fg,opacity=opacity)
    eye=dot(x+154*scale,y-72*scale,5*scale,style,color=acc,opacity=.9)
    snout=line(x+188*scale,y-70*scale,x+234*scale,y-74*scale,style,width=style.stroke.secondary,color=fg,opacity=opacity)
    scent=path(f"M {x+254*scale:.1f} {y-72*scale:.1f} C {x+300*scale:.1f} {y-112*scale:.1f} {x+318*scale:.1f} {y-30*scale:.1f} {x+284*scale:.1f} {y+6*scale:.1f}",style,width=style.stroke.detail,color=sec,opacity=.7*opacity)
    tail=path(f"M {x-164*scale:.1f} {y-10*scale:.1f} C {x-266*scale:.1f} {y-136*scale:.1f} {x-286*scale:.1f} {y+30*scale:.1f} {x-206*scale:.1f} {y+48*scale:.1f}",style,width=style.stroke.primary*.84,color=fg,opacity=opacity)
    return group(group_id, body+spine+chest+legs+paws+ears+eye+snout+scent+tail)
