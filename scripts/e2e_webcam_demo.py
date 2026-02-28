#!/usr/bin/env python3
"""
Dronecat inspection client — YOLO + async VLM + voice I/O.

  export MODAL_WS_URL=wss://...
  python3 scripts/e2e_webcam_demo.py
  python3 scripts/e2e_webcam_demo.py --url wss://... --serial CAT0325F4K01847

Keys: [g] General  [c] CAT  [r] Report  [e] Evidence  [p] Part ID  [m] Mute mic  [q] Quit
"""

import argparse
import asyncio
import base64
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

CAMERA_DEVICE = 0
FRAME_INTERVAL = 0.2
FORCE_SEND_MS = 350
JPEG_QUALITY = 85
BLUR_THRESHOLD = 100.0
MOTION_THRESHOLD = 1.0
SAMPLE_RATE = 16000
VAD_THRESHOLD = 0.5
SMOOTHING_ALPHA = 0.4
TRACK_MAX_AGE = 8
DETECTION_TTL_S = 1.2
ANALYSIS_TTL_S = 8.0
CALLOUT_COOLDOWN_S = 5.0

# COCO labels irrelevant to CAT inspection — suppress from terminal/display
_IGNORE_LABELS = {
    "person", "chair", "tv", "laptop", "cell phone", "book", "bottle",
    "cup", "clock", "keyboard", "mouse", "remote", "couch", "potted plant",
    "bed", "dining table", "toilet", "sink", "refrigerator", "microwave",
    "oven", "toaster", "wine glass", "fork", "knife", "spoon", "bowl",
    "banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog",
    "pizza", "donut", "cake", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush", "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis",
    "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket",
}

ALL_ZONES = [
    "boom_arm", "bucket", "cab", "cooling", "drivetrain",
    "engine", "hydraulics", "steps_handrails", "stick",
    "structural", "tires_rims", "tracks_left", "tracks_right",
    "undercarriage", "attachments",
]

ZONE_COLORS = {
    "GREEN": (0, 200, 0),
    "YELLOW": (0, 200, 255),
    "RED": (0, 0, 220),
    "GRAY": (120, 120, 120),
}


# ── Fast Event Detector (runs on YOLO detections, no VLM needed) ──────────

class FastEventDetector:
    """Tracks person bounding boxes over a sliding window to detect falls
    via center-y velocity and aspect ratio change."""

    def __init__(self, window=8):
        self._history = []
        self._alert_cooldown = 0.0
        self._window = window

    def check(self, detections):
        now = time.time()
        if now - self._alert_cooldown < 6.0:
            return None

        persons = [d for d in detections if d.get("label", "").lower() == "person"]
        if persons:
            best = max(persons, key=lambda d: d.get("confidence", 0))
            bb = best.get("bbox", [0, 0, 0, 0])
            cy = (bb[1] + bb[3]) / 2.0
            h = bb[3] - bb[1]
            w = bb[2] - bb[0]
            ar = w / max(h, 1)
            self._history.append({"t": now, "cy": cy, "h": h, "ar": ar})
        else:
            self._history.append({"t": now, "cy": None, "h": 0, "ar": 0})

        self._history = [e for e in self._history if now - e["t"] < 3.0]
        self._history = self._history[-self._window:]

        valid = [e for e in self._history if e["cy"] is not None]
        if len(valid) < 3:
            return None

        first, last = valid[0], valid[-1]
        dt = last["t"] - first["t"]
        if dt < 0.3:
            return None

        dy = last["cy"] - first["cy"]
        velocity = dy / dt

        if velocity > 200 and last["ar"] > 1.2 and first["ar"] < 1.0:
            self._alert_cooldown = now
            return "Person down detected"

        if velocity > 300:
            self._alert_cooldown = now
            return "Rapid downward movement"

        was_present = any(e["cy"] is not None for e in self._history[:3])
        now_gone = all(e["cy"] is None for e in self._history[-3:])
        if was_present and now_gone:
            self._alert_cooldown = now
            return "Person left frame suddenly"

        return None


# ── TTS via macOS say ──────────────────────────────────────────────────────

_tts_queue = queue.Queue()
_tts_proc = None
_tts_proc_lock = threading.Lock()
_tts_speaking = False

