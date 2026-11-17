from app.pipeline.framing import subject_crop


def test_face_window_keeps_the_person_for_the_top_panel() -> None:
    face = (860.0, 820.0, 200.0, 180.0)
    x, y, w, h = subject_crop(1920, 1080, face)
    assert abs((w * 1920) / (h * 1080) - (1080 / 1312)) < 0.02
    assert h < 0.95
    left = x * 1920
    top = y * 1080
    assert left <= face[0] + face[2] / 2 <= left + w * 1920
    assert top <= face[1]
    assert face[1] + face[3] <= top + h * 1080 + 1


def test_crop_stops_above_the_fixed_lower_third() -> None:
    face = (700.0, 420.0, 180.0, 160.0)
    x, y, w, h = subject_crop(1920, 1080, face)
    assert y + h <= 0.77
    top = y * 1080
    assert top <= face[1]
    assert face[1] + face[3] <= top + h * 1080 + 1


def test_without_a_face_the_window_is_centered() -> None:
    x, y, w, h = subject_crop(1920, 1080, None)
    assert abs(y) < 0.01
    assert abs((x + w / 2) - 0.5) < 0.01
    assert abs((w * 1920) / (h * 1080) - (1080 / 1312)) < 0.02
