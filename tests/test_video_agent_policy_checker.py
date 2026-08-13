from agent.lab_runner.policy_checker import PolicyChecker


def test_auto_allow_read_operations():
    decision = PolicyChecker().decide("read_project")
    assert decision.decision == "allow"
    assert decision.risk == "low"


def test_paid_approval_required():
    decision = PolicyChecker().decide("paid_image_generation", {"estimatedCost": {"amount": 1}})
    assert decision.decision == "approval_required"
    assert decision.policyId == "paid-operation-policy"


def test_replace_approval_required():
    decision = PolicyChecker().decide("replace_scene_asset")
    assert decision.decision == "approval_required"
    assert "preview" in decision.invalidatedArtifacts


def test_revoice_approval_invalidates_downstream():
    decision = PolicyChecker().decide("regenerate_voiceover")
    assert decision.decision == "approval_required"
    assert decision.invalidatedArtifacts == ["alignment", "subtitles", "visual_plan", "preview", "jianying_draft"]


def test_forbidden_subtitle_time_mutation_denied():
    decision = PolicyChecker().decide("modify_subtitle_time")
    assert decision.decision == "deny"
