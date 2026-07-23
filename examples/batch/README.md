# Template Batch Examples

Use `vforge batch-plan --spec @examples/batch/plain-script-batch.json` before starting a batch. Examples contain no credentials or local asset paths. A plan never creates projects or calls TTS; `batch-start` may call a provider only when the spec explicitly enables one.
