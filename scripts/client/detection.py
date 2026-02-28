"""
Frame quality gates, CAT color detection, bounding-box tracking, and coverage heat-map.
"""

import time

import cv2
import numpy as np

from .constants import SMOOTHING_ALPHA, TRACK_MAX_AGE


# ── Geometry helpers ────────────────────────────────────────────────────────

def iou(a, b):
    """IoU for two normalized [x1,y1,x2,y2] bboxes."""
    if len(a) < 4 or len(b) < 4:
        return 0.0
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter  = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union  = area_a + area_b - inter
    return inter / union if union > 0.0 else 0.0


# ── Frame quality ───────────────────────────────────────────────────────────

def blur_score(frame):
    """Laplacian variance — higher value means sharper frame."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def motion_score(prev_gray, curr_gray):
    """Mean absolute pixel difference between consecutive frames."""
    if prev_gray is None:
        return 999.0
    return cv2.absdiff(prev_gray, curr_gray).mean()


# ── CAT equipment color detector ────────────────────────────────────────────

def detect_cat_colors(frame):
    """Return True if the frame contains CAT equipment's yellow+black color signature."""
    hsv   = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    total = frame.shape[0] * frame.shape[1]
    yellow_pct = cv2.countNonZero(cv2.inRange(hsv, (18, 80, 140), (38, 255, 255))) / total
    black_pct  = cv2.countNonZero(cv2.inRange(hsv, (0, 0, 0), (180, 80, 50)))      / total
    return yellow_pct > 0.03 and black_pct > 0.02


# ── Detection tracking ──────────────────────────────────────────────────────

class Track:
    __slots__ = ("label", "bbox", "confidence", "track_id", "age", "hits", "zone")

    def __init__(self, label, bbox, confidence, track_id):
        self.label      = label
        self.bbox       = np.array(bbox, dtype=np.float64)
        self.confidence = confidence
        self.track_id   = track_id
        self.age        = 0
        self.hits       = 1
        self.zone       = None


class DetectionSmoother:
    """
    IoU-based multi-object tracker with EMA bbox smoothing.

    Each incoming detection is matched to the closest existing track (by IoU).
    Matched tracks get their bbox updated via exponential moving average.
    Unmatched tracks age out; new detections spawn new tracks.
    """

    def __init__(self, alpha=SMOOTHING_ALPHA, max_age=TRACK_MAX_AGE):
        self.alpha    = alpha
        self.max_age  = max_age
        self.tracks   = []
        self._next_id = 0

    def update(self, detections):
        if not detections:
            for t in self.tracks:
                t.age += 1
            self.tracks = [t for t in self.tracks if t.age < self.max_age]
            return list(self.tracks)

        used_tracks, used_dets = set(), set()
        pairs = [
            (iou(track.bbox, det["bbox"]), ti, di)
            for ti, track in enumerate(self.tracks)
            for di, det   in enumerate(detections)
            if iou(track.bbox, det["bbox"]) > 0.15
        ]
        pairs.sort(key=lambda p: p[0], reverse=True)

        for _, ti, di in pairs:
            if ti in used_tracks or di in used_dets:
                continue
            det, track = detections[di], self.tracks[ti]
            track.bbox       = self.alpha * np.array(det["bbox"], dtype=np.float64) + (1 - self.alpha) * track.bbox
            track.label      = det.get("label",      track.label)
            track.confidence = det.get("confidence", track.confidence)
            track.zone       = det.get("zone",       track.zone)
            track.age        = 0
            track.hits      += 1
            used_tracks.add(ti)
            used_dets.add(di)

        for ti, track in enumerate(self.tracks):
            if ti not in used_tracks:
                track.age += 1

        for di, det in enumerate(detections):
            if di not in used_dets:
                t       = Track(det.get("label", "?"), det["bbox"], det.get("confidence", 0), self._next_id)
                t.zone  = det.get("zone")
                self._next_id += 1
                self.tracks.append(t)

        self.tracks = [t for t in self.tracks if t.age < self.max_age]
        return list(self.tracks)


