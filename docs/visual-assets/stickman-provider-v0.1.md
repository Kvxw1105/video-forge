# Stickman Visual Asset Provider v0.1

Prepare a project with structuredContent.episode.visualPlan and subtitle-timed
VisualScenes. The provider uses each Scene's subtitleIds and never invents
Scene timing.

Render and bind PNG assets:

    vforge stickman render --project proj_xxx --source visual-plan --png --bind

Regenerate one Scene:

    vforge stickman regenerate --project proj_xxx --scene scene_001 --png

HTTP request:

    POST /api/projects/proj_xxx/visual-assets/stickman/render
    {"sourceMode":"visual_plan","exportPng":true,"bindToProject":true}

MCP: call render_stickman_assets(pid="proj_xxx").

Outputs live below projects/<project_id>/visual-assets/stickman/<run_id>/ and
include SVG/PNG assets, manifest, report, events, and contact sheet. PNG assets
are copied into projects/<project_id>/assets/, registered in Project.assets,
and bound to the matching VisualScene.

The provider has 16 core templates and 3 fallback templates. Routing is
structured-field first, deterministic, and makes zero LLM or AI-image calls.
It skips unchanged content and protects non-provider user assets by default.

Known limits: no stickman skeletal animation, no independent overlay above
background video, no multi-track picture-in-picture, and no frontend editor.
