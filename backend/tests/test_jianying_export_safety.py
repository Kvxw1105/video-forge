import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters import jianying


def _project(name: str = "Safety Project") -> dict:
    return {"id": "proj_safety", "name": name, "canvas": {"width": 1080, "height": 1920}}


def _fake_render(base_dir: Path, draft_name: str, _compiled=None) -> Path:
    draft_dir = base_dir / draft_name
    draft_dir.mkdir(parents=True)
    (draft_dir / "draft_content.json").write_text(
        json.dumps({"marker": "new draft"}), encoding="utf-8"
    )
    return draft_dir


def test_create_new_preserves_existing_draft_and_returns_metadata(monkeypatch, tmp_path):
    existing = tmp_path / "Safety Project"
    existing.mkdir()
    (existing / "draft_content.json").write_bytes(b"existing draft")
    monkeypatch.setattr(jianying, "_render_jianying_draft", _fake_render, raising=False)

    result = jianying.generate_jianying_draft(
        _project(), output_dir=tmp_path, policy="create_new", direct_export=True
    )

    assert (existing / "draft_content.json").read_bytes() == b"existing draft"
    assert result.policy == "create_new"
    assert result.final_path.exists()
    assert result.final_path.name != existing.name
    assert result.source_draft is None
    assert result.backup_path is None
    assert result.revision >= 1
    assert result.to_metadata()["finalDraftName"] == result.final_path.name


def test_direct_export_stages_outside_watched_draft_root(monkeypatch, tmp_path):
    observed = []

    def render(base_dir: Path, draft_name: str, _compiled=None):
        observed.append(base_dir)
        return _fake_render(base_dir, draft_name, _compiled)

    monkeypatch.setattr(jianying, "_render_jianying_draft", render)
    result = jianying.generate_jianying_draft(
        _project(), output_dir=tmp_path, policy="create_new", direct_export=True
    )

    assert observed[0].parent == tmp_path.parent
    assert result.final_path.parent == tmp_path
    assert not list(tmp_path.glob(".videoforge-staging-*"))


def test_failed_create_new_removes_owned_staging_directory(monkeypatch, tmp_path):
    def fail_after_staging(base_dir: Path, draft_name: str, _compiled=None) -> Path:
        draft_dir = base_dir / draft_name
        draft_dir.mkdir(parents=True)
        (draft_dir / "draft_content.json").write_bytes(b"partial")
        raise RuntimeError("render failed")

    monkeypatch.setattr(jianying, "_render_jianying_draft", fail_after_staging, raising=False)

    with pytest.raises(RuntimeError, match="render failed"):
        jianying.generate_jianying_draft(_project(), output_dir=tmp_path)

    assert not list(tmp_path.glob(".videoforge-staging-*"))
    assert not list(tmp_path.glob("Safety Project_*"))


def test_create_new_publish_conflict_never_deletes_other_writer_result(monkeypatch, tmp_path):
    monkeypatch.setattr(jianying, "_render_jianying_draft", _fake_render)
    real_rename = Path.rename

    def lose_publish_race(source: Path, target: Path):
        target = Path(target)
        if source.parent.name.startswith(".videoforge-staging-"):
            target.mkdir()
            (target / "draft_content.json").write_bytes(b"other writer")
            raise FileExistsError("publish collision")
        return real_rename(source, target)

    monkeypatch.setattr(jianying, "_rename_directory", lose_publish_race)

    with pytest.raises(FileExistsError, match="publish collision"):
        jianying.generate_jianying_draft(_project(), output_dir=tmp_path)

    published = list(tmp_path.glob("Safety Project_*"))
    assert len(published) == 1
    assert (published[0] / "draft_content.json").read_bytes() == b"other writer"
    assert not list(tmp_path.glob(".videoforge-staging-*"))


def test_concurrent_create_new_writers_complete_with_distinct_revisions(monkeypatch, tmp_path):
    nested_results = []
    render_calls = 0
    project = _project()

    def overlapping_render(base_dir: Path, draft_name: str, compiled=None):
        nonlocal render_calls
        render_calls += 1
        if render_calls == 1:
            nested_results.append(
                jianying.generate_jianying_draft(project, output_dir=tmp_path)
            )
        return _fake_render(base_dir, draft_name, compiled)

    monkeypatch.setattr(jianying, "_render_jianying_draft", overlapping_render)

    outer_result = jianying.generate_jianying_draft(_project(), output_dir=tmp_path)

    assert nested_results[0].final_path.exists()
    assert outer_result.final_path.exists()
    assert nested_results[0].final_path != outer_result.final_path
    assert {nested_results[0].revision, outer_result.revision} == {1, 2}


