from pathlib import Path

from visual_assets.rasterizer import FfmpegSvgRasterizer, PillowSvgRasterizer, RasterizeResult


class UnavailableRasterizer:
    rasterizer_id = "none"
    rasterizer_version = "test"
    def is_available(self): return False
    def rasterize(self, svg_path: Path, png_path: Path, width: int, height: int): return RasterizeResult(False, None, "png_converter_unavailable", "no converter")


def test_rasterizer_protocol_unavailable(tmp_path):
    r = UnavailableRasterizer()
    assert not r.is_available()
    assert r.rasterize(tmp_path / "x.svg", tmp_path / "x.png", 1, 1).error_code == "png_converter_unavailable"


def test_ffmpeg_rasterizer_availability_probe_is_boolean():
    assert isinstance(FfmpegSvgRasterizer().is_available(), bool)


def test_pillow_rasterizer_publishes_png_and_cleans_png_staging(tmp_path):
    svg = tmp_path / "asset.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"><line x1="2" y1="2" x2="18" y2="18" stroke="#FFFFFF" stroke-width="2"/></svg>',
        encoding="utf-8",
    )
    output = tmp_path / "asset.png"
    result = PillowSvgRasterizer().rasterize(svg, output, 20, 20)
    assert result.succeeded
    assert output.exists() and output.stat().st_size > 0
    assert not (tmp_path / ".asset.tmp.png").exists()
