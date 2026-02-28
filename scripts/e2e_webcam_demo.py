#!/usr/bin/env python3
"""
Dronecat inspection client — YOLO + async VLM + voice I/O.

  export MODAL_WS_URL=wss://...
  python3 scripts/e2e_webcam_demo.py
  python3 scripts/e2e_webcam_demo.py --url wss://... --serial CAT0325F4K01847

Keys: [g] General  [c] CAT  [r] Report  [e] Evidence  [Space] PTT  [q] Quit
"""

import argparse
import base64
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from client.audio    import VoiceCapture, handle_utterance, speak
from client.constants import (
    ALL_ZONES, ANALYSIS_TTL_S, BLUR_THRESHOLD, CAMERA_DEVICE,
    DETECTION_TTL_S, FRAME_INTERVAL, FORCE_SEND_MS, _IGNORE_LABELS,
    JPEG_QUALITY, LABEL_UNSEEN_TIMEOUT_S, MOTION_THRESHOLD,
)
from client.detection import DetectionSmoother, blur_score, detect_cat_colors, motion_score
from client.hud       import HUD
from client.session   import Session
from client.ws_client import shared, shared_lock, start_ws_thread

# Debounce state for Space PTT toggle (prevents key-repeat re-toggling on macOS)
_last_space_ts  = 0.0
_PTT_DEBOUNCE_S = 0.5


# ── Startup helpers ──────────────────────────────────────────────────────────

def _parse_args():
    parser = argparse.ArgumentParser(description="Dronecat inspection client")
    parser.add_argument("--url",              default=os.environ.get("MODAL_WS_URL"))
    parser.add_argument("--model",            default="CAT 325")
    parser.add_argument("--serial",           default="CAT0325F4K01847")
    parser.add_argument("--hours",            type=int,   default=2847)
    parser.add_argument("--technician",       default="Inspector")
    parser.add_argument("--camera",           type=int,   default=CAMERA_DEVICE)
    parser.add_argument("--mode",             choices=["general", "cat"], default="general")
    parser.add_argument("--frame-interval",   type=float, default=FRAME_INTERVAL)
    parser.add_argument("--force-send-ms",    type=int,   default=FORCE_SEND_MS)
    parser.add_argument("--motion-threshold", type=float, default=MOTION_THRESHOLD)
    parser.add_argument("--blur-threshold",   type=float, default=BLUR_THRESHOLD)
    return parser.parse_args()


def _resolve_ws_url(raw_url):
    if not raw_url:
        print("Set MODAL_WS_URL env var or pass --url wss://...", file=sys.stderr)
        sys.exit(1)
    url = raw_url if raw_url.startswith("ws") else "wss://" + raw_url.replace("https://", "").rstrip("/")
    return url if "/ws" in url else url.rstrip("/") + "/ws"


def _load_spec_kb():
    kb_path = Path(__file__).resolve().parent.parent / "data" / "cat_spec_kb.json"
    return json.loads(kb_path.read_text()) if kb_path.exists() else {}


def _load_local_whisper():
    try:
        from faster_whisper import WhisperModel
        print("  Loading local Whisper (base.en)...")
        model = WhisperModel("base.en", device="cpu", compute_type="int8")
        print("  Local Whisper ready.")
        return model
    except ImportError:
        print("  faster-whisper not installed — voice transcription disabled.")
        return None


def _open_camera(camera_id):
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        print(f"Cannot open camera device {camera_id}", file=sys.stderr)
        sys.exit(1)
    return cap


# ── Per-tick camera-loop helpers ─────────────────────────────────────────────

def _maybe_send_frame(frame, gray, prev_gray, frame_id, last_send, args):
    """Apply quality gate; encode and queue the frame for sending if it passes."""
    now        = time.time()
    force_send = (now - last_send) * 1000 >= args.force_send_ms
    should_send = force_send

    if not should_send and now - last_send >= args.frame_interval:
        if (prev_gray is None
                or (blur_score(frame)        >= args.blur_threshold
                    and motion_score(prev_gray, gray) >= args.motion_threshold)):
            should_send = True

    if should_send:
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        b64    = base64.b64encode(buf.tobytes()).decode("utf-8")
        frame_id += 1
        shared["frame_packet"]    = {"data": b64, "frame_id": frame_id, "client_ts": now}
        shared["last_frame_b64"]  = b64
        return frame_id, now

    return frame_id, last_send


def _process_voice(voice, local_whisper):
    """Transcribe any pending utterance and act if the activation word is heard."""
    utterance = voice.get_utterance()
    if utterance is None:
        return
    if local_whisper:
        threading.Thread(
            target=handle_utterance,
            args=(local_whisper, utterance, shared, shared_lock),
            daemon=True,
        ).start()
    else:
        print("[audio] local whisper not available — utterance dropped")


