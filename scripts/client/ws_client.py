"""
WebSocket client: shared state dict, send/receive loops, and per-message-type handlers.

The `shared` dict is the single source of truth exchanged between the WS thread
and the main camera loop.  `start_ws_thread()` launches the WS loop in a
daemon thread with automatic exponential-backoff reconnection.
"""

import asyncio
import json
import threading
import time

from .audio import speak
from .constants import ALL_ZONES, CALLOUT_COOLDOWN_S, DETECTION_TTL_S, _IGNORE_LABELS
from .detection import FastEventDetector


# ── Shared state ─────────────────────────────────────────────────────────────
# Written by both the WS thread (incoming messages) and the main loop (outgoing
# actions, frame packets).  Protect multi-step mutations with shared_lock.

shared_lock = threading.Lock()

shared = {
    "frame_packet":             None,
    "last_frame_b64":           None,
    "detections":               [],
    "last_detection_ts":        0.0,
    "last_detection_frame_id":  -1,
    "zone_status":              {},
    "new_findings":             [],
    "all_findings":             [],
    "transcript":               "",
    "brief_text":               "",
    "brief_zone":               "",
    "brief_time":               0,
    "spec_text":                "",
    "report":                   None,
    "auto_evidence":            False,
    "ws_connected":             False,
    "ws_latency_ms":            0,
    "yolo_ms":                  0,
    "send_fps":                 0.0,
    "recv_fps":                 0.0,
    "dropped_frames":           0,
    "coverage":                 0,
    "total_zones":              15,
    "detected_zones":           set(),
    "confirmed_zones":          set(),
    "pending_actions":          [],
    "vlm_callout":              "",
    "vlm_callout_time":         0,
    "vlm_severity":             "GREEN",
    "vlm_description":          "",
    "vlm_findings":             [],
    "last_analysis_ts":         0.0,
    "last_analysis_frame_id":   -1,
    "inspection_mode":          "general",
}


# ── WebSocket loop ────────────────────────────────────────────────────────────

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

        # Mutable loop state shared between the two coroutines via closure
        send_count            = 0
        recv_count            = 0
        last_metrics_ts       = time.time()
        frame_send_ts         = {}   # frame_id → send timestamp, for round-trip latency
        last_sent_frame_id    = -1
        last_callout_key      = ""
        last_callout_spoken_ts = 0.0
        fast_events           = FastEventDetector()

        async def sender_loop():
            nonlocal send_count, recv_count, last_metrics_ts, last_sent_frame_id
            while True:
                with shared_lock:
                    actions = shared["pending_actions"][:]
                    shared["pending_actions"] = []

                # Voice questions go first — before any frame — for minimum latency
                voice_actions = [(k, v) for k, v in actions if k == "voice_question"]
                other_actions = [(k, v) for k, v in actions if k != "voice_question"]
                for _, payload in voice_actions:
                    await ws.send(json.dumps(payload))

                packet = shared.get("frame_packet")
                if packet and packet["frame_id"] > last_sent_frame_id:
                    fid = packet["frame_id"]
                    frame_send_ts[fid] = time.time()
                    await ws.send(json.dumps({
                        "type":      "frame",
                        "data":      packet["data"],
                        "frame_id":  fid,
                        "client_ts": packet["client_ts"],
                        "mode":      shared.get("inspection_mode", "general"),
                    }))
                    last_sent_frame_id = fid
                    send_count += 1

                for _, payload in other_actions:
                    await ws.send(json.dumps(payload))

                now = time.time()
                if now - last_metrics_ts >= 1.0:
                    shared["send_fps"] = send_count / (now - last_metrics_ts)
                    shared["recv_fps"] = recv_count / (now - last_metrics_ts)
                    send_count = recv_count = 0
                    last_metrics_ts = now

                await asyncio.sleep(0.01)

        async def receiver_loop():
            nonlocal recv_count, last_callout_key, last_callout_spoken_ts
            while True:
                raw  = await ws.recv()
                recv_count += 1
                msg  = json.loads(raw)
                t    = msg.get("type")

                if t == "detection":
                    _on_detection(msg, frame_send_ts, fast_events)

                elif t == "analysis":
                    last_callout_key, last_callout_spoken_ts = _on_analysis(
                        msg, last_callout_key, last_callout_spoken_ts
                    )

                elif t == "zone_first_seen":
                    print(f"  ** zone_first_seen: {msg.get('zone')} **")

                elif t == "finding":
                    _on_finding(msg, spec_kb)

                elif t == "zone_brief":
                    shared["brief_text"] = msg.get("text", "")
                    shared["brief_zone"] = msg.get("zone", "")
                    shared["brief_time"] = time.time()
                    print(f"  brief [{msg.get('zone')}]: {msg.get('text','')[:80]}")

                elif t == "spec_assessment":
                    shared["spec_text"] = msg.get("result", "")
                    print(f"  spec [{msg.get('zone')}]: {msg.get('result','')[:80]}")

                elif t == "voice_answer":
                    _on_voice_answer(msg)

                elif t == "mode":
                    shared["inspection_mode"] = msg.get("mode", "general")
                    print(f"  mode: {msg.get('mode')}")

                elif t == "report":
                    shared["report"]        = msg.get("data", "")
                    shared["report_ready"]  = True
                    print(f"  REPORT GENERATED ({len(str(shared['report']))} chars)")

                else:
                    print(f"  {t}: {str(msg)[:100]}")

        await asyncio.gather(sender_loop(), receiver_loop())