# ── Fast safety event detector ──────────────────────────────────────────────

class FastEventDetector:
    """
    Detects person-fall events from a sliding window of YOLO person bboxes.

    Triggers on:
    - Rapid downward center-y velocity combined with aspect-ratio flip (upright → horizontal)
    - Extreme downward velocity alone
    - Person present in early window frames but gone in recent frames (sudden disappearance)

    Includes a per-alert cooldown to avoid repeated callouts for the same event.
    """

    def __init__(self, window=8):
        self._history        = []
        self._alert_cooldown = 0.0
        self._window         = window

    def check(self, detections):
        now = time.time()
        if now - self._alert_cooldown < 6.0:
            return None

        persons = [d for d in detections if d.get("label", "").lower() == "person"]
        if persons:
            best = max(persons, key=lambda d: d.get("confidence", 0))
            bb   = best.get("bbox", [0, 0, 0, 0])
            cy   = (bb[1] + bb[3]) / 2.0
            ar   = (bb[2] - bb[0]) / max(bb[3] - bb[1], 1)
            self._history.append({"t": now, "cy": cy, "h": bb[3] - bb[1], "ar": ar})
        else:
            self._history.append({"t": now, "cy": None, "h": 0, "ar": 0})

        self._history = [e for e in self._history if now - e["t"] < 3.0][-self._window:]

        valid = [e for e in self._history if e["cy"] is not None]
        if len(valid) < 3:
            return None

        first, last = valid[0], valid[-1]
        dt = last["t"] - first["t"]
        if dt < 0.3:
            return None

        velocity = (last["cy"] - first["cy"]) / dt

        if velocity > 200 and last["ar"] > 1.2 and first["ar"] < 1.0:
            self._alert_cooldown = now
            return "Person down detected"

        if velocity > 300:
            self._alert_cooldown = now
            return "Rapid downward movement"

        was_present = any(e["cy"] is not None for e in self._history[:3])
        now_gone    = all(e["cy"] is None     for e in self._history[-3:])
        if was_present and now_gone:
            self._alert_cooldown = now
            return "Person left frame suddenly"

        return None


# ── Coverage heat-map ───────────────────────────────────────────────────────

class CoverageHeatmap:
    """
    Accumulates a Gaussian heat-map of detection centers to estimate spatial coverage.

    Each detection nudges a Gaussian blob at its center. coverage_pct() reports
    the fraction of grid cells that have been "visited" above a threshold.
    """

    def __init__(self, width=80, height=60, sigma=5.0):
        self.w    = width
        self.h    = height
        self.hmap = np.zeros((height, width), dtype=np.float64)
        gy, gx    = np.ogrid[-height:height, -width:width]
        self._kernel = np.exp(-(gx * gx + gy * gy) / (2.0 * sigma * sigma))

    def accumulate(self, detections):
        for det in detections:
            bbox = det.get("bbox", det) if isinstance(det, dict) else det
            if hasattr(bbox, "bbox"):
                bbox = bbox.bbox
            if not hasattr(bbox, "__len__") or len(bbox) != 4:
                continue
            cx = max(0, min(int(((bbox[0] + bbox[2]) / 2.0) * self.w), self.w - 1))
            cy = max(0, min(int(((bbox[1] + bbox[3]) / 2.0) * self.h), self.h - 1))
            ky1, ky2 = self.h - cy, self.h - cy + self.h
            kx1, kx2 = self.w - cx, self.w - cx + self.w
            self.hmap += self._kernel[ky1:ky2, kx1:kx2]

    def coverage_pct(self):
        if self.hmap.max() == 0:
            return 0.0
        return float(np.mean(self.hmap / self.hmap.max() > 0.1) * 100)

    def render(self, size=(140, 80)):
        if self.hmap.max() == 0:
            return np.zeros((size[1], size[0], 3), dtype=np.uint8)
        norm    = (self.hmap / self.hmap.max() * 255).astype(np.uint8)
        colored = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
        return cv2.resize(colored, size, interpolation=cv2.INTER_NEAREST)