def _get_live_detections(smoother, now):
    """Filter stale/irrelevant detections and run the bbox smoother."""
    det_age_s = now - shared.get("last_detection_ts", 0.0)
    raw = [
        d for d in shared.get("detections", [])
        if d.get("label", "").lower() not in _IGNORE_LABELS
    ] if det_age_s <= DETECTION_TTL_S else []
    tracks = smoother.update(raw)
    return det_age_s, raw, tracks


def _announce_new_equipment(live_detections, now, announced_labels, label_last_seen):
    """
    Speak newly appeared equipment labels.

    Each unique YOLO label is announced once when it first appears.  After
    LABEL_UNSEEN_TIMEOUT_S of absence it is forgotten and can be re-announced.
    """
    for lk in list(announced_labels):
        if now - label_last_seen.get(lk, 0) > LABEL_UNSEEN_TIMEOUT_S:
            del announced_labels[lk]

    for d in live_detections:
        lbl = d.get("label", "").strip()
        if not lbl:
            continue
        lk = lbl.lower()
        label_last_seen[lk] = now
        if lk not in announced_labels:
            announced_labels[lk] = now
            part_name = (d.get("zone") or lbl).replace("_", " ")
            speak(f"{part_name} in view")
            break   # one announcement per tick


def _expire_stale_analysis(now):
    """Clear VLM callout fields once the result is too old to be relevant."""
    if now - shared.get("last_analysis_ts", 0.0) > ANALYSIS_TTL_S:
        shared["vlm_callout"]     = ""
        shared["vlm_description"] = ""
        shared["vlm_findings"]    = []


def _flush_session_actions(session, frame):
    """Save auto-evidence and flush any queued findings to disk."""
    if shared.get("auto_evidence"):
        fname = session.save_evidence(frame, "auto")
        print(f"  [evidence: {fname}]")
        shared["auto_evidence"] = False

    with shared_lock:
        new = shared["new_findings"][:]
        shared["new_findings"] = []
    for f in new:
        session.log_finding(f)


def _sync_hud(hud, voice, det_age_s, now):
    """Push the latest shared-state values into the HUD before rendering."""
    hud.ws_connected    = shared.get("ws_connected", False)
    hud.ws_latency_ms   = shared.get("ws_latency_ms", 0)
    hud.yolo_ms         = shared.get("yolo_ms", 0)
    hud.send_fps        = shared.get("send_fps", 0.0)
    hud.recv_fps        = shared.get("recv_fps", 0.0)
    hud.det_age_ms      = int(det_age_s * 1000)
    hud.dropped_frames  = shared.get("dropped_frames", 0)
    hud.mic_active      = voice.running
    hud.ptt_recording   = voice.ptt_recording
    hud.transcript      = shared.get("transcript", "")
    hud.findings        = shared.get("all_findings", [])
    hud.brief_text      = shared.get("brief_text", "")
    hud.brief_zone      = shared.get("brief_zone", "")
    hud.brief_time      = shared.get("brief_time", 0)
    hud.vlm_callout     = shared.get("vlm_callout", "")
    hud.vlm_callout_time = shared.get("vlm_callout_time", 0)
    hud.vlm_severity    = shared.get("vlm_severity", "GREEN")
    hud.vlm_description = shared.get("vlm_description", "")
    hud.vlm_findings    = shared.get("vlm_findings", [])
    hud.mode            = shared.get("inspection_mode", "general")


def _handle_keyboard(key, session, voice, unit_info, frame, coverage_pct):
    """Process a keypress. Returns True if the user requested quit."""
    global _last_space_ts

    if key == ord("q"):
        return True

    if key == ord(" "):
        now = time.time()
        if now - _last_space_ts >= _PTT_DEBOUNCE_S:
            _last_space_ts = now
            if voice.ptt_recording:
                voice.stop_ptt()
            elif voice.running:
                voice.start_ptt()
        return False

    if key == ord("g"):
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
    elif key == ord("r"):
        _queue_report(unit_info, coverage_pct)
        print("  [requesting report...]")
    return False



def _handle_report_ready(session, coverage_pct):
    """When the backend sends a completed report, save it to disk and speak a confirmation."""
    if not shared.get("report_ready"):
        return
    shared["report_ready"] = False
    report_data = shared.get("report", "")
    session.save_report(report_data)
    pdf_path = session.generate_pdf(shared.get("all_findings", []), report_data, coverage_pct)
    if pdf_path:
        print(f"  [PDF report saved: {pdf_path}]")
        speak("Report saved to session folder.")
    else:
        print(f"  [report saved to {session.dir / 'report.json'}]")
        speak("Report generated.")