def start_ws_thread(url, unit_info, spec_kb):
    """Launch the WebSocket loop in a background daemon thread with auto-reconnect."""
    def _run():
        loop    = asyncio.new_event_loop()
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

    threading.Thread(target=_run, daemon=True).start()


# ── Per-message-type handlers ─────────────────────────────────────────────────

def _on_detection(msg, frame_send_ts, fast_events):
    frame_id = int(msg.get("frame_id", -1))
    if frame_id < shared.get("last_detection_frame_id", -1):
        shared["dropped_frames"] = shared.get("dropped_frames", 0) + 1
        return

    shared["last_detection_frame_id"] = frame_id
    shared["last_detection_ts"]        = time.time()
    shared["detections"]               = msg.get("detections", [])
    shared["coverage"]                 = msg.get("coverage", 0)
    shared["total_zones"]              = msg.get("total_zones", 15)
    shared["yolo_ms"]                  = msg.get("yolo_ms", 0)
    if msg.get("mode") in ("general", "797"):
        shared["inspection_mode"] = msg["mode"]

    det_zones = {d.get("zone") for d in shared["detections"] if d.get("zone")}
    if det_zones:
        shared["detected_zones"].update(det_zones)

    if frame_id in frame_send_ts:
        shared["ws_latency_ms"] = int((time.time() - frame_send_ts.pop(frame_id)) * 1000)

    fast_alert = fast_events.check(shared["detections"])
    if fast_alert:
        print(f"  !! FAST ALERT: {fast_alert}")
        speak(fast_alert)
        shared["auto_evidence"] = True
        with shared_lock:
            shared["pending_actions"].append(("vlm", {"type": "request_vlm_analysis"}))

    relevant = [d for d in shared["detections"] if d.get("label", "").lower() not in _IGNORE_LABELS]
    if relevant:
        labels = [f"{d['label']}({d.get('confidence',0):.0%})" for d in relevant[:5]]
        zones  = [d.get("zone") for d in relevant if d.get("zone")]
        print(f"  det: {len(relevant)} obj | {labels} | zones: {zones}")


def _on_analysis(msg, last_callout_key, last_callout_spoken_ts):
    """Handle a VLM analysis result. Returns updated (last_callout_key, last_callout_spoken_ts)."""
    frame_id = int(msg.get("frame_id", -1))
    if frame_id < shared.get("last_analysis_frame_id", -1):
        return last_callout_key, last_callout_spoken_ts

    shared["last_analysis_frame_id"] = frame_id
    shared["last_analysis_ts"]        = time.time()
    if msg.get("mode") in ("general", "797"):
        shared["inspection_mode"] = msg["mode"]

    data         = msg.get("data", {})
    callout      = data.get("callout", "")
    severity     = data.get("severity", "GREEN")
    description  = data.get("description", "")
    zone         = data.get("zone")

    shared["vlm_callout"]      = callout
    shared["vlm_callout_time"] = time.time()
    shared["vlm_severity"]     = severity
    shared["vlm_description"]  = description
    shared["vlm_findings"]     = data.get("findings", [])

    if zone and zone in ALL_ZONES:
        shared["detected_zones"].add(zone)
        if severity in ("YELLOW", "RED"):
            shared["zone_status"][zone] = severity
        elif zone not in shared["zone_status"]:
            shared["zone_status"][zone] = severity

    print(f"  VLM [{severity}]: {callout or description[:60]}")

    spoken_text  = callout if callout else " ".join(description.split()[:6])
    callout_key  = f"{severity}|{spoken_text}".strip()
    now          = time.time()
    should_speak = False

    if severity in ("YELLOW", "RED"):
        should_speak = (callout_key != last_callout_key) or (now - last_callout_spoken_ts > CALLOUT_COOLDOWN_S)
    elif callout_key != last_callout_key and last_callout_key:
        prev_desc   = last_callout_key.split("|", 1)[1] if "|" in last_callout_key else ""
        desc_words  = set(spoken_text.lower().split())
        prev_words  = set(prev_desc.lower().split())
        overlap     = len(desc_words & prev_words) / max(len(desc_words | prev_words), 1)
        should_speak = overlap < 0.5

    if should_speak and spoken_text:
        last_callout_key        = callout_key
        last_callout_spoken_ts  = now
        speak(spoken_text)

    return last_callout_key, last_callout_spoken_ts


def _on_finding(msg, spec_kb):
    finding = msg.get("data", {})
    zone    = finding.get("zone", "?")
    rating  = finding.get("rating", "GREEN")

    if zone in ALL_ZONES:
        shared["confirmed_zones"].add(zone)
    shared["zone_status"][zone] = rating
    with shared_lock:
        shared["new_findings"].append(finding)
        shared["all_findings"].append(finding)

    print(f"  finding: [{zone}] {rating} {finding.get('description','')[:60]}")
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
                "type":          "request_spec_assessment",
                "zone":          zone,
                "rating":        rating,
                "description":   finding.get("description", ""),
                "spec_knowledge": zone_spec.get("spec_text", ""),
                "frame":         shared.get("last_frame_b64", ""),
            }))
        shared["auto_evidence"] = True

    if rating == "RED":
        speak(f"Red alert. {zone_spoken}")


def _on_voice_answer(msg):
    answer = msg.get("text", "")
    shared["voice_answer"]      = answer
    shared["voice_answer_time"] = time.time()
    print(f"  ANSWER: {answer}")
    first_sent = answer.split(".")[0].strip()
    speak((first_sent + ".") if first_sent else answer[:80])


