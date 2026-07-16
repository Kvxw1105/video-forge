import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_parse_jianying_draft_extracts_video_scale_and_subtitle_size(tmp_path):
    from adapters.jianying_reader import parse_jianying_draft

    draft = tmp_path / "Draft"
    draft.mkdir()
    (draft / "draft_content.json").write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "type": "video",
                        "segments": [
                            {
                                "id": "video_seg_1",
                                "material_id": "video_mat_1",
                                "target_timerange": {"start": 1000000, "duration": 2500000},
                                "clip": {
                                    "scale": {"x": 1.25, "y": 1.25},
                                    "transform": {"x": 0.12, "y": -0.2},
                                    "rotation": 3.0,
                                },
                                "uniform_scale": {"on": True, "value": 1.25},
                            }
                        ],
                    },
                    {
                        "type": "text",
                        "segments": [
                            {
                                "id": "text_seg_1",
                                "material_id": "text_mat_1",
                                "target_timerange": {"start": 3000000, "duration": 1200000},
                                "clip": {
                                    "scale": {"x": 1.0, "y": 1.0},
                                    "transform": {"x": 0.0, "y": 0.78},
                                },
                            }
                        ],
                    },
                ],
                "materials": {
                    "videos": [{"id": "video_mat_1", "path": "C:/media/a.png"}],
                    "texts": [
                        {
                            "id": "text_mat_1",
                            "type": "subtitle",
                            "content": json.dumps(
                                {
                                    "text": "底部字幕",
                                    "styles": [{"range": [0, 4], "size": 12, "bold": False}],
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    parsed = parse_jianying_draft(draft)

    assert parsed["draftPath"] == str(draft)
    assert parsed["videoSegments"] == [
        {
            "id": "video_seg_1",
            "materialId": "video_mat_1",
            "path": "C:/media/a.png",
            "start": 1.0,
            "duration": 2.5,
            "scaleX": 1.25,
            "scaleY": 1.25,
            "uniformScale": 1.25,
            "transformX": 0.12,
            "transformY": -0.2,
            "rotation": 3.0,
        }
    ]
    assert parsed["textSegments"] == [
        {
            "id": "text_seg_1",
            "materialId": "text_mat_1",
            "type": "subtitle",
            "text": "底部字幕",
            "start": 3.0,
            "duration": 1.2,
            "fontSize": 12,
            "styleSizes": [12],
            "scaleX": 1.0,
            "scaleY": 1.0,
            "transformX": 0.0,
            "transformY": 0.78,
        }
    ]


def test_jianying_draft_params_endpoint_reads_configured_draft_dir(monkeypatch, tmp_path):
    from routers import export

    root = tmp_path / "draft_root"
    draft = root / "MyDraft"
    draft.mkdir(parents=True)
    (draft / "draft_content.json").write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "type": "video",
                        "segments": [
                            {
                                "id": "seg",
                                "material_id": "mat",
                                "target_timerange": {"start": 0, "duration": 1000000},
                                "clip": {"scale": {"x": 0.8, "y": 0.8}, "transform": {"x": 0, "y": 0}},
                                "uniform_scale": {"value": 0.8},
                            }
                        ],
                    }
                ],
                "materials": {"videos": [{"id": "mat", "path": "C:/a.png"}], "texts": []},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(export, "JIANYING_DRAFT_DIR", root.resolve())

    result = export.get_jianying_draft_params("MyDraft")

    assert result["videoSegments"][0]["uniformScale"] == 0.8