@pytest.mark.parametrize("source_draft", [None, "", "../draft", "a/b", r"a\\b", str(Path("C:/draft"))])
def test_replace_explicit_requires_a_single_valid_source_folder(monkeypatch, tmp_path, source_draft):
    monkeypatch.setattr(jianying, "_render_jianying_draft", _fake_render, raising=False)

    with pytest.raises(ValueError):
        jianying.generate_jianying_draft(
            _project(),
            output_dir=tmp_path,
            policy="replace_explicit",
            source_draft=source_draft,
            direct_export=True,
        )

    assert not list(tmp_path.iterdir())


def test_replace_explicit_backs_up_and_replaces_only_named_draft(monkeypatch, tmp_path):
    source = tmp_path / "Existing Draft"
    source.mkdir()
    (source / "draft_content.json").write_bytes(b"original draft")
    monkeypatch.setattr(jianying, "_render_jianying_draft", _fake_render, raising=False)

    result = jianying.generate_jianying_draft(
        _project(),
        output_dir=tmp_path,
        policy="replace_explicit",
        source_draft="Existing Draft",
        direct_export=True,
    )

    assert result.policy == "replace_explicit"
    assert result.source_draft == "Existing Draft"
    assert result.final_path == source
    assert json.loads((source / "draft_content.json").read_text(encoding="utf-8"))["marker"] == "new draft"
    assert result.backup_path is not None
    assert (result.backup_path / "draft_content.json").read_bytes() == b"original draft"
    assert result.backup_path.parent == tmp_path / ".videoforge-backups"


def test_replace_explicit_restores_backup_when_publish_fails(monkeypatch, tmp_path):
    source = tmp_path / "Existing Draft"
    source.mkdir()
    (source / "draft_content.json").write_bytes(b"original draft")
    monkeypatch.setattr(jianying, "_render_jianying_draft", _fake_render, raising=False)

    calls = []
    real_rename = Path.rename

    def fail_publish(self: Path, target: Path):
        calls.append((self.name, Path(target).name))
        if self.name == "Existing Draft" and Path(target).name == "Existing Draft":
            raise OSError("publish failed")
        return real_rename(self, target)

    monkeypatch.setattr(jianying, "_rename_directory", fail_publish, raising=False)

    with pytest.raises(OSError, match="publish failed"):
        jianying.generate_jianying_draft(
            _project(),
            output_dir=tmp_path,
            policy="replace_explicit",
            source_draft="Existing Draft",
            direct_export=True,
        )

    assert (source / "draft_content.json").read_bytes() == b"original draft"
    assert calls
    assert not list(tmp_path.glob(".videoforge-staging-*"))


def test_replace_explicit_exposes_backup_when_publish_and_rollback_fail(monkeypatch, tmp_path):
    source = tmp_path / "Existing Draft"
    source.mkdir()
    (source / "draft_content.json").write_bytes(b"original draft")
    monkeypatch.setattr(jianying, "_render_jianying_draft", _fake_render)
    real_rename = Path.rename

    def fail_publish_and_restore(source_path: Path, target_path: Path):
        target_path = Path(target_path)
        if source_path.parent.name.startswith(".videoforge-staging-"):
            raise OSError("publish failed")
        if source_path.parent.name == ".videoforge-backups" and target_path.name == "Existing Draft":
            raise PermissionError("rollback failed")
        return real_rename(source_path, target_path)

    monkeypatch.setattr(jianying, "_rename_directory", fail_publish_and_restore)

    with pytest.raises(jianying.DraftRollbackError) as error:
        jianying.generate_jianying_draft(
            _project(),
            output_dir=tmp_path,
            policy="replace_explicit",
            source_draft="Existing Draft",
            direct_export=True,
        )

    assert "publish failed" in str(error.value)
    assert "rollback failed" in str(error.value)
    assert error.value.backup_path.exists()
    assert str(error.value.backup_path) in str(error.value)


def test_real_renderer_writes_minimal_jianying_draft(tmp_path):
    importlib.reload(jianying)
    result = jianying.generate_jianying_draft(_project(), output_dir=tmp_path)

    assert (result.final_path / "draft_content.json").is_file()
    assert (result.final_path / "draft_meta_info.json").is_file()