def _queue_report(unit_info, coverage_pct):
    elapsed = (datetime.now()).total_seconds() / 60  # approximate; session.start_time not in scope here
    with shared_lock:
        shared["pending_actions"].append(("report", {
            "type":             "generate_report",
            "model":            unit_info["model"],
            "serial":           unit_info["serial"],
            "hours":            unit_info["hours"],
            "technician":       unit_info["technician"],
            "duration_minutes": 0,        # caller fills this in when possible
            "coverage_percent": int(coverage_pct),
        }))


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args     = _parse_args()
    url      = _resolve_ws_url(args.url)
    spec_kb  = _load_spec_kb()

    unit_info = {
        "model":       args.model,
        "serial":      args.serial,
        "hours":       args.hours,
        "technician":  args.technician,
    }

    session        = Session(unit_info)
    smoother       = DetectionSmoother()
    hud            = HUD(unit_info)
    voice          = VoiceCapture()
    local_whisper  = _load_local_whisper()

    shared["inspection_mode"] = args.mode
    start_ws_thread(url, unit_info, spec_kb)
    voice.start()

    cap = _open_camera(args.camera)
    cv2.namedWindow("Dronecat", cv2.WINDOW_NORMAL)

    print(f"Camera {args.camera} open. Connecting to {url}")
    print(f"Unit: {unit_info['model']} | {unit_info['serial']} | {unit_info['hours']}h")
    print(f"Mode: {shared['inspection_mode'].upper()}  |  Session: {session.dir}")
    print("Keys: [g]General [c]CAT [r]Report [e]Evidence [Space]PTT [q]Quit")
    print("Voice: press Space to start recording, press Space again to send\n")
    with shared_lock:
        shared["pending_actions"].append(("set_mode", {"type": "set_mode", "mode": shared["inspection_mode"]}))

    prev_gray        = None
    last_send        = 0.0
    frame_id         = 0
    cat_counter      = 0
    announced_labels = {}   # label_lower → last_announced_ts
    label_last_seen  = {}   # label_lower → last_seen_ts

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            now  = time.time()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            frame_id, last_send = _maybe_send_frame(frame, gray, prev_gray, frame_id, last_send, args)
            prev_gray = gray

            # CAT color presence flag (used by HUD / downstream logic)
            cat_counter += 1
            if cat_counter % 10 == 0:
                shared["cat_visible"] = detect_cat_colors(frame)

            _process_voice(voice, local_whisper)

            det_age_s, live_detections, tracks = _get_live_detections(smoother, now)
            _announce_new_equipment(live_detections, now, announced_labels, label_last_seen)

            _expire_stale_analysis(now)
            _flush_session_actions(session, frame)

            _sync_hud(hud, voice, det_age_s, now)

            completed_zones = set(shared.get("detected_zones", set())) | set(shared.get("confirmed_zones", set()))
            confirmed_zones = set(shared.get("confirmed_zones", set()))
            coverage_pct    = len(completed_zones) / len(ALL_ZONES) * 100.0

            display = hud.render(frame.copy(), tracks, shared.get("zone_status", {}),
                                 coverage_pct, completed_zones, confirmed_zones)
            cv2.imshow("Dronecat", display)

            if shared.get("quit_requested"):
                break

            # Report requested via voice ("generate report")
            if shared.get("request_report"):
                shared["request_report"] = False
                elapsed = (datetime.now() - session.start_time).total_seconds() / 60
                with shared_lock:
                    shared["pending_actions"].append(("report", {
                        "type":             "generate_report",
                        "model":            unit_info["model"],
                        "serial":           unit_info["serial"],
                        "hours":            unit_info["hours"],
                        "technician":       unit_info["technician"],
                        "duration_minutes": int(elapsed),
                        "coverage_percent": int(coverage_pct),
                    }))
                speak("Generating report.")

            _handle_report_ready(session, coverage_pct)

            if _handle_keyboard(cv2.waitKey(30) & 0xFF, session, voice, unit_info, frame, coverage_pct):
                break

    except KeyboardInterrupt:
        pass
    finally:
        voice.stop()
        completed_zones = set(shared.get("detected_zones", set())) | set(shared.get("confirmed_zones", set()))
        session.close(len(completed_zones) / len(ALL_ZONES) * 100.0)
        cap.release()
        cv2.destroyAllWindows()
        print(f"\nSession saved to {session.dir}")


if __name__ == "__main__":
    main()
