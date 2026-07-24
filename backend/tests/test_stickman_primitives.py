from visual_assets.stickman import primitives


def test_primitive_catalog_contains_required_names():
    required = {"stick_person", "head", "torso", "arm", "leg", "person_pose", "mask", "rope", "control_line", "cage", "wall", "boulder", "evidence_stack", "arrow", "crack", "shadow", "heart", "spikes", "boundary_circle", "comparison_scale", "crowd", "rule_frame", "scissors"}
    assert required <= primitives.PRIMITIVE_NAMES
