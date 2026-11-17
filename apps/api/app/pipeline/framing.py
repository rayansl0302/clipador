from pathlib import Path
from statistics import median


TOP_WIDTH = 1080.0
TOP_HEIGHT = 1312.0


def _top_window(width: float, height: float) -> tuple[float, float]:
    crop_h = height
    crop_w = crop_h * TOP_WIDTH / TOP_HEIGHT
    if crop_w > width:
        crop_w = width
        crop_h = crop_w * TOP_HEIGHT / TOP_WIDTH
    return crop_w, crop_h


def subject_crop(
    width: float,
    height: float,
    face: tuple[float, float, float, float] | None,
) -> tuple[float, float, float, float]:
    if width <= 0 or height <= 0:
        return (0.0, 0.0, 1.0, 1.0)
    if face is None:
        crop_w, crop_h = _top_window(width, height)
        x = (width - crop_w) / 2
        y = (height - crop_h) / 2
        return (x / width, y / height, crop_w / width, crop_h / height)

    fx, fy, fw, fh = face
    center_x = fx + fw / 2
    center_y = fy + fh / 2
    crop_h = min(height, max(fh * 3.4, height * 0.72))
    crop_w = crop_h * TOP_WIDTH / TOP_HEIGHT
    if crop_w > width:
        crop_w = width
        crop_h = min(height, crop_w * TOP_HEIGHT / TOP_WIDTH)
    x = center_x - crop_w / 2
    y = center_y - crop_h * 0.42
    if fy < y:
        y = fy
    if fy + fh > y + crop_h:
        y = fy + fh - crop_h
    x = min(max(0.0, x), max(0.0, width - crop_w))
    y = min(max(0.0, y), max(0.0, height - crop_h))
    x, y, crop_w, crop_h = _above_lower_third(x, y, crop_w, crop_h, width, height, face)
    return (x / width, y / height, crop_w / width, crop_h / height)


def _above_lower_third(
    x: float,
    y: float,
    crop_w: float,
    crop_h: float,
    width: float,
    height: float,
    face: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    fx, fy, fw, fh = face
    limit = height * 0.76
    if fy + fh >= limit or y + crop_h <= limit:
        return x, y, crop_w, crop_h
    y -= (y + crop_h) - limit
    if y < 0:
        y = 0.0
        crop_h = limit
        crop_w = crop_h * TOP_WIDTH / TOP_HEIGHT
        if crop_w > width:
            crop_w = width
            crop_h = min(limit, crop_w * TOP_HEIGHT / TOP_WIDTH)
        x = min(max(0.0, (fx + fw / 2) - crop_w / 2), max(0.0, width - crop_w))
    if fy < y:
        y = fy
    if fy + fh > y + crop_h:
        y = fy + fh - crop_h
    x = min(max(0.0, x), max(0.0, width - crop_w))
    y = min(max(0.0, y), max(0.0, height - crop_h))
    return x, y, crop_w, crop_h


def detect_subject_window(path: Path) -> tuple[float, float, float, float]:
    try:
        import cv2
    except ImportError:
        return subject_crop(1920, 1080, None)

    capture = cv2.VideoCapture(str(path))
    width = float(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = float(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if width <= 0 or height <= 0:
        capture.release()
        return subject_crop(1920, 1080, None)

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces: list[tuple[float, float, float, float]] = []
    samples = 10
    for index in range(samples):
        if total > 0:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int((index + 0.5) / samples * (total - 1)))
        ok, frame = capture.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        found = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(28, 28))
        if len(found) == 0:
            continue
        x, y, w, h = max(found, key=lambda box: int(box[2]) * int(box[3]))
        faces.append((float(x), float(y), float(w), float(h)))
    capture.release()
    if not faces:
        return subject_crop(width, height, None)
    face = (
        float(median(item[0] for item in faces)),
        float(median(item[1] for item in faces)),
        float(median(item[2] for item in faces)),
        float(median(item[3] for item in faces)),
    )
    return subject_crop(width, height, face)
