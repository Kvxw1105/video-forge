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
