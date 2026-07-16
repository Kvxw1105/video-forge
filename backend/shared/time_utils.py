import math


def media_safe_seconds(seconds: float) -> float:
    return math.floor(max(0.0, float(seconds)) * 1000) / 1000
