import asyncio
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_import_srt_updates_script_and_subtitles_while_preserving_style(monkeypatch):
    from routers import subtitle

    project = SimpleNamespace(
        id="proj_1",
        name="测试项目",
        subtitles=[
            SimpleNamespace(
                style={
                    "fontSize": 48,
                    "color": "#ffeeaa",
                    "strokeColor": "#111111",
                    "strokeWidth": 3,
                    "position": "top_center",
                }
            )
        ],
    )
    saved = {}
    monkeypatch.setattr(subtitle, "get_project", lambda project_id: project)

    def fake_update(project_id, data):
        saved.update(data)
        return SimpleNamespace(model_dump=lambda: {"id": project_id, **data})

    monkeypatch.setattr(subtitle, "update_project", fake_update)
    raw = (
        "1\r\n00:00:00,000 --> 00:00:01,000\r\n第一条\r\n\r\n"
        "bad block\r\n\r\n"
        "2\r\n00:00:01,100 --> 00:00:02,500\r\n第二条\r\n"
    ).encode("utf-8-sig")
    upload = UploadFile(filename="captions.srt", file=io.BytesIO(raw))

    result = asyncio.run(subtitle.import_srt("proj_1", upload))

    assert saved["script"] == "第一条\n第二条"
    assert [item["text"] for item in saved["subtitles"]] == ["第一条", "第二条"]
    assert saved["subtitles"][0]["style"]["fontSize"] == 48
    assert saved["subtitles"][0]["style"]["position"] == "top_center"
    assert result["subtitleCount"] == 2
    assert result["ignoredCount"] == 1
    assert result["project"]["script"] == "第一条\n第二条"


def test_import_srt_uses_readable_default_font_size(monkeypatch):
    from routers import subtitle

    project = SimpleNamespace(id="proj_1", name="测试项目", subtitles=[])
    saved = {}
    monkeypatch.setattr(subtitle, "get_project", lambda project_id: project)

    def fake_update(project_id, data):
        saved.update(data)
        return SimpleNamespace(model_dump=lambda: {"id": project_id, **data})

    monkeypatch.setattr(subtitle, "update_project", fake_update)
    raw = "1\n00:00:00,000 --> 00:00:01,000\n默认字号\n".encode("utf-8")
    upload = UploadFile(filename="captions.srt", file=io.BytesIO(raw))

    asyncio.run(subtitle.import_srt("proj_1", upload))

    assert saved["subtitles"][0]["style"]["fontSize"] == 48


def test_export_srt_returns_utf8_bom_attachment(monkeypatch):
    from routers import subtitle

    project = SimpleNamespace(
        name='项目:一/测试',
        subtitles=[
            SimpleNamespace(
                model_dump=lambda: {
                    "id": "sub_1",
                    "text": "字幕内容",
                    "start": 0.25,
                    "end": 1.5,
                    "style": {},
                }
            )
        ],
    )
    monkeypatch.setattr(subtitle, "get_project", lambda project_id: project)

    response = subtitle.export_srt("proj_1")

    assert response.media_type == "application/x-subrip"
    assert response.body.startswith(b"\xef\xbb\xbf")
    assert "00:00:00,250 --> 00:00:01,500" in response.body.decode("utf-8-sig")
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert "%E9%A1%B9%E7%9B%AE_%E4%B8%80_%E6%B5%8B%E8%AF%95.srt" in response.headers["content-disposition"]


def test_export_srt_rejects_project_without_subtitles(monkeypatch):
    from routers import subtitle

    monkeypatch.setattr(
        subtitle,
        "get_project",
        lambda project_id: SimpleNamespace(name="Empty", subtitles=[]),
    )

    with pytest.raises(HTTPException) as exc:
        subtitle.export_srt("proj_1")

    assert exc.value.status_code == 400
    assert "没有可导出的字幕" in str(exc.value.detail)