def test_publish_rewrites_generated_media_paths_out_of_staging(monkeypatch, tmp_path):
    def render_with_generated_media(base_dir: Path, draft_name: str, _compiled=None):
        draft_dir = base_dir / draft_name
        draft_dir.mkdir(parents=True)
        generated = draft_dir / "_adj_source.png"
        generated.write_bytes(b"png")
        (draft_dir / "draft_content.json").write_text(
            json.dumps({"materials": {"videos": [{"path": str(generated)}]}}),
            encoding="utf-8",
        )
        return draft_dir

    monkeypatch.setattr(jianying, "_render_jianying_draft", render_with_generated_media)

    result = jianying.generate_jianying_draft(_project(), output_dir=tmp_path)
    content = json.loads(
        (result.final_path / "draft_content.json").read_text(encoding="utf-8")
    )
    media_path = Path(content["materials"]["videos"][0]["path"])

    assert media_path == result.final_path / "_adj_source.png"
    assert media_path.is_file()
    assert ".videoforge-staging-" not in str(media_path)


def _render_with_media_path(base_dir: Path, draft_name: str, _compiled=None):
    draft_dir = base_dir / draft_name
    draft_dir.mkdir(parents=True)
    generated = draft_dir / "_adj_source.png"
    generated.write_bytes(b"png")
    (draft_dir / "draft_content.json").write_text(
        json.dumps({"materials": {"videos": [{"path": str(generated)}]}}),
        encoding="utf-8",
    )
    return draft_dir


def test_media_paths_are_rewritten_before_create_new_publish(monkeypatch, tmp_path):
    monkeypatch.setattr(jianying, "_render_jianying_draft", _render_with_media_path)
    real_rename = jianying._rename_directory
    observed = []

    def inspect_rename(source: Path, target: Path):
        if source.parent.name.startswith(".videoforge-staging-"):
            content = json.loads((source / "draft_content.json").read_text(encoding="utf-8"))
            observed.append(content["materials"]["videos"][0]["path"])
            assert observed[-1] == str(target / "_adj_source.png")
        return real_rename(source, target)

    monkeypatch.setattr(jianying, "_rename_directory", inspect_rename)
    result = jianying.generate_jianying_draft(_project(), output_dir=tmp_path)

    assert observed == [str(result.final_path / "_adj_source.png")]


def test_create_new_rewrite_missing_content_rejects_publish(monkeypatch, tmp_path):
    def render_without_content(base_dir: Path, draft_name: str, _compiled=None):
        draft_dir = base_dir / draft_name
        draft_dir.mkdir(parents=True)
        raise jianying.DraftMediaPathRewriteError(
            "failed to rewrite generated JianYing media paths: draft_content.json is missing"
        )

    monkeypatch.setattr(jianying, "_render_jianying_draft", render_without_content)

    with pytest.raises(jianying.DraftMediaPathRewriteError, match="draft_content.json is missing"):
        jianying.generate_jianying_draft(_project(), output_dir=tmp_path)

    assert not list(tmp_path.glob("Safety Project_*"))
    assert not list(tmp_path.glob(".videoforge-staging-*"))
    assert not list((tmp_path / ".videoforge-reservations").glob("*") )


def test_create_new_parse_failure_rejects_publish(monkeypatch, tmp_path):
    def render_invalid_content(base_dir: Path, draft_name: str, _compiled=None):
        draft_dir = base_dir / draft_name
        draft_dir.mkdir(parents=True)
        (draft_dir / "draft_content.json").write_text("{invalid", encoding="utf-8")
        return draft_dir

    monkeypatch.setattr(jianying, "_render_jianying_draft", render_invalid_content)

    with pytest.raises(jianying.DraftMediaPathRewriteError, match="failed to rewrite"):
        jianying.generate_jianying_draft(_project(), output_dir=tmp_path)

    assert not list(tmp_path.glob("Safety Project_*"))
    assert not list(tmp_path.glob(".videoforge-staging-*"))


def test_replace_explicit_rewrite_failure_preserves_original_without_backup(monkeypatch, tmp_path):
    source = tmp_path / "Existing Draft"
    source.mkdir()
    original = json.dumps({"marker": "original"})
    (source / "draft_content.json").write_text(original, encoding="utf-8")

    def render_invalid_content(base_dir: Path, draft_name: str, _compiled=None):
        draft_dir = base_dir / draft_name
        draft_dir.mkdir(parents=True)
        (draft_dir / "draft_content.json").write_text("not json", encoding="utf-8")
        return draft_dir

    monkeypatch.setattr(jianying, "_render_jianying_draft", render_invalid_content)

    with pytest.raises(jianying.DraftMediaPathRewriteError):
        jianying.generate_jianying_draft(
            _project(), output_dir=tmp_path, policy="replace_explicit",
            source_draft="Existing Draft", direct_export=True,
        )

    assert (source / "draft_content.json").read_text(encoding="utf-8") == original
    assert not (tmp_path / ".videoforge-backups").exists()
    assert not list(tmp_path.glob(".videoforge-staging-*"))


