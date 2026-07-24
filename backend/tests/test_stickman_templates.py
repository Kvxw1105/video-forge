from visual_assets.stickman.templates import CORE_TEMPLATE_IDS, FALLBACK_TEMPLATE_IDS, TEMPLATES


def test_template_counts_and_metadata():
    assert len(CORE_TEMPLATE_IDS) == 16
    assert len(FALLBACK_TEMPLATE_IDS) == 3
    assert len(TEMPLATES) == 19
    for template in TEMPLATES.values():
        assert template.template_version
        assert template.supported_actor_count
        assert template.default_composition
        assert template.default_motion_hint
        assert template.validate_parameters({"tension": 3})["tension"] == 1.0
