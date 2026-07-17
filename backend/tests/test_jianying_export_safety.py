import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters import jianying


def _project(name: str = "Safety Project") -> dict:
    return {"id": "proj_safety", "name": name, "canvas": {"width": 1080, "height": 1920}}


def _fake_render(_project: dict, base_dir: Path, draft_name: str, _cue_points=None) -> Path:
    draft_dir = base_dir / draft_name
    draft_dir.mkdir(parents=True)
    (draft_dir / "draft_content.json").write_bytes(b"new draft")
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


def test_failed_create_new_removes_owned_staging_directory(monkeypatch, tmp_path):
    def fail_after_staging(_project: dict, base_dir: Path, draft_name: str, _cue_points=None) -> Path:
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

    def overlapping_render(project: dict, base_dir: Path, draft_name: str, cue_points=None):
        nonlocal render_calls
        render_calls += 1
        if render_calls == 1:
            nested_results.append(
                jianying.generate_jianying_draft(project, output_dir=tmp_path)
            )
        return _fake_render(project, base_dir, draft_name, cue_points)

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
    assert (source / "draft_content.json").read_bytes() == b"new draft"
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
