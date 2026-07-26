from __future__ import annotations

from .internal import MotionBeat, MotionInstruction, MotionPlan, SemanticSceneGraph, StyleContract


def resolve_motion(scene: SemanticSceneGraph, style: StyleContract) -> MotionPlan:
    d = max(2.8, min(5.0, scene.end-scene.start))
    dark = style.theme_mode == "dark"
    reveal_ease = "easeOutCubic" if dark else "easeInOutSine"
    actors=[]; symbols=[]; env=[]; camera=[]
    profile=scene.motion_profile
    if profile == "control":
        symbols=[MotionInstruction(target_id="symbol_primary",property="scale",start_time=.5,end_time=d*.62,from_value=.94,to_value=1.06,easing="easeInOutCubic"),MotionInstruction(target_id="symbol_primary",property="x",start_time=.5,end_time=d*.62,from_value=-8,to_value=8,easing="easeInOutCubic")]
        actors=[MotionInstruction(target_id="actor_secondary",property="x",start_time=.8,end_time=d*.75,from_value=0,to_value=-24,easing="easeOutCubic")]
        camera=[MotionInstruction(target_id="scene_root",property="scale",start_time=0,end_time=d,from_value=1,to_value=1.035,easing="linear")]
    elif profile == "anxiety":
        env=[MotionInstruction(target_id="environment_primary",property="scale",start_time=.2,end_time=d*.78,from_value=1.06,to_value=.88,easing="easeInOutCubic")]
        actors=[MotionInstruction(target_id="actor_primary",property="scale",start_time=.5,end_time=d*.78,from_value=1,to_value=.92,easing="easeInOutCubic")]
    elif profile == "people_pleasing":
        symbols=[MotionInstruction(target_id="symbol_primary",property="y",start_time=.3,end_time=d*.55,from_value=-22,to_value=8,easing=reveal_ease),MotionInstruction(target_id="opposing_force",property="opacity",start_time=.5,end_time=d*.7,from_value=.1,to_value=1,easing="easeOutCubic")]
        actors=[MotionInstruction(target_id="actor_primary",property="opacity",start_time=d*.25,end_time=d*.9,from_value=1,to_value=.62,easing="easeInOutSine")]
    elif profile == "evidence":
        symbols=[MotionInstruction(target_id="symbol_primary",property="y",start_time=.2,end_time=d*.72,from_value=90,to_value=0,easing="easeOutBack")]
        env=[MotionInstruction(target_id="environment_primary",property="x",start_time=d*.35,end_time=d*.8,from_value=0,to_value=38,easing="easeInOutCubic")]
    elif profile == "awakening":
        symbols=[MotionInstruction(target_id="symbol_primary",property="scale",start_time=d*.35,end_time=d*.48,from_value=1,to_value=1.12,easing="easeOutBack"),MotionInstruction(target_id="symbol_secondary",property="opacity",start_time=d*.45,end_time=d*.7,from_value=0,to_value=1,easing="easeOutCubic")]
        env=[MotionInstruction(target_id="environment_primary",property="x",start_time=d*.48,end_time=d*.9,from_value=0,to_value=120,easing="easeOutCubic")]
    elif profile == "hidden_path":
        symbols=[MotionInstruction(target_id="symbol_primary",property="opacity",start_time=.5,end_time=d*.65,from_value=0,to_value=1,easing=reveal_ease),MotionInstruction(target_id="symbol_primary",property="stroke",start_time=.5,end_time=d*.8,from_value=1,to_value=0,easing="linear")]
        actors=[MotionInstruction(target_id="actor_primary",property="x",start_time=d*.55,end_time=d*.9,from_value=0,to_value=42,easing="easeOutCubic")]
    elif profile == "trap_detection":
        actors=[MotionInstruction(target_id="actor_primary",property="x",start_time=.4,end_time=d*.55,from_value=-14,to_value=18,easing="easeInOutSine"), MotionInstruction(target_id="actor_primary",property="y",start_time=d*.55,end_time=d*.82,from_value=0,to_value=-12,easing="easeOutCubic")]
        symbols=[MotionInstruction(target_id="symbol_primary",property="opacity",start_time=.35,end_time=d*.65,from_value=.18,to_value=1,easing="easeOutCubic"), MotionInstruction(target_id="symbol_secondary",property="scale",start_time=d*.52,end_time=d*.86,from_value=.88,to_value=1.08,easing="easeOutBack")]
        env=[MotionInstruction(target_id="environment_primary",property="opacity",start_time=.3,end_time=d*.7,from_value=.32,to_value=1,easing="easeOutCubic")]
        camera=[MotionInstruction(target_id="scene_root",property="scale",start_time=0,end_time=d,from_value=1,to_value=1.02,easing="linear")]
    beats=[MotionBeat(time=0,type="establish"),MotionBeat(time=round(d*.45,2),type="pressure_or_reveal"),MotionBeat(time=round(d*.78,2),type="turning_point")]
    return MotionPlan(profile=profile,theme_mode=style.theme_mode,duration=d,actor_motions=actors,symbol_motions=symbols,environment_motions=env,camera_motions=camera,beats=beats,seed=style.seed)