def _tts_worker():
    global _tts_proc, _tts_speaking
    while True:
        text = _tts_queue.get()
        if text is None:
            break
        _tts_speaking = True
        try:
            with _tts_proc_lock:
                _tts_proc = subprocess.Popen(
                    ["say", "-r", "220", text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            _tts_proc.wait()
        except Exception:
            pass
        time.sleep(0.4)
        _tts_speaking = False

_tts_thread = threading.Thread(target=_tts_worker, daemon=True)
_tts_thread.start()

def speak(text):
    if not text or sys.platform != "darwin":
        return
    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
        except queue.Empty:
            break
    with _tts_proc_lock:
        if _tts_proc and _tts_proc.poll() is None:
            _tts_proc.kill()
    _tts_queue.put(text)


# ── CAT Equipment Color Detector ──────────────────────────────────────────

def detect_cat_colors(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    total = frame.shape[0] * frame.shape[1]
    yellow_mask = cv2.inRange(hsv, (18, 80, 140), (38, 255, 255))
    black_mask = cv2.inRange(hsv, (0, 0, 0), (180, 80, 50))
    yellow_pct = cv2.countNonZero(yellow_mask) / total
    black_pct = cv2.countNonZero(black_mask) / total
    return yellow_pct > 0.03 and black_pct > 0.02


# ── Frame Quality Gate ─────────────────────────────────────────────────────

def blur_score(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def motion_score(prev_gray, curr_gray):
    if prev_gray is None:
        return 999.0
    return cv2.absdiff(prev_gray, curr_gray).mean()


# ── Detection Smoother (IoU matching + EMA) ────────────────────────────────

class Track:
    __slots__ = ("label", "bbox", "confidence", "track_id", "age", "hits", "zone")

    def __init__(self, label, bbox, confidence, track_id):
        self.label = label
        self.bbox = np.array(bbox, dtype=np.float64)
        self.confidence = confidence
        self.track_id = track_id
        self.age = 0
        self.hits = 1
        self.zone = None


class DetectionSmoother:
    def __init__(self, alpha=SMOOTHING_ALPHA, max_age=TRACK_MAX_AGE):
        self.alpha = alpha
        self.max_age = max_age
        self.tracks = []
        self._next_id = 0

    @staticmethod
    def _iou(a, b):
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
        area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0

    def update(self, detections):
        if not detections:
            for t in self.tracks:
                t.age += 1
            self.tracks = [t for t in self.tracks if t.age < self.max_age]
            return list(self.tracks)

        used_tracks = set()
        used_dets = set()
        pairs = []
        for ti, track in enumerate(self.tracks):
            for di, det in enumerate(detections):
                iou = self._iou(track.bbox, det["bbox"])
                if iou > 0.15:
                    pairs.append((iou, ti, di))
        pairs.sort(key=lambda p: p[0], reverse=True)

        for iou_val, ti, di in pairs:
            if ti in used_tracks or di in used_dets:
                continue
            det = detections[di]
            track = self.tracks[ti]
            new_bbox = np.array(det["bbox"], dtype=np.float64)
            track.bbox = self.alpha * new_bbox + (1 - self.alpha) * track.bbox
            track.label = det.get("label", track.label)
            track.confidence = det.get("confidence", track.confidence)
            track.zone = det.get("zone", track.zone)
            track.age = 0
            track.hits += 1
            used_tracks.add(ti)
            used_dets.add(di)

        for ti, track in enumerate(self.tracks):
            if ti not in used_tracks:
                track.age += 1

        for di, det in enumerate(detections):
            if di not in used_dets:
                t = Track(det.get("label", "?"), det["bbox"], det.get("confidence", 0), self._next_id)
                t.zone = det.get("zone")
                self._next_id += 1
                self.tracks.append(t)

        self.tracks = [t for t in self.tracks if t.age < self.max_age]
        return list(self.tracks)


# ── Coverage Heatmap ───────────────────────────────────────────────────────

class CoverageHeatmap:
    def __init__(self, width=80, height=60, sigma=5.0):
        self.w = width
        self.h = height
        self.hmap = np.zeros((height, width), dtype=np.float64)
        gy, gx = np.ogrid[-height:height, -width:width]
        self._kernel = np.exp(-(gx * gx + gy * gy) / (2.0 * sigma * sigma))

    def accumulate(self, detections):
        for det in detections:
            bbox = det.get("bbox", det) if isinstance(det, dict) else det
            if hasattr(bbox, "bbox"):
                bbox = bbox.bbox
            if not hasattr(bbox, "__len__") or len(bbox) != 4:
                continue
            cx = int(((bbox[0] + bbox[2]) / 2.0) * self.w)
            cy = int(((bbox[1] + bbox[3]) / 2.0) * self.h)
            cx = max(0, min(cx, self.w - 1))
            cy = max(0, min(cy, self.h - 1))
            ky1 = self.h - cy
            ky2 = ky1 + self.h
            kx1 = self.w - cx
            kx2 = kx1 + self.w
            self.hmap += self._kernel[ky1:ky2, kx1:kx2]

    def coverage_pct(self):
        if self.hmap.max() == 0:
            return 0.0
        norm = self.hmap / self.hmap.max()
        return float(np.mean(norm > 0.1) * 100)

    def render(self, size=(140, 80)):
        if self.hmap.max() == 0:
            return np.zeros((size[1], size[0], 3), dtype=np.uint8)
        norm = (self.hmap / self.hmap.max() * 255).astype(np.uint8)
        colored = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
        return cv2.resize(colored, size, interpolation=cv2.INTER_NEAREST)


# ── Voice Capture with Silero VAD ──────────────────────────────────────────

class VoiceCapture:
    def __init__(self):
        self.running = False
        self.muted = False
        self._utterances = []
        self._lock = threading.Lock()
        self._vad_model = None
        self._buffer = []
        self._speech_active = False
        self._silence_frames = 0
        self._max_silence = 30

    def start(self):
        try:
            import sounddevice  # noqa: F401
            from silero_vad import load_silero_vad
            self._vad_model = load_silero_vad()
        except ImportError as e:
            print(f"  Audio disabled ({e}). Install sounddevice + silero-vad for voice.", file=sys.stderr)
            return
        except Exception as e:
            print(f"  VAD init failed: {e}", file=sys.stderr)
            return

        self.running = True
        t = threading.Thread(target=self._capture_loop, daemon=True)
        t.start()

    def _capture_loop(self):
        import sounddevice as sd
        import torch

        def callback(indata, frames, time_info, status):
            if self.muted or not self.running or _tts_speaking:
                return
            audio = indata[:, 0].copy()
            chunk = torch.from_numpy(audio).float()
            try:
                prob = self._vad_model(chunk, SAMPLE_RATE).item()
            except Exception:
                prob = 0.0

            if prob > VAD_THRESHOLD:
                self._speech_active = True
                self._silence_frames = 0
                self._buffer.append(audio)
            elif self._speech_active:
                self._silence_frames += 1
                self._buffer.append(audio)
                if self._silence_frames >= self._max_silence:
                    self._flush()

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=512,
                callback=callback,
            ):
                while self.running:
                    time.sleep(0.1)
        except Exception as e:
            print(f"  Audio stream error: {e}", file=sys.stderr)

    def _flush(self):
        if self._buffer:
            audio = np.concatenate(self._buffer)
            with self._lock:
                self._utterances.append(audio)
            self._buffer = []
        self._speech_active = False
        self._silence_frames = 0

    def get_utterance(self):
        with self._lock:
            if self._utterances:
                return self._utterances.pop(0)
        return None

    def stop(self):
        self.running = False
        if self._speech_active:
            self._flush()


# ── HUD Renderer ───────────────────────────────────────────────────────────

class HUD:
    def __init__(self, unit_info):
        self.unit = unit_info
        self.ws_connected = False
        self.ws_latency_ms = 0
        self.yolo_ms = 0
        self.send_fps = 0.0
        self.recv_fps = 0.0
        self.det_age_ms = 0
        self.dropped_frames = 0
        self.mic_active = False
        self.mic_muted = False
        self.transcript = ""
        self.findings = []
        self.brief_text = ""
        self.brief_zone = ""
        self.brief_time = 0
        self.spec_text = ""
        self.parts = []
        self.vlm_callout = ""
        self.vlm_callout_time = 0
        self.vlm_severity = "GREEN"
        self.vlm_description = ""
        self.vlm_findings = []
        self.mode = "general"

    @staticmethod
    def _dark_rect(frame, x, y, w, h, alpha=0.55):
        y2, x2 = min(y + h, frame.shape[0]), min(x + w, frame.shape[1])
        y, x = max(y, 0), max(x, 0)
        if y2 <= y or x2 <= x:
            return
        sub = frame[y:y2, x:x2]
        dark = (sub * (1.0 - alpha)).astype(np.uint8)
        frame[y:y2, x:x2] = dark

    def render(self, frame, tracks, zone_status, coverage_pct, completed_zones, confirmed_zones):
        h, w = frame.shape[:2]

        for t in tracks:
            bx = t.bbox
            x1, y1 = int(bx[0] * w), int(bx[1] * h)
            x2, y2 = int(bx[2] * w), int(bx[3] * h)
            zone = t.zone or ""
            rating = zone_status.get(zone, "GRAY") if zone else "GRAY"
            color = ZONE_COLORS.get(rating, (255, 255, 255))
            thickness = 2 if rating in ("GREEN", "GRAY") else 3
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
            conf_str = f"{t.confidence:.0%}" if t.confidence else ""
            txt = f"{t.label} {conf_str}" + (f" [{zone}]" if zone else "")
            cv2.putText(frame, txt, (x1, max(y1 - 6, 14)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)

        # Top bar
        self._dark_rect(frame, 0, 0, w, 34)
        info = f"DRONECAT [{self.mode.upper()}] | {self.unit['model']} {self.unit['serial']} {self.unit['hours']}h"
        cv2.putText(frame, info, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

        ws_color = (0, 200, 0) if self.ws_connected else (0, 0, 220)
        cv2.circle(frame, (w - 260, 18), 5, ws_color, -1)
        latency_txt = (
            f"WS {self.ws_latency_ms}ms | YOLO {self.yolo_ms}ms | "
            f"S/R {self.send_fps:.1f}/{self.recv_fps:.1f} | Age {self.det_age_ms}ms | Drop {self.dropped_frames}"
        )
        cv2.putText(frame, latency_txt, (w - 250, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, (200, 200, 200), 1, cv2.LINE_AA)

        mic_color = (0, 200, 0) if (self.mic_active and not self.mic_muted) else (100, 100, 100)
        mic_label = "MUTE" if self.mic_muted else ("MIC" if self.mic_active else "NO MIC")
        cv2.circle(frame, (w - 60, 18), 5, mic_color, -1)
        cv2.putText(frame, mic_label, (w - 50, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1, cv2.LINE_AA)

        # Right panel — zone checklist coverage
        pw = 175
        px = w - pw - 6
        py = 40
        ph = min(350, h - 140)
        self._dark_rect(frame, px, py, pw, ph)

        cv2.putText(frame, f"ZONE COVERAGE {coverage_pct:.0f}%", (px + 8, py + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(
            frame,
            f"{len(completed_zones)}/{len(ALL_ZONES)} completed",
            (px + 8, py + 34),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.34,
            (180, 180, 180),
            1,
            cv2.LINE_AA,
        )

        zy = py + 50
        for zone_name in ALL_ZONES:
            if zone_name in confirmed_zones:
                rating = zone_status.get(zone_name, "GREEN")
                color = ZONE_COLORS.get(rating, (100, 100, 100))
            elif zone_name in completed_zones:
                rating = "GREEN"
                color = (90, 180, 90)
            else:
                rating = "GRAY"
                color = (100, 100, 100)
            row_y = zy
            if row_y + 12 > py + ph:
                break
            cv2.rectangle(frame, (px + 8, row_y), (px + 18, row_y + 10), color, -1)
            short = zone_name.replace("_", " ")[:14]
            cv2.putText(frame, short, (px + 24, row_y + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, (190, 190, 190), 1, cv2.LINE_AA)
            zy += 16

        # VLM analysis panel (left side, below top bar)
        if (self.vlm_callout or self.vlm_description) and (time.time() - self.vlm_callout_time) < 12:
            vlm_pw = 280
            vlm_py = 40
            vlm_ph = 80
            self._dark_rect(frame, 6, vlm_py, vlm_pw, vlm_ph, alpha=0.65)

            sev_color = ZONE_COLORS.get(self.vlm_severity, (200, 200, 200))
            ai_label = self.vlm_callout or " ".join(self.vlm_description.split()[:5])
            cv2.putText(frame, f"AI: {ai_label}", (12, vlm_py + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, sev_color, 1, cv2.LINE_AA)

            if self.vlm_description:
                cv2.putText(frame, self.vlm_description[:55], (12, vlm_py + 38),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.34, (200, 200, 200), 1, cv2.LINE_AA)

            for i, finding_text in enumerate(self.vlm_findings[:2]):
                cv2.putText(frame, f"- {finding_text[:50]}", (12, vlm_py + 54 + i * 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.30, (180, 180, 180), 1, cv2.LINE_AA)

        # Bottom panel — voice + findings
        bot_h = 96
        bot_y = h - bot_h
        self._dark_rect(frame, 0, bot_y, w - pw - 12, bot_h)

        ly = bot_y + 16
        if self.transcript:
            cv2.putText(frame, f"VOICE: {self.transcript[:75]}", (8, ly),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1, cv2.LINE_AA)
            ly += 16

        for f in self.findings[-3:]:
            zone = f.get("zone", "?")
            rating = f.get("rating", "?")
            desc = f.get("description", "")[:55]
            color = ZONE_COLORS.get(rating, (200, 200, 200))
            cv2.putText(frame, f"[{zone}] {rating} {desc}", (8, ly),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, color, 1, cv2.LINE_AA)
            ly += 15

        if self.brief_text and (time.time() - self.brief_time) < 15:
            brief_disp = f"BRIEF [{self.brief_zone}]: {self.brief_text[:80]}"
            cv2.putText(frame, brief_disp, (8, ly),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, (100, 255, 255), 1, cv2.LINE_AA)

        cv2.putText(frame, "[g]General [c]CAT [r]Report [e]Evidence [p]PartID [m]Mute [q]Quit",
                    (8, h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (140, 140, 140), 1, cv2.LINE_AA)

        return frame


# ── Session Manager ────────────────────────────────────────────────────────

class Session:
    def __init__(self, unit_info):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.dir = Path("sessions") / ts
        self.evidence_dir = self.dir / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.unit_info = unit_info
        self.start_time = datetime.now()
        self._findings_fh = open(self.dir / "findings.jsonl", "a")
        self._evi_count = 0
        meta = {"unit": unit_info, "start_time": self.start_time.isoformat()}
        (self.dir / "session.json").write_text(json.dumps(meta, indent=2))

    def save_evidence(self, frame, label="manual"):
        self._evi_count += 1
        ts = datetime.now().strftime("%H%M%S")
        fname = f"{ts}_{self._evi_count:04d}_{label}.jpg"
        cv2.imwrite(str(self.evidence_dir / fname), frame)
        return fname

    def log_finding(self, finding):
        finding["timestamp"] = datetime.now().isoformat()
        self._findings_fh.write(json.dumps(finding) + "\n")
        self._findings_fh.flush()

    def save_report(self, report_data):
        text = json.dumps(report_data, indent=2) if isinstance(report_data, dict) else str(report_data)
        (self.dir / "report.json").write_text(text)

    def generate_pdf(self, findings, report_json, coverage_pct):
        try:
            from fpdf import FPDF
        except ImportError:
            print("  fpdf2 not installed, skipping PDF.")
            return None

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 12, "CAT 325 Daily Walk-Around Inspection", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        u = self.unit_info
        pdf.cell(0, 6, f"Unit: {u.get('model','')} | Serial: {u.get('serial','')} | {u.get('hours',0)}h", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Date: {self.start_time.strftime('%Y-%m-%d %H:%M')} | Coverage: {coverage_pct:.0f}%", new_x="LMARGIN", new_y="NEXT")
        dur = (datetime.now() - self.start_time).total_seconds() / 60
        pdf.cell(0, 6, f"Duration: {dur:.1f} min | Evidence: {self._evi_count} photos", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)

        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, "Zone Findings", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)

        sev_colors = {"RED": (200, 0, 0), "YELLOW": (180, 140, 0), "GREEN": (0, 130, 0)}
        for f in findings:
            zone = f.get("zone", "unknown")
            rating = f.get("rating", "GREEN")
            desc = f.get("description", "")
            r, g, b = sev_colors.get(rating, (0, 0, 0))
            pdf.set_text_color(r, g, b)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(30, 6, f"[{rating}]")
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 6, f"{zone}: {desc[:120]}")
            pdf.ln(1)

        evi_files = sorted(self.evidence_dir.glob("*.jpg"))
        if evi_files:
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 13)
            pdf.cell(0, 8, "Evidence Photos", new_x="LMARGIN", new_y="NEXT")
            for img_path in evi_files[:12]:
                try:
                    if pdf.get_y() > 230:
                        pdf.add_page()
                    pdf.set_font("Helvetica", "", 8)
                    pdf.cell(0, 4, img_path.name, new_x="LMARGIN", new_y="NEXT")
                    pdf.image(str(img_path), w=80)
                    pdf.ln(3)
                except Exception:
                    pass

        if report_json:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 13)
            pdf.cell(0, 8, "AI Executive Summary", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 10)
            summary = ""
            if isinstance(report_json, dict):
                summary = report_json.get("ai_executive_summary", json.dumps(report_json, indent=2))
            else:
                summary = str(report_json)
            pdf.multi_cell(0, 5, summary[:2000])

        pdf_path = self.dir / "report.pdf"
        pdf.output(str(pdf_path))
        return str(pdf_path)

    def close(self, coverage_pct):
        meta = json.loads((self.dir / "session.json").read_text())
        meta["end_time"] = datetime.now().isoformat()
        meta["duration_s"] = (datetime.now() - self.start_time).total_seconds()
        meta["coverage_pct"] = round(coverage_pct, 1)
        meta["evidence_count"] = self._evi_count
        (self.dir / "session.json").write_text(json.dumps(meta, indent=2))
        self._findings_fh.close()


# ── Shared state ───────────────────────────────────────────────────────────

shared_lock = threading.Lock()

shared = {
    "frame_packet": None,
    "last_frame_b64": None,
    "audio_b64": None,
    "detections": [],
    "last_detection_ts": 0.0,
    "last_detection_frame_id": -1,
    "zone_status": {},
    "new_findings": [],
    "all_findings": [],
    "transcript": "",
    "brief_text": "",
    "brief_zone": "",
    "brief_time": 0,
    "spec_text": "",
    "parts": [],
    "report": None,
    "auto_evidence": False,
    "ws_connected": False,
    "ws_latency_ms": 0,
    "yolo_ms": 0,
    "send_fps": 0.0,
    "recv_fps": 0.0,
    "dropped_frames": 0,
    "coverage": 0,
    "total_zones": 15,
    "detected_zones": set(),
    "confirmed_zones": set(),
    "pending_actions": [],
    "vlm_callout": "",
    "vlm_callout_time": 0,
    "vlm_severity": "GREEN",
    "vlm_description": "",
    "vlm_findings": [],
    "last_analysis_ts": 0.0,
    "last_analysis_frame_id": -1,
    "inspection_mode": "general",
}


# ── WebSocket loop ─────────────────────────────────────────────────────────

async def ws_loop(url, unit_info, spec_kb):
    import websockets

    async with websockets.connect(
        url,
        ping_interval=30,
        ping_timeout=60,
        close_timeout=10,
        max_size=10 * 1024 * 1024,
    ) as ws:
        shared["ws_connected"] = True
        print("  WebSocket connected.\n")
        send_count = 0
        recv_count = 0
        last_metrics_ts = time.time()
        frame_send_ts = {}
        last_sent_frame_id = -1
        last_callout_key = ""
        last_callout_spoken_ts = 0.0
        fast_events = FastEventDetector()

        async def sender_loop():
            nonlocal send_count, recv_count, last_metrics_ts, last_sent_frame_id
            while True:
                packet = shared.get("frame_packet")
                if packet and packet["frame_id"] > last_sent_frame_id:
                    fid = packet["frame_id"]
                    frame_send_ts[fid] = time.time()
                    await ws.send(json.dumps({
                        "type": "frame",
                        "data": packet["data"],
                        "frame_id": fid,
                        "client_ts": packet["client_ts"],
                        "mode": shared.get("inspection_mode", "general"),
                    }))
                    last_sent_frame_id = fid
                    send_count += 1

                audio = shared.get("audio_b64")
                if audio:
                    await ws.send(json.dumps({"type": "audio", "data": audio}))
                    shared["audio_b64"] = None

                with shared_lock:
                    actions = shared["pending_actions"][:]
                    shared["pending_actions"] = []
                for _, payload in actions:
                    await ws.send(json.dumps(payload))

                now = time.time()
                if now - last_metrics_ts >= 1.0:
                    shared["send_fps"] = send_count / (now - last_metrics_ts)
                    shared["recv_fps"] = recv_count / (now - last_metrics_ts)
                    send_count = 0
                    recv_count = 0
                    last_metrics_ts = now

                await asyncio.sleep(0.01)

        async def receiver_loop():
            nonlocal recv_count, last_callout_key, last_callout_spoken_ts
            while True:
                raw = await ws.recv()
                recv_count += 1
                msg = json.loads(raw)
                t = msg.get("type")

                if t == "detection":
                    frame_id = int(msg.get("frame_id", -1))
                    if frame_id < shared.get("last_detection_frame_id", -1):
                        shared["dropped_frames"] = shared.get("dropped_frames", 0) + 1
                        continue

                    shared["last_detection_frame_id"] = frame_id
                    shared["last_detection_ts"] = time.time()
                    shared["detections"] = msg.get("detections", [])
                    shared["coverage"] = msg.get("coverage", 0)
                    shared["total_zones"] = msg.get("total_zones", 15)
                    shared["yolo_ms"] = msg.get("yolo_ms", 0)
                    if msg.get("mode") in ("general", "cat"):
                        shared["inspection_mode"] = msg.get("mode")
                    det_zones = {d.get("zone") for d in shared["detections"] if d.get("zone")}
                    if det_zones:
                        shared["detected_zones"].update(det_zones)

                    if frame_id in frame_send_ts:
                        shared["ws_latency_ms"] = int((time.time() - frame_send_ts.pop(frame_id)) * 1000)

                    dets = shared["detections"]

                    fast_alert = fast_events.check(dets)
                    if fast_alert:
                        print(f"  !! FAST ALERT: {fast_alert}")
                        speak(fast_alert)
                        shared["auto_evidence"] = True
                        with shared_lock:
                            shared["pending_actions"].append(("vlm", {
                                "type": "request_vlm_analysis",
                            }))

                    relevant = [d for d in dets if d.get("label", "").lower() not in _IGNORE_LABELS]
                    if relevant:
                        labels = [f"{d['label']}({d.get('confidence',0):.0%})" for d in relevant[:5]]
                        zones = [d.get("zone") for d in relevant if d.get("zone")]
                        print(f"  det: {len(relevant)} obj | {labels} | zones: {zones}")

                elif t == "analysis":
                    frame_id = int(msg.get("frame_id", -1))
                    if frame_id < shared.get("last_analysis_frame_id", -1):
                        continue
                    shared["last_analysis_frame_id"] = frame_id
                    shared["last_analysis_ts"] = time.time()
                    if msg.get("mode") in ("general", "cat"):
                        shared["inspection_mode"] = msg.get("mode")

                    data = msg.get("data", {})
                    callout = data.get("callout", "")
                    severity = data.get("severity", "GREEN")
                    description = data.get("description", "")
                    findings_list = data.get("findings", [])
                    zone = data.get("zone")

                    shared["vlm_callout"] = callout
                    shared["vlm_callout_time"] = time.time()
                    shared["vlm_severity"] = severity
                    shared["vlm_description"] = description
                    shared["vlm_findings"] = findings_list

                    if zone and zone in ALL_ZONES:
                        shared["detected_zones"].add(zone)
                        if severity in ("YELLOW", "RED"):
                            shared["zone_status"][zone] = severity
                        elif zone not in shared["zone_status"]:
                            shared["zone_status"][zone] = severity

                    print(f"  VLM [{severity}]: {callout or description[:60]}")
                    now = time.time()
                    spoken_text = callout if callout else " ".join(description.split()[:6])
                    callout_key = f"{severity}|{spoken_text}".strip()
                    should_speak = False
                    if severity in ("YELLOW", "RED"):
                        should_speak = (callout_key != last_callout_key) or (now - last_callout_spoken_ts > CALLOUT_COOLDOWN_S)
                    elif callout_key != last_callout_key and last_callout_key:
                        prev_sev = last_callout_key.split("|")[0] if last_callout_key else ""
                        prev_desc = last_callout_key.split("|", 1)[1] if "|" in last_callout_key else ""
                        desc_words = set(spoken_text.lower().split())
                        prev_words = set(prev_desc.lower().split())
                        overlap = len(desc_words & prev_words) / max(len(desc_words | prev_words), 1)
                        should_speak = overlap < 0.5
                    if should_speak and spoken_text:
                        last_callout_key = callout_key
                        last_callout_spoken_ts = now
                        speak(spoken_text)

                elif t == "zone_first_seen":
                    zone_id = msg.get("zone")
                    print(f"  ** zone_first_seen: {zone_id} **")

                elif t == "transcript":
                    text = msg.get("text", "")
                    shared["transcript"] = text
                    print(f"  transcript: {text}")

                elif t == "finding":
                    finding = msg.get("data", {})
                    zone = finding.get("zone", "?")
                    rating = finding.get("rating", "GREEN")
                    if zone in ALL_ZONES:
                        shared["confirmed_zones"].add(zone)
                    shared["zone_status"][zone] = rating
                    with shared_lock:
                        shared["new_findings"].append(finding)
                        shared["all_findings"].append(finding)
                    print(f"  finding: [{zone}] {rating} {finding.get('description', '')[:60]}")
                    zone_spoken = zone.replace("_", " ")
                    if rating == "RED":
                        speak(f"Red flag on {zone_spoken}. Logged.")
                    elif rating == "YELLOW":
                        speak(f"Yellow on {zone_spoken}. Logged.")
                    else:
                        speak(f"{zone_spoken} logged green.")

                    if rating in ("YELLOW", "RED"):
                        zone_spec = spec_kb.get(zone, {})
                        with shared_lock:
                            shared["pending_actions"].append(("spec", {
                                "type": "request_spec_assessment",
                                "zone": zone,
                                "rating": rating,
                                "description": finding.get("description", ""),
                                "spec_knowledge": zone_spec.get("spec_text", ""),
                                "frame": shared.get("last_frame_b64", ""),
                            }))
                        shared["auto_evidence"] = True

                    if rating == "RED":
                        speak(f"Red alert. {zone.replace('_', ' ')}")

                elif t == "zone_brief":
                    shared["brief_text"] = msg.get("text", "")
                    shared["brief_zone"] = msg.get("zone", "")
                    shared["brief_time"] = time.time()
                    print(f"  brief [{msg.get('zone')}]: {msg.get('text', '')[:80]}")

                elif t == "spec_assessment":
                    shared["spec_text"] = msg.get("result", "")
                    print(f"  spec [{msg.get('zone')}]: {msg.get('result', '')[:80]}")

                elif t == "parts_result":
                    shared["parts"] = msg.get("parts", [])
                    for p in shared["parts"][:3]:
                        print(f"  part: {p.get('part_number', '?')} — {p.get('description', '')[:40]} ({p.get('certainty_pct', 0)}%)")

                elif t == "voice_answer":
                    answer = msg.get("text", "")
                    shared["voice_answer"] = answer
                    shared["voice_answer_time"] = time.time()
                    print(f"  ANSWER: {answer}")
                    first_sent = answer.split(".")[0].strip()
                    if first_sent:
                        speak(first_sent + ".")
                    else:
                        speak(answer[:80])

                elif t == "mode":
                    mode = msg.get("mode", "general")
                    shared["inspection_mode"] = mode
                    print(f"  mode: {mode}")

                elif t == "report":
                    shared["report"] = msg.get("data", "")
                    shared["report_ready"] = True
                    print(f"  REPORT GENERATED ({len(str(shared['report']))} chars)")

                else:
                    print(f"  {t}: {str(msg)[:100]}")

        await asyncio.gather(sender_loop(), receiver_loop())


def start_ws_thread(url, unit_info, spec_kb):
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        backoff = 2
        while True:
            try:
                shared["ws_connected"] = False
                loop.run_until_complete(ws_loop(url, unit_info, spec_kb))
            except Exception as e:
                shared["ws_connected"] = False
                print(f"  WebSocket error: {e} — reconnecting in {backoff}s...")
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
            else:
                backoff = 2

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# ── Intent Router ─────────────────────────────────────────────────────────

_Q_WORDS = {"what", "how", "why", "where", "is", "does", "can", "tell", "describe", "show", "explain", "do", "are", "which"}

_COMMANDS = {
    "generate report": "report",
    "create report": "report",
    "make report": "report",
    "save evidence": "evidence",
    "capture evidence": "evidence",
    "take photo": "evidence",
    "unmute": "unmute",
    "mute": "mute",
    "stop": "stop",
    "cat mode": "mode_cat",
    "switch to cat": "mode_cat",
    "general mode": "mode_general",
    "switch to general": "mode_general",
}

def _classify_intent(text):
    t = text.strip().lower()
    for trigger, cmd in _COMMANDS.items():
        if trigger in t:
            return "command", cmd
    if "?" in t:
        return "question", None
    words = t.split()
    if words and words[0] in _Q_WORDS:
        return "question", None
    return "finding", None

def _local_transcribe(whisper_model, audio_array, shared, spec_kb):
    try:
        segments, _ = whisper_model.transcribe(audio_array, beam_size=1, language="en")
        transcript = " ".join(s.text.strip() for s in segments).strip()
    except Exception as e:
        print(f"  local whisper error: {e}")
        return
    if not transcript or len(transcript) < 3:
        return
    shared["transcript"] = transcript
    print(f"  voice: {transcript}")

    intent, cmd = _classify_intent(transcript)

    if intent == "command":
        if cmd == "report":
            shared["request_report"] = True
            speak("Generating report.")
        elif cmd == "evidence":
            shared["auto_evidence"] = True
            speak("Evidence saved.")
        elif cmd == "mute":
            shared["voice_mute_request"] = True
        elif cmd == "unmute":
            shared["voice_unmute_request"] = True
        elif cmd == "stop":
            shared["quit_requested"] = True
        elif cmd == "mode_cat":
            shared["inspection_mode"] = "cat"
            with shared_lock:
                shared["pending_actions"].append(("set_mode", {"type": "set_mode", "mode": "cat"}))
            speak("CAT mode enabled.")
        elif cmd == "mode_general":
            shared["inspection_mode"] = "general"
            with shared_lock:
                shared["pending_actions"].append(("set_mode", {"type": "set_mode", "mode": "general"}))
            speak("General mode enabled.")
        return

    if intent == "question":
        frame_b64 = shared.get("last_frame_b64")
        if frame_b64:
            with shared_lock:
                shared["pending_actions"].append(("voice_question", {
                    "type": "voice_question",
                    "text": transcript,
                    "frame": frame_b64,
                }))
        else:
            speak("No frame available yet.")
        return

    if shared.get("inspection_mode", "general") != "cat":
        frame_b64 = shared.get("last_frame_b64")
        if frame_b64:
            with shared_lock:
                shared["pending_actions"].append(("voice_question", {
                    "type": "voice_question",
                    "text": transcript,
                    "frame": frame_b64,
                }))
        return

    from backend.nlp import extract_finding
    finding = extract_finding(transcript)
    if finding["zone"]:
        zone = finding["zone"]
        rating = finding["rating"]
        with shared_lock:
            shared["new_findings"].append(finding)
            shared["all_findings"].append(finding)
        if zone in ALL_ZONES:
            shared["confirmed_zones"].add(zone)
        shared["zone_status"][zone] = rating
        print(f"  finding: [{zone}] {rating} {finding.get('description', '')[:60]}")
        zone_spoken = zone.replace("_", " ")
        if rating == "RED":
            speak(f"Alert. {zone_spoken} has a problem.")
        elif rating == "YELLOW":
            speak(f"Watch out, {zone_spoken} needs attention.")
        else:
            speak(f"Noted, {zone_spoken} looks good.")
    else:
        frame_b64 = shared.get("last_frame_b64")
        if frame_b64:
            with shared_lock:
                shared["pending_actions"].append(("voice_question", {
                    "type": "voice_question",
                    "text": transcript,
                    "frame": frame_b64,
                }))


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Dronecat inspection client")
    parser.add_argument("--url", default=os.environ.get("MODAL_WS_URL"))
    parser.add_argument("--model", default="CAT 325")
    parser.add_argument("--serial", default="CAT0325F4K01847")
    parser.add_argument("--hours", type=int, default=2847)
    parser.add_argument("--technician", default="Inspector")
    parser.add_argument("--camera", type=int, default=CAMERA_DEVICE)
    parser.add_argument("--mode", choices=["general", "cat"], default="general")
    parser.add_argument("--frame-interval", type=float, default=FRAME_INTERVAL)
    parser.add_argument("--force-send-ms", type=int, default=FORCE_SEND_MS)
    parser.add_argument("--motion-threshold", type=float, default=MOTION_THRESHOLD)
    parser.add_argument("--blur-threshold", type=float, default=BLUR_THRESHOLD)
    args = parser.parse_args()

    url = args.url
    if not url:
        print("Set MODAL_WS_URL env var or pass --url wss://...", file=sys.stderr)
        sys.exit(1)
    if not url.startswith("ws"):
        url = "wss://" + url.replace("https://", "").rstrip("/")
    if "/ws" not in url:
        url = url.rstrip("/") + "/ws"

    unit_info = {
        "model": args.model,
        "serial": args.serial,
        "hours": args.hours,
        "technician": args.technician,
    }

    spec_kb = {}
    kb_path = Path(__file__).resolve().parent.parent / "data" / "cat_spec_kb.json"
    if kb_path.exists():
        spec_kb = json.loads(kb_path.read_text())

    session = Session(unit_info)
    smoother = DetectionSmoother()
    hud = HUD(unit_info)
    voice = VoiceCapture()
    shared["inspection_mode"] = args.mode

    local_whisper = None
    try:
        from faster_whisper import WhisperModel
        print("  Loading local Whisper (base.en) for fast transcription...")
        local_whisper = WhisperModel("base.en", device="cpu", compute_type="int8")
        print("  Local Whisper ready.")
    except ImportError:
        print("  faster-whisper not installed, using Modal Whisper (slower).")

    start_ws_thread(url, unit_info, spec_kb)
    voice.start()
    hud.mic_active = voice.running

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"Cannot open camera device {args.camera}", file=sys.stderr)
        sys.exit(1)

    print(f"Camera {args.camera} open. Connecting to {url}")
    print(f"Unit: {unit_info['model']} | {unit_info['serial']} | {unit_info['hours']}h")
    print(f"Mode: {shared['inspection_mode'].upper()}")
    print(f"Session: {session.dir}")
    print("Keys: [g]General [c]CAT [r]Report [e]Evidence [p]PartID [m]Mute [q]Quit")
    print("Voice: press M to unmute, then speak. Ask questions, log findings, or say 'generate report'.\n")
    with shared_lock:
        shared["pending_actions"].append(("set_mode", {"type": "set_mode", "mode": shared["inspection_mode"]}))

    prev_gray = None
    last_send = 0
    frame_id = 0
    cat_color_counter = 0
    cat_was_visible = False

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            now = time.time()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            should_send = False
            force_send = (now - last_send) * 1000 >= args.force_send_ms
            if now - last_send >= args.frame_interval:
                bs = blur_score(frame)
                ms = motion_score(prev_gray, gray)
                if bs >= args.blur_threshold and ms >= args.motion_threshold:
                    should_send = True
                elif prev_gray is None:
                    should_send = True
            if force_send:
                should_send = True

            if should_send:
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
                frame_id += 1
                shared["frame_packet"] = {
                    "data": b64,
                    "frame_id": frame_id,
                    "client_ts": time.time(),
                }
                shared["last_frame_b64"] = b64
                last_send = now

            prev_gray = gray

            cat_color_counter += 1
            if cat_color_counter % 10 == 0:
                cat_now = detect_cat_colors(frame)
                shared["cat_visible"] = cat_now
                if cat_now and not cat_was_visible:
                    print("  ** CAT equipment detected (yellow+black) **")
                    speak("CAT equipment in view.")
                cat_was_visible = cat_now

            utterance = voice.get_utterance()
            if utterance is not None:
                if local_whisper:
                    threading.Thread(
                        target=_local_transcribe,
                        args=(local_whisper, utterance, shared, spec_kb),
                        daemon=True,
                    ).start()
                else:
                    shared["audio_b64"] = base64.b64encode(utterance.tobytes()).decode("utf-8")

            det_age_s = now - shared.get("last_detection_ts", 0.0)
            live_detections = [
                d for d in shared.get("detections", [])
                if d.get("label", "").lower() not in _IGNORE_LABELS
            ]
            if det_age_s > DETECTION_TTL_S:
                live_detections = []
            tracks = smoother.update(live_detections)

            analysis_age_s = now - shared.get("last_analysis_ts", 0.0)
            if analysis_age_s > ANALYSIS_TTL_S:
                shared["vlm_callout"] = ""
                shared["vlm_description"] = ""
                shared["vlm_findings"] = []

            if shared.get("auto_evidence"):
                fname = session.save_evidence(frame, "auto")
                print(f"  [evidence: {fname}]")
                shared["auto_evidence"] = False

            with shared_lock:
                new = shared["new_findings"][:]
                shared["new_findings"] = []
            for f in new:
                session.log_finding(f)

            hud.ws_connected = shared.get("ws_connected", False)
            hud.ws_latency_ms = shared.get("ws_latency_ms", 0)
            hud.yolo_ms = shared.get("yolo_ms", 0)
            hud.send_fps = shared.get("send_fps", 0.0)
            hud.recv_fps = shared.get("recv_fps", 0.0)
            hud.det_age_ms = int(det_age_s * 1000)
            hud.dropped_frames = shared.get("dropped_frames", 0)
            hud.mic_active = voice.running
            hud.mic_muted = voice.muted
            hud.transcript = shared.get("transcript", "")
            hud.findings = shared.get("all_findings", [])
            hud.brief_text = shared.get("brief_text", "")
            hud.brief_zone = shared.get("brief_zone", "")
            hud.brief_time = shared.get("brief_time", 0)
            hud.vlm_callout = shared.get("vlm_callout", "")
            hud.vlm_callout_time = shared.get("vlm_callout_time", 0)
            hud.vlm_severity = shared.get("vlm_severity", "GREEN")
            hud.vlm_description = shared.get("vlm_description", "")
            hud.vlm_findings = shared.get("vlm_findings", [])
            hud.mode = shared.get("inspection_mode", "general")

            zone_status = shared.get("zone_status", {})
            completed_zones = set(shared.get("detected_zones", set())).union(
                set(shared.get("confirmed_zones", set()))
            )
            confirmed_zones = set(shared.get("confirmed_zones", set()))
            coverage_pct = (len(completed_zones) / len(ALL_ZONES)) * 100.0

            display = hud.render(
                frame.copy(),
                tracks,
                zone_status,
                coverage_pct,
                completed_zones,
                confirmed_zones,
            )
            cv2.imshow("Dronecat", display)

            if shared.get("voice_mute_request"):
                shared["voice_mute_request"] = False
                voice.muted = True
                speak("Mic muted.")
            if shared.get("voice_unmute_request"):
                shared["voice_unmute_request"] = False
                voice.muted = False
                speak("Mic on.")
            if shared.get("quit_requested"):
                break

            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("g"):
                shared["inspection_mode"] = "general"
                with shared_lock:
                    shared["pending_actions"].append(("set_mode", {"type": "set_mode", "mode": "general"}))
                speak("General mode.")
            elif key == ord("c"):
                shared["inspection_mode"] = "cat"
                with shared_lock:
                    shared["pending_actions"].append(("set_mode", {"type": "set_mode", "mode": "cat"}))
                speak("CAT mode.")
            elif key == ord("e"):
                fname = session.save_evidence(frame, "manual")
                print(f"  [evidence: {fname}]")
            elif key == ord("m"):
                voice.muted = not voice.muted
                print(f"  mic {'muted' if voice.muted else 'unmuted'}")
            elif key == ord("p"):
                fb = shared.get("last_frame_b64")
                if fb:
                    with shared_lock:
                        shared["pending_actions"].append(("part_id", {
                            "type": "identify_part",
                            "data": fb,
                        }))
                    print("  [requesting part ID...]")
            elif key == ord("r"):
                elapsed = (datetime.now() - session.start_time).total_seconds() / 60
                with shared_lock:
                    shared["pending_actions"].append(("report", {
                        "type": "generate_report",
                        "model": unit_info["model"],
                        "serial": unit_info["serial"],
                        "hours": unit_info["hours"],
                        "technician": unit_info["technician"],
                        "duration_minutes": int(elapsed),
                        "coverage_percent": int(coverage_pct),
                    }))
                print("  [requesting report...]")

            if shared.get("request_report"):
                shared["request_report"] = False
                elapsed = (datetime.now() - session.start_time).total_seconds() / 60
                with shared_lock:
                    shared["pending_actions"].append(("report", {
                        "type": "generate_report",
                        "model": unit_info["model"],
                        "serial": unit_info["serial"],
                        "hours": unit_info["hours"],
                        "technician": unit_info["technician"],
                        "duration_minutes": int(elapsed),
                        "coverage_percent": int(coverage_pct),
                    }))
                speak("Generating report.")

            if shared.get("report_ready"):
                shared["report_ready"] = False
                report_data = shared.get("report", "")
                session.save_report(report_data)
                pdf_path = session.generate_pdf(
                    shared.get("all_findings", []),
                    report_data,
                    coverage_pct,
                )
                if pdf_path:
                    print(f"  [PDF report saved: {pdf_path}]")
                    speak("Report saved to session folder.")
                else:
                    print(f"  [report saved to {session.dir / 'report.json'}]")
                    speak("Report generated.")

    except KeyboardInterrupt:
        pass
    finally:
        voice.stop()
        completed_zones = set(shared.get("detected_zones", set())).union(
            set(shared.get("confirmed_zones", set()))
        )
        session.close((len(completed_zones) / len(ALL_ZONES)) * 100.0)
        cap.release()
        cv2.destroyAllWindows()
        print(f"\nSession saved to {session.dir}")


if __name__ == "__main__":
    main()
