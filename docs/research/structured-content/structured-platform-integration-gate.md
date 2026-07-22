# Structured Platform Integration Gate

## Automated

- Transactional Structured Fish materialization, relative generation paths, hash cache, conflict detection, and legacy active voiceover preservation.
- Structured Project creation validation and atomic publish.
- Markdown preamble preservation, aliases, Variant compilation, API/MCP regression coverage, backend tests, compileall, frontend build, and CI workflow.
- Canonical Chinese alias: `艾特引导` maps to `CTA_TAG`; `艺特引导` remains compatibility-only for the common typo.

## Mock validated

- Fish timestamp parsing, WAV generation, alignment, bindings, automatic subtitles, cached retry, variants, composition compilation, and export lowering are covered without a Fish credential.

## Manual validation pending

- Small real Fish Audio request.
- Independent portable launch.
- Browser full workflow and visual mobile check.
- At least one Structured Episode opened and played in JianYing.
- GitHub Actions run result after the Draft PR is created.

## Merge gate

CI must pass, all P0 transaction tests must pass, and the real Fish/portable/JianYing checks above must be recorded before merge. Release requires a post-merge full regression and a newly built package; do not reuse a pre-merge ZIP.
