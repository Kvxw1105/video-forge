from . import white_sketch, silhouette, pixel_rules, mechanism_diagram
REGISTRY={m.renderer_id:m for m in [white_sketch,silhouette,pixel_rules,mechanism_diagram]}
