"""
OpenCV HUD overlay: detection boxes with triage coloring, zone coverage panel,
VLM callout panel, and bottom status bar.
"""

import time

import cv2
import numpy as np

from .constants import ALL_ZONES, HIGH_ANOMALY_THRESHOLD, ZONE_COLORS
from .detection import iou


class HUD:
    """
    Renders the full inspection overlay onto a frame and returns it.

    State fields are set by the main loop each tick before calling render().
    All drawing is split into named private methods so each visual region
    can be understood and modified independently.
    """

    def __init__(self, unit_info):
        self.unit            = unit_info
        self.ws_connected    = False
        self.ws_latency_ms   = 0
        self.yolo_ms         = 0
        self.send_fps        = 0.0
        self.recv_fps        = 0.0
        self.det_age_ms      = 0
        self.dropped_frames  = 0
        self.mic_active      = False
        self.mic_muted       = False
        self.transcript      = ""
        self.findings        = []
        self.brief_text      = ""
        self.brief_zone      = ""
        self.brief_time      = 0
        self.spec_text       = ""
        self.parts           = []
        self.vlm_callout     = ""
        self.vlm_callout_time = 0
        self.vlm_severity    = "GREEN"
        self.vlm_description = ""
        self.vlm_findings    = []
        self.mode            = "general"
        # Tier 2 triage
        self.triage_boxes       = []   # [{bbox, is_flagged, anomaly_score}]
        self.anomaly_flash_boxes = []  # [{bbox, ts, score, label, top_anomaly}]
        self.t2_ms              = 0

    def render(self, frame, tracks, zone_status, coverage_pct, completed_zones, confirmed_zones):
        h, w = frame.shape[:2]
        self._draw_detection_boxes(frame, tracks, zone_status, w, h)
        self._draw_top_bar(frame, w)
        self._draw_zone_panel(frame, zone_status, coverage_pct, completed_zones, confirmed_zones, w, h)
        self._draw_vlm_panel(frame)
        self._draw_bottom_panel(frame, w, h)
        return frame

    # ── Detection boxes ──────────────────────────────────────────────────────

    def _draw_detection_boxes(self, frame, tracks, zone_status, w, h):
        now = time.time()
        for t in tracks:
            bx        = t.bbox
            x1, y1    = int(bx[0] * w), int(bx[1] * h)
            x2, y2    = int(bx[2] * w), int(bx[3] * h)
            bbox_list = bx.tolist() if hasattr(bx, "tolist") else list(bx)

            color, thickness = self._box_color(bbox_list, t, zone_status)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

            self._draw_anomaly_flash(frame, bbox_list, x1, y1, x2, y2, now)

            conf_str = f"{t.confidence:.0%}" if t.confidence else ""
            zone     = t.zone or ""
            label    = f"{t.label} {conf_str}" + (f" [{zone}]" if zone else "")
            cv2.putText(frame, label, (x1, max(y1 - 6, 14)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)

    def _box_color(self, bbox_list, track, zone_status):
        """Tier 2 triage result takes priority over zone_status coloring."""
        for tb in self.triage_boxes:
            if iou(bbox_list, tb.get("bbox", [])) > 0.25:
                if tb.get("is_flagged"):
                    color = (0, 0, 220) if tb.get("anomaly_score", 0) > HIGH_ANOMALY_THRESHOLD else (0, 200, 255)
                    return color, 3
                break
        zone      = track.zone or ""
        rating    = zone_status.get(zone, "GRAY") if zone else "GRAY"
        color     = ZONE_COLORS.get(rating, (255, 255, 255))
        thickness = 2 if rating in ("GREEN", "GRAY") else 3
        return color, thickness

    def _draw_anomaly_flash(self, frame, bbox_list, x1, y1, x2, y2, now):
        """Pulsing cyan border for detections flagged by Tier 2 in the last 3 seconds."""
        for fb in self.anomaly_flash_boxes:
            if iou(bbox_list, fb.get("bbox", [])) > 0.25:
                age = now - fb.get("ts", 0)
                if age < 3.0 and int(age * 4) % 2 == 0:
                    cv2.rectangle(frame, (x1 - 3, y1 - 3), (x2 + 3, y2 + 3), (0, 255, 255), 4)
                break

    # ── Top bar ──────────────────────────────────────────────────────────────

    def _draw_top_bar(self, frame, w):
        self._dark_rect(frame, 0, 0, w, 34)

        info = f"DRONECAT [{self.mode.upper()}] | {self.unit['model']} {self.unit['serial']} {self.unit['hours']}h"
        cv2.putText(frame, info, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

        ws_color = (0, 200, 0) if self.ws_connected else (0, 0, 220)
        cv2.circle(frame, (w - 260, 18), 5, ws_color, -1)
        latency = (
            f"WS {self.ws_latency_ms}ms | YOLO {self.yolo_ms}ms | T2 {self.t2_ms}ms | "
            f"S/R {self.send_fps:.1f}/{self.recv_fps:.1f} | Age {self.det_age_ms}ms | Drop {self.dropped_frames}"
        )
        cv2.putText(frame, latency, (w - 250, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (200, 200, 200), 1, cv2.LINE_AA)

        mic_color = (0, 200, 0) if (self.mic_active and not self.mic_muted) else (100, 100, 100)
        mic_label = "MUTE" if self.mic_muted else ("MIC" if self.mic_active else "NO MIC")
        cv2.circle(frame, (w - 60, 18), 5, mic_color, -1)
        cv2.putText(frame, mic_label, (w - 50, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1, cv2.LINE_AA)

    # ── Right zone-coverage panel ────────────────────────────────────────────

    def _draw_zone_panel(self, frame, zone_status, coverage_pct, completed_zones, confirmed_zones, w, h):
        pw, px, py = 175, w - 175 - 6, 40
        ph = min(350, h - 140)
        self._dark_rect(frame, px, py, pw, ph)

        cv2.putText(frame, f"ZONE COVERAGE {coverage_pct:.0f}%", (px + 8, py + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, f"{len(completed_zones)}/{len(ALL_ZONES)} completed",
                    (px + 8, py + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (180, 180, 180), 1, cv2.LINE_AA)

        zy = py + 50
        for zone_name in ALL_ZONES:
            if zy + 12 > py + ph:
                break
            if zone_name in confirmed_zones:
                color = ZONE_COLORS.get(zone_status.get(zone_name, "GREEN"), (100, 100, 100))
            elif zone_name in completed_zones:
                color = (90, 180, 90)
            else:
                color = (100, 100, 100)
            cv2.rectangle(frame, (px + 8, zy), (px + 18, zy + 10), color, -1)
            cv2.putText(frame, zone_name.replace("_", " ")[:14], (px + 24, zy + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, (190, 190, 190), 1, cv2.LINE_AA)
            zy += 16

    # ── Left VLM callout panel ───────────────────────────────────────────────

    def _draw_vlm_panel(self, frame):
        if not (self.vlm_callout or self.vlm_description):
            return
        if time.time() - self.vlm_callout_time >= 12:
            return
        self._dark_rect(frame, 6, 40, 280, 80, alpha=0.65)
        sev_color = ZONE_COLORS.get(self.vlm_severity, (200, 200, 200))
        ai_label  = self.vlm_callout or " ".join(self.vlm_description.split()[:5])
        cv2.putText(frame, f"AI: {ai_label}", (12, 58),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, sev_color, 1, cv2.LINE_AA)
        if self.vlm_description:
            cv2.putText(frame, self.vlm_description[:55], (12, 78),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.34, (200, 200, 200), 1, cv2.LINE_AA)
        for i, finding in enumerate(self.vlm_findings[:2]):
            cv2.putText(frame, f"- {finding[:50]}", (12, 94 + i * 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.30, (180, 180, 180), 1, cv2.LINE_AA)

    # ── Bottom status bar ────────────────────────────────────────────────────

    def _draw_bottom_panel(self, frame, w, h):
        pw    = 175
        bot_y = h - 96
        self._dark_rect(frame, 0, bot_y, w - pw - 12, 96)

        ly = bot_y + 16
        if self.transcript:
            cv2.putText(frame, f"VOICE: {self.transcript[:75]}", (8, ly),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1, cv2.LINE_AA)
            ly += 16

        for f in self.findings[-3:]:
            color = ZONE_COLORS.get(f.get("rating", "?"), (200, 200, 200))
            text  = f"[{f.get('zone','?')}] {f.get('rating','?')} {f.get('description','')[:55]}"
            cv2.putText(frame, text, (8, ly), cv2.FONT_HERSHEY_SIMPLEX, 0.36, color, 1, cv2.LINE_AA)
            ly += 15

        if self.brief_text and (time.time() - self.brief_time) < 15:
            cv2.putText(frame, f"BRIEF [{self.brief_zone}]: {self.brief_text[:80]}", (8, ly),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, (100, 255, 255), 1, cv2.LINE_AA)

        cv2.putText(frame, "[g]General [c]CAT [r]Report [e]Evidence [p]PartID [m]Mute [q]Quit",
                    (8, h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (140, 140, 140), 1, cv2.LINE_AA)

    # ── Utility ──────────────────────────────────────────────────────────────

    @staticmethod
    def _dark_rect(frame, x, y, w, h, alpha=0.55):
        y2, x2 = min(y + h, frame.shape[0]), min(x + w, frame.shape[1])
        y,  x  = max(y, 0), max(x, 0)
        if y2 > y and x2 > x:
            frame[y:y2, x:x2] = (frame[y:y2, x:x2] * (1.0 - alpha)).astype(np.uint8)
