import struct
import zlib

from visual_assets.rasterizer import validate_png_alpha


def chunk(kind, data):
    import binascii
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)


def test_png_alpha_validation_rejects_no_alpha(tmp_path):
    path = tmp_path / "rgb.png"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00")) + chunk(b"IEND", b""))
    assert "png has no alpha channel" in validate_png_alpha(path, 1, 1)
