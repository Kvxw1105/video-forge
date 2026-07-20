import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routers.assets import _safe_upload_name
from routers.library import _safe_display_name
from routers.voiceover import MAX_SCRIPT_CHARS


@pytest.mark.parametrize("value", ["", ".", "..", "bad?.png"])
def test_upload_names_reject_traversal_and_windows_invalid_chars(value):
    with pytest.raises(HTTPException):
        _safe_upload_name(value)
    with pytest.raises(HTTPException):
        _safe_display_name(value)


def test_upload_names_keep_unicode_and_spaces():
    name = "我的素材 01.png"
    assert _safe_upload_name(name) == name
    assert _safe_display_name(name) == name


def test_upload_names_strip_browser_folder_prefixes():
    assert _safe_upload_name("folder/subfolder/clip.png") == "clip.png"
    assert _safe_display_name("folder\\subfolder\\clip.png") == "clip.png"


def test_script_limit_allows_long_form_but_has_a_defined_ceiling():
    assert MAX_SCRIPT_CHARS >= 50000
