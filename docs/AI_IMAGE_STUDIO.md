# AI Image Studio

`/image-studio` turns a project's existing `VisualPlan.scenes` into a parallel
AI image batch. It does not create another project, scene model, or timeline.

## Provider Contract

The initial adapter is OpenAI-image compatible:

```text
GET  {baseUrl}/models
POST {baseUrl}/images/generations
```

The generation request contains `model`, `prompt`, `n`, `size`, and
`response_format: b64_json`. URL responses are also accepted. Settings are
stored only in `config/ai_image_provider.json`; the API returns an empty key
field plus `apiKeyConfigured`.

## Workflow

1. Open `/image-studio`, select a project, and edit Scene prompts.
2. Configure the provider, test the connection, fetch models, and save.
3. Start one batch. The backend runs Scene requests concurrently up to the
   saved `maxConcurrency` limit.
4. Review candidates and select one candidate per Scene.
5. Approve the selected candidates. VideoForge copies them to project assets,
   registers normal `Project.assets` image records, and updates each matching
   `VisualScene.primaryAssetId` and `visualAssetIds`.

Batch manifests and unapproved candidates live under:

```text
projects/{project_id}/visual-assets/ai-image/{batch_id}/manifest.json
```

Approved images are copied to `projects/{project_id}/assets/`. The normal
Preview and JianYing paths consume the resulting Scene bindings.