def test_rewrite_write_failure_is_atomic_and_cleans_temp(monkeypatch, tmp_path):
    monkeypatch.setattr(jianying, "_render_jianying_draft", _render_with_media_path)
    real_replace = jianying.os.replace

    def fail_rewrite_replace(source: Path, target: Path):
        if ".videoforge-rewrite-" in Path(source).name:
            raise OSError("simulated rewrite write failure")
        return real_replace(source, target)

    monkeypatch.setattr(jianying.os, "replace", fail_rewrite_replace)

    with pytest.raises(jianying.DraftMediaPathRewriteError, match="failed to rewrite"):
        jianying.generate_jianying_draft(_project(), output_dir=tmp_path)

    assert not list(tmp_path.glob("Safety Project_*"))
    assert not list(tmp_path.glob(".videoforge-staging-*"))
    assert not list(tmp_path.rglob("*.videoforge-rewrite-*.tmp"))


def test_rewrite_only_changes_paths_with_real_staging_prefix(tmp_path):
    staged = tmp_path / ".videoforge-staging-abc"
    staged.mkdir()
    final = tmp_path / "Final Draft"
    sibling = str(tmp_path / ".videoforge-staging-abc-other" / "media.png")
    payload = {
        "paths": [str(staged / "media.png"), sibling],
        "nested": {"path": str(staged / "nested" / "file.png")},
    }
    content_file = staged / "draft_content.json"
    content_file.write_text(json.dumps(payload), encoding="utf-8")

    jianying._rewrite_draft_media_paths(staged, staged, final)
    rewritten = json.loads(content_file.read_text(encoding="utf-8"))

    assert rewritten["paths"][0] == str(final / "media.png")
    assert rewritten["paths"][1] == sibling
    assert rewritten["nested"]["path"] == str(final / "nested" / "file.png")


def test_replace_explicit_publishes_rewritten_media_and_keeps_backup(monkeypatch, tmp_path):
    source = tmp_path / "Existing Draft"
    source.mkdir()
    (source / "draft_content.json").write_text(
        json.dumps({"marker": "original"}), encoding="utf-8"
    )
    monkeypatch.setattr(jianying, "_render_jianying_draft", _render_with_media_path)

    result = jianying.generate_jianying_draft(
        _project(), output_dir=tmp_path, policy="replace_explicit",
        source_draft="Existing Draft", direct_export=True,
    )
    content = json.loads((source / "draft_content.json").read_text(encoding="utf-8"))
    media_path = Path(content["materials"]["videos"][0]["path"])

    assert media_path == source / "_adj_source.png"
    assert media_path.is_file()
    assert result.backup_path is not None
    assert json.loads((result.backup_path / "draft_content.json").read_text(encoding="utf-8"))["marker"] == "original"


def test_generate_compiles_once_and_propagates_warnings(monkeypatch, tmp_path):
    compiled = type("Compiled", (), {"warnings": ("missing asset",)})()
    compile_calls = []

    def fake_compile(*args, **kwargs):
        compile_calls.append((args, kwargs))
        return compiled

    def fake_render(base_dir, draft_name, compiled_timeline):
        assert compiled_timeline is compiled
        return _fake_render(base_dir, draft_name, compiled_timeline)

    monkeypatch.setattr(jianying, "compile_project_timeline", fake_compile)
    monkeypatch.setattr(jianying, "_render_jianying_draft", fake_render)

    result = jianying.generate_jianying_draft(_project(), output_dir=tmp_path)

    assert len(compile_calls) == 1
    assert result.warnings == ("missing asset",)
    assert result.to_metadata()["warnings"] == ["missing asset"]


def test_generate_merges_adapter_warnings_into_result(monkeypatch, tmp_path):
    def render_with_warning(base_dir, draft_name, compiled):
        return _fake_render(base_dir, draft_name, compiled), ("adapter warning sentinel",)

    monkeypatch.setattr(jianying, "_render_jianying_draft", render_with_warning)
    result = jianying.generate_jianying_draft(_project(), output_dir=tmp_path)
    assert result.warnings == ("adapter warning sentinel",)
    assert result.to_metadata()["warnings"] == ["adapter warning sentinel"]
