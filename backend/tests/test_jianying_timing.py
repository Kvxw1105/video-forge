import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared import time_utils


def test_media_duration_is_floored_to_milliseconds_for_jianying():
    assert time_utils.media_safe_seconds(60.055437) == 60.055
    assert time_utils.media_safe_seconds(1.999999) == 1.999
