import asyncio
import base64
import json
import os
import secrets
import struct
import time
import traceback
from datetime import datetime

import modal

from . import app, web_image
from .yolo_detector import YoloDetector, YoloDetector797
from .qwen_vl import Qwen25VLInspector

VLM_ANALYSIS_INTERVAL_S = 3.0

# ── Multi-signal correlation rules ────────────────────────────────────────
# (yolo_label_keywords, vlm_finding_keywords, event_name, description)
_CORRELATION_RULES = [
    (
        {"hydraulic_hose", "hydraulic_cylinder", "hose", "cylinder", "hoist_cylinder", "steering_cylinder"},
        {"leak", "stain", "fluid", "drip", "wet", "seep", "puddle", "oil", "pitting"},
        "hydraulic_leak",
        "Hydraulic component + fluid evidence — possible active leak",
    ),
    (
        {"tire", "rim", "wheel", "lug_nut"},
        {"wear", "cut", "bulge", "crack", "flat", "tread", "damage", "missing", "loose"},
        "tire_damage",
        "Tire or rim damage detected — 63\" OTR tire concern",
    ),
    (
        {"dump_body", "tailgate", "liner"},
        {"crack", "dent", "wear", "damage", "hole", "bent", "weld", "fatigue"},
        "dump_body_wear",
        "Dump body structural damage or liner wear detected",
    ),
    (
        {"suspension_strut", "strut"},
        {"leak", "oil", "low", "sag", "damage", "nitrogen", "ride_height"},
        "suspension_issue",
        "Suspension strut anomaly — possible oil leak or low charge",
    ),
    (
        {"cab_glass", "cab", "windshield", "mirror"},
        {"crack", "chip", "broken", "shatter", "obstruct", "damage", "visibility"},
        "cab_visibility",
        "Cab glass or mirror damage — operator visibility concern",
    ),
    (
        {"engine_compartment", "exhaust", "engine", "radiator", "cooling", "turbocharger"},
        {"smoke", "overheat", "discolor", "hot", "leak", "coolant", "steam", "residue"},
        "engine_thermal",
        "Engine/cooling area thermal or fluid anomaly",
    ),
    (
        {"step", "handrail", "ladder"},
        {"loose", "missing", "bent", "broken", "slip", "grease", "damage"},
        "access_safety",
        "Access point hazard — steps or handrails compromised",
    ),
]

_MAX_ANALYSIS_HISTORY = 10
_INSIGHT_COOLDOWN_S = 15.0


def _correlate_signals(yolo_labels, vlm_text, vlm_severity, recent_insights):
    """Match YOLO labels against VLM text. Returns triggered insight dicts."""
    if not yolo_labels or not vlm_text:
        return []
    now = time.time()
    lower_text = vlm_text.lower()
    label_set = {l.lower().replace(" ", "_") for l in yolo_labels}
    results = []
    for rule_labels, rule_keywords, event_name, description in _CORRELATION_RULES:
        if now - recent_insights.get(event_name, 0) < _INSIGHT_COOLDOWN_S:
            continue
        label_match = label_set & rule_labels
        keyword_match = [kw for kw in rule_keywords if kw in lower_text]
        if label_match and keyword_match:
            recent_insights[event_name] = now
            results.append({
                "event": event_name,
                "description": description,
                "components": sorted(label_match),
                "evidence_keywords": keyword_match[:3],
                "vlm_severity": vlm_severity,
            })
    return results


def _compute_zone_trend(history_list):
    """Compute severity trend from a zone's analysis history."""
    if len(history_list) < 2:
        return None
    counts = {"RED": 0, "YELLOW": 0, "GREEN": 0}
    total_conf = 0.0
    for entry in history_list:
        sev = entry.get("severity", "GREEN")
        if sev in counts:
            counts[sev] += 1
        total_conf += entry.get("confidence", 0.5)
    n = len(history_list)
    avg_conf = round(total_conf / n, 2)

    sev_val = {"GREEN": 0, "YELLOW": 1, "RED": 2}
    recent = [sev_val.get(e["severity"], 0) for e in history_list[-3:]]
    early = [sev_val.get(e["severity"], 0) for e in history_list[:3]]
    r_avg = sum(recent) / len(recent)
    e_avg = sum(early) / len(early)
    if r_avg > e_avg + 0.3:
        drift = "worsening"
    elif r_avg < e_avg - 0.3:
        drift = "improving"
    elif counts["RED"] > 0 and counts["GREEN"] > 0 and counts["RED"] + counts["GREEN"] > counts["YELLOW"]:
        drift = "inconsistent"
    else:
        drift = "stable"
    return {
        "severity_counts": counts,
        "confidence_avg": avg_conf,
        "drift": drift,
        "sample_count": n,
    }


_sessions = {}


@app.function(
    image=web_image,
    min_containers=1,
    scaledown_window=600,
    secrets=[modal.Secret.from_name("catwatch-db")],
    # WebSocket sessions use in-memory state — all connections MUST hit the same
    # container.  High concurrency limit tells Modal "one container can handle
    # many long-lived WS connections, don't spin up extras."
    allow_concurrent_inputs=1000,
)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    api = FastAPI()

    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    yolo = YoloDetector()
    yolo797 = YoloDetector797()
    qwen = Qwen25VLInspector()

    @api.websocket("/ws")
    async def inspection_ws(ws: WebSocket):
        await ws.accept()

        seen_zones = set()
        zone_findings = {}
        sensor_snapshot = {}
        latest_frame_b64 = None
        latest_frame_id = -1
        latest_frame_client_ts = 0.0
        last_vlm_run_ts = 0.0
        vlm_busy = False
        inspection_mode = "general"
        last_vlm_zone = None

        async def run_vlm_analysis(frame_b64, frame_id, frame_client_ts, triggered_by="cadence"):
            nonlocal vlm_busy, last_vlm_run_ts, last_vlm_zone
            if vlm_busy:
                return
            vlm_busy = True
            last_vlm_run_ts = time.monotonic()
            print(f"[VLM] Starting analysis frame {frame_id} (trigger={triggered_by}, zone_hint={last_vlm_zone})")
            try:
                from backend.prompts import build_zone_inspection_prompt
                persona, schema = build_zone_inspection_prompt(last_vlm_zone, mode=inspection_mode)

                analysis = await asyncio.wait_for(
                    asyncio.to_thread(qwen.analyze_frame.remote, frame_b64, persona, schema),
                    timeout=120,
                )
                if not isinstance(analysis, dict):
                    analysis = {"description": str(analysis), "severity": "GREEN", "findings": [], "callout": "", "confidence": 0.5, "component": None}
                if "component" in analysis and "zone" not in analysis:
                    analysis["zone"] = analysis["component"]
                elif "zone" in analysis and "component" not in analysis:
                    analysis["component"] = analysis["zone"]
                analysis["triggered_by"] = triggered_by

                new_zone = analysis.get("component") or analysis.get("zone")
                if new_zone:
                    last_vlm_zone = new_zone

                print(f"[VLM] Done frame {frame_id}: [{analysis.get('severity','?')}] {analysis.get('description', '')[:80]}")
                await ws.send_json({
                    "type": "analysis",
                    "data": analysis,
                    "mode": inspection_mode,
                    "frame_id": frame_id,
                    "client_ts": frame_client_ts,
                    "server_ts": time.time(),
                })
            except asyncio.TimeoutError:
                print(f"[VLM] Timeout frame {frame_id}")
                try:
                    await ws.send_json({
                        "type": "analysis",
                        "data": {"description": "VLM warming up, please wait...", "severity": "GREEN", "findings": [], "callout": "VLM loading", "confidence": 0.0, "component": None},
                        "mode": inspection_mode, "frame_id": frame_id,
                        "client_ts": frame_client_ts, "server_ts": time.time(),
                    })
                except Exception:
                    pass
            except Exception as e:
                print(f"[VLM] Error frame {frame_id}: {e}")
                traceback.print_exc()
                try:
                    await ws.send_json({
                        "type": "analysis",
                        "data": {"description": f"VLM error: {str(e)[:80]}", "severity": "GREEN", "findings": [], "callout": "", "confidence": 0.0, "component": None},
                        "mode": inspection_mode, "frame_id": frame_id,
                        "client_ts": frame_client_ts, "server_ts": time.time(),
                    })
                except Exception:
                    pass
            finally:
                vlm_busy = False

        async def run_zone_brief(zone_id, hours, spec_knowledge):
            print(f"[BRIEF] Starting zone brief for {zone_id}")
            try:
                from backend.prompts import BRIEF_PROMPT
                from backend.zone_config import ZONE_PROMPT_MAP
                prompt_key = ZONE_PROMPT_MAP.get(zone_id, "")
                sub_title = prompt_key.replace("_", " ").title()
                audio_data = sensor_snapshot.get("audio", {})
                ir_data = sensor_snapshot.get("ir", {})
                light_data = sensor_snapshot.get("light", {})
                prompt = BRIEF_PROMPT.format(
                    zone=zone_id, hours=hours, sub_section_title=sub_title,
                    unit_history="No prior history available",
                    fleet_stats="No fleet data available",
                    spec_knowledge=spec_knowledge,
                    audio_score=audio_data.get("anomaly_score", 0),
                    ir_score=ir_data.get("anomaly_score", 0),
                    light_quality=light_data.get("quality", "unknown"),
                )
                brief = await asyncio.wait_for(
                    asyncio.to_thread(qwen.zone_brief.remote, prompt), timeout=60,
                )
            except asyncio.TimeoutError:
                brief = "Zone brief timed out — VLM may still be warming up."
            except Exception as e:
                print(f"[BRIEF] Error for {zone_id}: {e}")
                brief = f"Brief error: {str(e)[:60]}"
            print(f"[BRIEF] Done for {zone_id}")
            await ws.send_json({"type": "zone_brief", "zone": zone_id, "text": brief})

        async def run_spec_assessment(zone_id, tech_rating, tech_description, spec_knowledge, frame_b64):
            print(f"[SPEC] Starting spec assessment for {zone_id}")
            try:
                from backend.prompts import SPEC_PROMPT, get_sub_section_prompt
                from backend.zone_config import ZONE_PROMPT_MAP
                prompt_key = ZONE_PROMPT_MAP.get(zone_id, "")
                sub_prompt = get_sub_section_prompt(prompt_key)
                prompt = SPEC_PROMPT.format(
                    zone=zone_id, tech_rating=tech_rating, tech_description=tech_description,
                    spec_knowledge=spec_knowledge, sub_section_prompt=sub_prompt[:500],
                )
                result = await asyncio.wait_for(
                    asyncio.to_thread(qwen.spec_assessment.remote, prompt, frame_b64), timeout=60,
                )
            except asyncio.TimeoutError:
                result = "Spec assessment timed out — VLM may still be warming up."
            except Exception as e:
                print(f"[SPEC] Error for {zone_id}: {e}")
                result = f"Spec error: {str(e)[:60]}"
            print(f"[SPEC] Done for {zone_id}")
            await ws.send_json({"type": "spec_assessment", "zone": zone_id, "result": result})

        async def run_report(msg):
            print("[REPORT] Starting report generation")
            try:
                from backend.prompts import REPORT_PROMPT
                now = datetime.utcnow()
                all_findings = [f for fs in zone_findings.values() for f in (fs if isinstance(fs, list) else [fs])]
                prompt = REPORT_PROMPT.format(
                    model=msg.get("model", "Unknown"), serial=msg.get("serial", ""),
                    hours=msg.get("hours", 0), technician=msg.get("technician", ""),
                    duration_minutes=msg.get("duration_minutes", 0),
                    coverage_percent=msg.get("coverage_percent", 0),
                    findings_json=json.dumps(all_findings, indent=2),
                    date_compact=now.strftime("%Y%m%d"), timestamp=now.isoformat() + "Z",
                )
                report = await asyncio.wait_for(
                    asyncio.to_thread(qwen.generate_report.remote, prompt), timeout=120,
                )
            except asyncio.TimeoutError:
                report = "Report generation timed out — try again in a moment."
            except Exception as e:
                print(f"[REPORT] Error: {e}")
                report = f"Report error: {str(e)[:60]}"
            if isinstance(report, str):
                start = report.find("{")
                end = report.rfind("}") + 1
                if start != -1 and end > start:
                    try:
                        report = json.loads(report[start:end])
                    except json.JSONDecodeError:
                        pass
            print(f"[REPORT] Done ({len(str(report))} chars)")
            await ws.send_json({"type": "report", "data": report})

        async def run_voice_answer(question, frame_b64):
            print(f"[VOICE Q] {question[:60]}")
            try:
                if inspection_mode in ("cat", "797"):
                    context = "You are inspecting a CAT 797F mining haul truck."
                else:
                    context = "You are a visual copilot for general scene and safety monitoring."
                prompt = (
                    f"{context} The technician asks: \"{question}\""
                    "\nAnswer in one concise sentence based on the image."
                    " Be specific and avoid repeating the question."
                )
                answer = await asyncio.wait_for(
                    asyncio.to_thread(qwen.generate.remote, prompt, frame_b64), timeout=30,
                )
            except asyncio.TimeoutError:
                answer = "Still loading, try again in a moment."
            except Exception as e:
                print(f"[VOICE Q] Error: {e}")
                answer = "Could not process question."
            print(f"[VOICE A] {answer[:80]}")
            await ws.send_json({"type": "voice_answer", "text": answer, "mode": inspection_mode})

        yolo_busy = False
        pending_frame = None

        async def process_yolo(frame_b64, frame_id, frame_client_ts):
            nonlocal yolo_busy, pending_frame

            yolo_busy = True
            try:
                if inspection_mode == "797":
                    result = await asyncio.to_thread(yolo797.detect.remote, frame_b64)
                else:
                    result = await asyncio.to_thread(yolo.detect.remote, frame_b64, inspection_mode)
                detections = result.get("detections", [])
                yolo_ms = result.get("yolo_ms", 0)

                if inspection_mode == "797":
                    from backend.zone_config import zone_from_label_797, zone_from_bbox_797
                    _zone_fn = zone_from_label_797
                    _bbox_fn = zone_from_bbox_797
                else:
                    from backend.zone_config import zone_from_label, zone_from_bbox
                    _zone_fn = zone_from_label
                    _bbox_fn = zone_from_bbox
                zone_events = []
                for det in detections:
                    zone_id = _zone_fn(det["label"])
                    if not zone_id:
                        zone_id = _bbox_fn(det["bbox"])
                    det["zone"] = zone_id
                    if zone_id and zone_id not in seen_zones:
                        seen_zones.add(zone_id)
                        zone_events.append(zone_id)

                await ws.send_json({
                    "type": "detection",
                    "detections": detections,
                    "coverage": len(seen_zones),
                    "total_zones": 8 if inspection_mode == "797" else 15,
                    "mode": inspection_mode,
                    "yolo_ms": yolo_ms,
                    "frame_id": frame_id,
                    "client_ts": frame_client_ts,
                    "server_ts": time.time(),
                })
                for zone_id in zone_events:
                    await ws.send_json({"type": "zone_first_seen", "zone": zone_id})

                if (
                    detections
                    and not vlm_busy
                    and latest_frame_b64
                    and (time.monotonic() - last_vlm_run_ts) >= VLM_ANALYSIS_INTERVAL_S
                ):
                    asyncio.create_task(
                        run_vlm_analysis(
                            latest_frame_b64, latest_frame_id, latest_frame_client_ts,
                            triggered_by="cadence",
                        )
                    )

            except Exception as e:
                print(f"[YOLO] Error: {e}")
            finally:
                yolo_busy = False
                if pending_frame:
                    pf = pending_frame
                    pending_frame = None
                    asyncio.create_task(process_yolo(pf[0], pf[1], pf[2]))

        try:
            while True:
                raw = await ws.receive_text()
                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "frame":
                    frame_b64 = msg["data"]
                    frame_id = int(msg.get("frame_id", 0))
                    frame_client_ts = float(msg.get("client_ts", 0))
                    incoming_mode = str(msg.get("mode", "")).lower()
                    if incoming_mode in ("general", "cat", "797"):
                        inspection_mode = incoming_mode
                    latest_frame_b64 = frame_b64
                    latest_frame_id = frame_id
                    latest_frame_client_ts = frame_client_ts

                    if yolo_busy:
                        pending_frame = (frame_b64, frame_id, frame_client_ts)
                    else:
                        pending_frame = None
                        asyncio.create_task(process_yolo(frame_b64, frame_id, frame_client_ts))

                elif msg_type == "sensor":
                    sensor_snapshot = msg.get("data", {})

                elif msg_type == "request_zone_brief":
                    asyncio.create_task(run_zone_brief(
                        msg["zone"], msg.get("hours", 0), msg.get("spec_knowledge", ""),
                    ))

                elif msg_type == "request_spec_assessment":
                    asyncio.create_task(run_spec_assessment(
                        msg["zone"], msg["rating"], msg["description"],
                        msg.get("spec_knowledge", ""), msg.get("frame", ""),
                    ))

                elif msg_type == "generate_report":
                    asyncio.create_task(run_report(msg))

                elif msg_type == "voice_question":
                    asyncio.create_task(run_voice_answer(
                        msg.get("text", ""), msg.get("frame", ""),
                    ))

                elif msg_type == "request_vlm_analysis":
                    if latest_frame_b64 and not vlm_busy:
                        asyncio.create_task(
                            run_vlm_analysis(
                                latest_frame_b64, latest_frame_id, latest_frame_client_ts,
                                triggered_by="manual_request",
                            )
                        )

                elif msg_type == "set_mode":
                    requested_mode = str(msg.get("mode", "")).lower()
                    if requested_mode in ("general", "cat", "797"):
                        inspection_mode = requested_mode
                    await ws.send_json({"type": "mode", "mode": inspection_mode})

        except WebSocketDisconnect:
            pass

    @api.post("/api/sessions")
    async def create_session(request: Request):
        from .db import validate_api_key, create_session as db_create_session, close_active_sessions_for_user

        body = await request.json()
        api_key = body.get("api_key", "")
        mode = body.get("mode", "general")
        unit_serial = body.get("unit_serial")
        unit_model = body.get("model")
        fleet_tag = body.get("fleet_tag")
        location = body.get("location")

        if not api_key:
            return JSONResponse({"error": "api_key required"}, status_code=400)

        key_info = await validate_api_key(api_key)
        if not key_info:
            return JSONResponse({"error": "Invalid API key"}, status_code=401)

        # Close any existing active sessions for this user
        closed_ids = await close_active_sessions_for_user(key_info["user_id"])
        for old_id in closed_ids:
            old_session = _sessions.pop(old_id, None)
            if old_session:
                for vws in list(old_session.get("viewer_wss", [])):
                    try:
                        await vws.send_json({"type": "session_ended", "data": {
                            "session_id": old_id, "zones_inspected": len(old_session.get("seen_zones", set())),
                            "total_zones": len(old_session.get("dynamic_zones", [])) or 15,
                            "coverage_pct": 0, "findings_count": 0, "mode": old_session.get("mode", "general"),
                        }})
                        await vws.close()
                    except Exception:
                        pass
                iws = old_session.get("ingest_ws")
                if iws:
                    try:
                        await iws.close()
                    except Exception:
                        pass
                print(f"[SESSION] Force-closed stale session {old_id} for user {key_info['user_id']}")

        session_id = secrets.token_hex(6)

        await db_create_session(
            session_id, key_info["api_key_id"], key_info["user_id"], mode,
            unit_serial=unit_serial, model=unit_model, fleet_tag=fleet_tag,
        )

        _sessions[session_id] = {
            "id": session_id,
            "api_key_id": key_info["api_key_id"],
            "user_id": key_info["user_id"],
            "mode": mode,
            "unit_serial": unit_serial,
            "unit_model": unit_model,
            "fleet_tag": fleet_tag,
            "location": location,
            "unit_context": None,
            "ingest_ws": None,
            "viewer_wss": [],
            "seen_zones": set(),
            "zone_findings": {},
            "sensor_snapshot": {},
            "latest_frame_b64": None,
            "latest_frame_id": -1,
            "latest_frame_client_ts": 0.0,
            "last_vlm_run_ts": 0.0,
            "vlm_busy": False,
            "last_vlm_zone": None,
            "yolo_busy": False,
            "pending_frame": None,
            "equipment_info": None,
            "equipment_id_done": False,
            "dynamic_zones": [],
            "analysis_history": {},
            "last_yolo_labels": set(),
            "insight_cooldowns": {},
        }

        dashboard_host = os.environ.get("DASHBOARD_URL", "https://catwatch-hackillinois.vercel.app")
        ws_host = os.environ.get("MODAL_WS_HOST", request.base_url.hostname)
        scheme = "wss" if request.url.scheme == "https" else "ws"

        return JSONResponse({
            "session_id": session_id,
            "dashboard_url": f"{dashboard_host}/session/{session_id}",
            "ws_url": f"{scheme}://{ws_host}/ws/ingest/{session_id}",
        })

    @api.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        sess = _sessions.get(session_id)
        if not sess:
            return JSONResponse({"error": "Session not found"}, status_code=404)
        return JSONResponse({
            "session_id": sess["id"],
            "mode": sess["mode"],
            "zones_seen": len(sess["seen_zones"]),
            "active": sess["ingest_ws"] is not None,
        })

    async def _broadcast(session, msg):
        """Send JSON to all viewer WebSockets in parallel with timeout."""
        viewers = session["viewer_wss"][:]
        if not viewers:
            return

        async def _send(ws):
            try:
                await asyncio.wait_for(ws.send_json(msg), timeout=0.2)
            except Exception:
                return ws
            return None

        results = await asyncio.gather(*[_send(ws) for ws in viewers])
        for ws in results:
            if ws is not None and ws in session["viewer_wss"]:
                session["viewer_wss"].remove(ws)

    async def _broadcast_bytes(session, data: bytes):
        """Send binary data to all viewer WebSockets in parallel with timeout."""
        viewers = session["viewer_wss"][:]
        if not viewers:
            return

        async def _send(ws):
            try:
                await asyncio.wait_for(ws.send_bytes(data), timeout=0.2)
            except Exception:
                return ws
            return None

        results = await asyncio.gather(*[_send(ws) for ws in viewers])
        for ws in results:
            if ws is not None and ws in session["viewer_wss"]:
                session["viewer_wss"].remove(ws)

    async def _run_session_pipeline(session, ingest_ws):
        """Run the YOLO→Qwen pipeline for a session, reading frames from ingest_ws."""

        async def send_all(msg):
            """Send to ingest SDK + all viewers."""
            try:
                await ingest_ws.send_json(msg)
            except Exception:
                pass
            await _broadcast(session, msg)

        async def run_vlm(frame_b64, frame_id, frame_client_ts, triggered_by="cadence"):
            if session["vlm_busy"]:
                return
            session["vlm_busy"] = True
            session["last_vlm_run_ts"] = time.monotonic()
            try:
                from backend.prompts import build_zone_inspection_prompt
                persona, schema = build_zone_inspection_prompt(
                    session["last_vlm_zone"], mode=session["mode"],
                    equipment_info=session.get("equipment_info"),
                )
                unit_ctx = session.get("unit_context")
                if unit_ctx:
                    persona = f"{persona}\n\n--- Unit Memory ---\n{unit_ctx}"
                analysis = await asyncio.wait_for(
                    asyncio.to_thread(qwen.analyze_frame.remote, frame_b64, persona, schema),
                    timeout=120,
                )
                if not isinstance(analysis, dict):
                    analysis = {"description": str(analysis), "severity": "GREEN", "findings": [], "callout": "", "confidence": 0.5, "component": None}
                if "component" in analysis and "zone" not in analysis:
                    analysis["zone"] = analysis["component"]
                elif "zone" in analysis and "component" not in analysis:
                    analysis["component"] = analysis["zone"]
                analysis["triggered_by"] = triggered_by
                new_zone = analysis.get("component") or analysis.get("zone")
                if new_zone:
                    session["last_vlm_zone"] = new_zone

                msg = {
                    "type": "analysis", "data": analysis,
                    "mode": session["mode"], "frame_id": frame_id,
                    "client_ts": frame_client_ts, "server_ts": time.time(),
                }
                await send_all(msg)

                from .db import save_finding
                severity = analysis.get("severity", "GREEN")
                for f in analysis.get("findings", []):
                    if isinstance(f, str) and f.strip():
                        zone = analysis.get("component") or analysis.get("zone") or "General"
                        finding_data = {"zone": zone, "rating": severity, "description": f, "createdAt": datetime.utcnow().isoformat() + "Z"}
                        if severity in ("RED", "YELLOW") and frame_b64:
                            finding_data["snapshot"] = frame_b64
                        session["zone_findings"].setdefault(zone, []).append(finding_data)
                        await send_all({"type": "finding", "data": finding_data})
                        try:
                            await save_finding(session["id"], zone, severity, f)
                        except Exception as e:
                            print(f"[DB] save_finding error: {e}")

                # ── Analysis history + severity trend ─────────────────
                zone_key = analysis.get("component") or analysis.get("zone") or "_global"
                hist = session["analysis_history"].setdefault(zone_key, [])
                hist.append({
                    "severity": severity,
                    "confidence": analysis.get("confidence", 0.5),
                    "ts": time.time(),
                })
                if len(hist) > _MAX_ANALYSIS_HISTORY:
                    session["analysis_history"][zone_key] = hist[-_MAX_ANALYSIS_HISTORY:]
                trend = _compute_zone_trend(hist)
                if trend:
                    await send_all({"type": "zone_trend", "zone": zone_key, "trend": trend})

                # ── Multi-signal correlation ──────────────────────────
                vlm_text = analysis.get("description", "") + " " + " ".join(
                    str(f) for f in analysis.get("findings", []) if f
                )
                insights = _correlate_signals(
                    session.get("last_yolo_labels", set()),
                    vlm_text, severity,
                    session["insight_cooldowns"],
                )
                for insight in insights:
                    await send_all({"type": "insight", "data": insight})
                    print(f"[INSIGHT] {insight['event']}: {insight['description']}")

            except asyncio.TimeoutError:
                try:
                    await send_all({
                        "type": "analysis",
                        "data": {"description": "VLM warming up...", "severity": "GREEN", "findings": [], "callout": "VLM loading", "confidence": 0.0, "component": None},
                        "mode": session["mode"], "frame_id": frame_id,
                        "client_ts": frame_client_ts, "server_ts": time.time(),
                    })
                except Exception:
                    pass
            except Exception as e:
                print(f"[VLM] Error: {e}")
                traceback.print_exc()
            finally:
                session["vlm_busy"] = False

        async def run_report_session(msg):
            try:
                from backend.prompts import REPORT_PROMPT
                now = datetime.utcnow()
                all_findings = [f for fs in session["zone_findings"].values() for f in (fs if isinstance(fs, list) else [fs])]
                prompt = REPORT_PROMPT.format(
                    model=msg.get("model", session.get("model") or "Unknown"),
                    serial=msg.get("serial", session.get("unit_serial") or ""),
                    hours=msg.get("hours", 0), technician=msg.get("technician", ""),
                    duration_minutes=msg.get("duration_minutes", 0),
                    coverage_percent=msg.get("coverage_percent", 0),
                    findings_json=json.dumps(all_findings, indent=2),
                    date_compact=now.strftime("%Y%m%d"), timestamp=now.isoformat() + "Z",
                )
                report = await asyncio.wait_for(
                    asyncio.to_thread(qwen.generate_report.remote, prompt), timeout=120,
                )
            except asyncio.TimeoutError:
                report = "Report generation timed out."
            except Exception as e:
                report = f"Report error: {str(e)[:60]}"
            if isinstance(report, str):
                start = report.find("{")
                end = report.rfind("}") + 1
                if start != -1 and end > start:
                    try:
                        report = json.loads(report[start:end])
                    except json.JSONDecodeError:
                        pass
            await send_all({"type": "report", "data": report})
            from .db import save_report
            try:
                await save_report(session["id"], report)
            except Exception as e:
                print(f"[DB] save_report error: {e}")

        async def run_voice_session(question, frame_b64):
            try:
                if session["mode"] in ("cat", "797"):
                    context = "You are inspecting a CAT 797F mining haul truck."
                else:
                    context = "You are a visual copilot."
                prompt = (
                    f'{context} The technician asks: "{question}"\n'
                    "Answer based on what you see in the image. "
                    "Keep each sentence short and direct. "
                    "If it's a yes/no question, state yes or no first, then briefly explain why. "
                    "For all other questions, give a specific and detailed answer with concrete observations — never be vague."
                )
                answer = await asyncio.wait_for(
                    asyncio.to_thread(qwen.generate.remote, prompt, frame_b64), timeout=30,
                )
            except asyncio.TimeoutError:
                answer = "Still loading, try again in a moment."
            except Exception:
                answer = "Could not process question."
            await send_all({"type": "voice_answer", "text": answer, "mode": session["mode"]})

        async def process_yolo_session(frame_b64, frame_id, frame_client_ts):
            session["yolo_busy"] = True
            try:
                if session["mode"] == "797":
                    result = await asyncio.to_thread(yolo797.detect.remote, frame_b64)
                else:
                    result = await asyncio.to_thread(yolo.detect.remote, frame_b64, session["mode"])
                detections = result.get("detections", [])
                yolo_ms = result.get("yolo_ms", 0)

                if session["mode"] == "797":
                    from backend.zone_config import zone_from_label_797, zone_from_bbox_797
                    _zone_fn = zone_from_label_797
                    _bbox_fn = zone_from_bbox_797
                else:
                    from backend.zone_config import zone_from_label, zone_from_bbox
                    _zone_fn = zone_from_label
                    _bbox_fn = zone_from_bbox
                zone_events = []
                for det in detections:
                    zone_id = _zone_fn(det["label"])
                    if not zone_id:
                        zone_id = _bbox_fn(det["bbox"])
                    det["zone"] = zone_id
                    if zone_id and zone_id not in session["seen_zones"]:
                        session["seen_zones"].add(zone_id)
                        zone_events.append(zone_id)

                session["last_yolo_labels"] = {det["label"] for det in detections if det.get("label")}

                total_z = len(session["dynamic_zones"]) or (8 if session["mode"] == "797" else 15)
                det_msg = {
                    "type": "detection", "detections": detections,
                    "coverage": len(session["seen_zones"]), "total_zones": total_z,
                    "mode": session["mode"], "yolo_ms": yolo_ms,
                    "frame_id": frame_id, "client_ts": frame_client_ts,
                    "server_ts": time.time(),
                }
                await send_all(det_msg)
                for zid in zone_events:
                    await send_all({"type": "zone_first_seen", "zone": zid})

                # Equipment auto-identification on first frame with detections
                if detections and not session["equipment_id_done"] and session["latest_frame_b64"]:
                    session["equipment_id_done"] = True
                    asyncio.create_task(_run_equipment_id(session, session["latest_frame_b64"], qwen, send_all))

                if (
                    detections
                    and not session["vlm_busy"]
                    and session["latest_frame_b64"]
                    and (time.monotonic() - session["last_vlm_run_ts"]) >= VLM_ANALYSIS_INTERVAL_S
                ):
                    asyncio.create_task(run_vlm(
                        session["latest_frame_b64"], session["latest_frame_id"],
                        session["latest_frame_client_ts"], triggered_by="cadence",
                    ))
            except Exception as e:
                print(f"[YOLO] Error: {e}")
            finally:
                session["yolo_busy"] = False
                if session["pending_frame"]:
                    pf = session["pending_frame"]
                    session["pending_frame"] = None
                    asyncio.create_task(process_yolo_session(pf[0], pf[1], pf[2]))

        _MODE_MAP = {0: "general", 1: "cat", 2: "797"}

        try:
            while True:
                ws_msg = await ingest_ws.receive()

                if ws_msg.get("type") == "websocket.disconnect":
                    break

                if "bytes" in ws_msg and ws_msg["bytes"]:
                    raw_bytes = ws_msg["bytes"]
                    if len(raw_bytes) < 13:
                        continue

                    frame_id, frame_client_ts, mode_byte = struct.unpack_from("!IdB", raw_bytes)
                    jpeg_bytes = raw_bytes[13:]

                    incoming_mode = _MODE_MAP.get(mode_byte, "general")
                    if incoming_mode in ("general", "cat", "797"):
                        session["mode"] = incoming_mode

                    session["latest_frame_b64"] = base64.b64encode(jpeg_bytes).decode("ascii")
                    session["latest_frame_id"] = frame_id
                    session["latest_frame_client_ts"] = frame_client_ts

                    viewer_payload = struct.pack("!I", frame_id) + jpeg_bytes
                    asyncio.create_task(_broadcast_bytes(session, viewer_payload))

                    if not session["viewer_wss"]:
                        continue

                    if session["yolo_busy"]:
                        session["pending_frame"] = (session["latest_frame_b64"], frame_id, frame_client_ts)
                    else:
                        session["pending_frame"] = None
                        asyncio.create_task(process_yolo_session(session["latest_frame_b64"], frame_id, frame_client_ts))

                    continue

                raw = ws_msg.get("text", "")
                if not raw:
                    continue
                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "frame":
                    frame_b64 = msg["data"]
                    frame_id = int(msg.get("frame_id", 0))
                    frame_client_ts = float(msg.get("client_ts", 0))
                    incoming_mode = str(msg.get("mode", "")).lower()
                    if incoming_mode in ("general", "cat", "797"):
                        session["mode"] = incoming_mode
                    session["latest_frame_b64"] = frame_b64
                    session["latest_frame_id"] = frame_id
                    session["latest_frame_client_ts"] = frame_client_ts

                    jpeg_bytes = base64.b64decode(frame_b64)
                    viewer_payload = struct.pack("!I", frame_id) + jpeg_bytes
                    asyncio.create_task(_broadcast_bytes(session, viewer_payload))

                    if session["viewer_wss"]:
                        if session["yolo_busy"]:
                            session["pending_frame"] = (frame_b64, frame_id, frame_client_ts)
                        else:
                            session["pending_frame"] = None
                            asyncio.create_task(process_yolo_session(frame_b64, frame_id, frame_client_ts))

                elif msg_type == "sensor":
                    session["sensor_snapshot"] = msg.get("data", {})

                elif msg_type == "generate_report":
                    asyncio.create_task(run_report_session(msg))

                elif msg_type == "voice_question":
                    asyncio.create_task(run_voice_session(
                        msg.get("text", ""), msg.get("frame", ""),
                    ))

                elif msg_type == "request_vlm_analysis":
                    if session["latest_frame_b64"] and not session["vlm_busy"]:
                        asyncio.create_task(run_vlm(
                            session["latest_frame_b64"], session["latest_frame_id"],
                            session["latest_frame_client_ts"], triggered_by="manual_request",
                        ))

                elif msg_type == "set_mode":
                    requested_mode = str(msg.get("mode", "")).lower()
                    if requested_mode in ("general", "cat", "797"):
                        session["mode"] = requested_mode
                    await send_all({"type": "mode", "mode": session["mode"]})

                elif msg_type == "unit_context":
                    session["unit_context"] = msg.get("context", "")
                    print(f"[MEMORY] Received unit context for session {session['id']}: {str(session['unit_context'])[:100]}")

                elif msg_type == "request_zone_brief":
                    asyncio.create_task(_run_zone_brief_session(
                        session, msg, send_all, qwen,
                    ))

        except (WebSocketDisconnect, RuntimeError):
            pass

    async def _run_equipment_id(session, frame_b64, qwen_ref, send_all_fn):
        """Identify equipment type and build dynamic inspection checklist from the first good frame."""
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(qwen_ref.identify_equipment.remote, frame_b64),
                timeout=30,
            )
            session["equipment_info"] = result
            zones = result.get("inspectable_zones", [])
            if zones:
                session["dynamic_zones"] = zones
            equip_msg = {
                "type": "equipment_identified",
                "data": result,
            }
            await send_all_fn(equip_msg)
            print(f"[EQUIP-ID] Identified: {result.get('equipment_type')} / {result.get('model_guess')} — {len(zones)} zones")
        except Exception as e:
            print(f"[EQUIP-ID] Error: {e}")
            session["equipment_id_done"] = False

    async def _run_zone_brief_session(session, msg, send_all, qwen_ref):
        """Run zone brief for a platform session, using Supermemory context if available."""
        zone_id = msg["zone"]
        hours = msg.get("hours", 0)
        spec_knowledge = msg.get("spec_knowledge", "")
        unit_history = msg.get("unit_history", "No prior history available")
        fleet_stats = msg.get("fleet_stats", "No fleet data available")
        try:
            from backend.prompts import BRIEF_PROMPT
            from backend.zone_config import ZONE_PROMPT_MAP
            prompt_key = ZONE_PROMPT_MAP.get(zone_id, "")
            sub_title = prompt_key.replace("_", " ").title()
            sensor = session.get("sensor_snapshot", {})
            prompt = BRIEF_PROMPT.format(
                zone=zone_id, hours=hours, sub_section_title=sub_title,
                unit_history=unit_history,
                fleet_stats=fleet_stats,
                spec_knowledge=spec_knowledge,
                audio_score=sensor.get("audio", {}).get("anomaly_score", 0),
                ir_score=sensor.get("ir", {}).get("anomaly_score", 0),
                light_quality=sensor.get("light", {}).get("quality", "unknown"),
            )
            brief = await asyncio.wait_for(
                asyncio.to_thread(qwen_ref.zone_brief.remote, prompt), timeout=60,
            )
        except asyncio.TimeoutError:
            brief = "Zone brief timed out — VLM may still be warming up."
        except Exception as e:
            print(f"[BRIEF] Error for {zone_id}: {e}")
            brief = f"Brief error: {str(e)[:60]}"
        await send_all({"type": "zone_brief", "zone": zone_id, "text": brief})

    @api.websocket("/ws/ingest/{session_id}")
    async def ingest_ws(ws: WebSocket, session_id: str):
        await ws.accept()
        session = _sessions.get(session_id)

        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=10)
            msg = json.loads(raw)
        except Exception:
            await ws.send_json({"type": "error", "message": "Auth timeout"})
            await ws.close()
            return

        if msg.get("type") != "auth":
            await ws.send_json({"type": "error", "message": "Expected auth message"})
            await ws.close()
            return

        from .db import validate_api_key
        key_info = await validate_api_key(msg.get("api_key", ""))
        if not key_info:
            await ws.send_json({"type": "error", "message": "Invalid API key"})
            await ws.close()
            return

        if not session:
            from .db import get_session as db_get_session
            db_sess = await db_get_session(session_id)
            if not db_sess or db_sess["status"] != "active":
                await ws.send_json({"type": "error", "message": "Session not found"})
                await ws.close()
                return
            session = {
                "id": session_id,
                "api_key_id": db_sess.get("api_key_id", ""),
                "user_id": db_sess.get("user_id", ""),
                "mode": db_sess.get("mode", "general"),
                "unit_serial": db_sess.get("unit_serial"),
                "unit_model": db_sess.get("model"),
                "fleet_tag": db_sess.get("fleet_tag"),
                "location": db_sess.get("location"),
                "unit_context": None,
                "ingest_ws": None,
                "viewer_wss": [],
                "seen_zones": set(),
                "zone_findings": {},
                "sensor_snapshot": {},
                "latest_frame_b64": None,
                "latest_frame_id": -1,
                "latest_frame_client_ts": 0.0,
                "last_vlm_run_ts": 0.0,
                "vlm_busy": False,
                "last_vlm_zone": None,
                "yolo_busy": False,
                "pending_frame": None,
                "equipment_info": None,
                "equipment_id_done": False,
                "dynamic_zones": [],
                "analysis_history": {},
                "last_yolo_labels": set(),
                "insight_cooldowns": {},
            }
            _sessions[session_id] = session
            print(f"[SESSION] Recovered session {session_id} from database")

        await ws.send_json({"type": "auth_ok", "session_id": session_id})

        session["ingest_ws"] = ws

        try:
            await _run_session_pipeline(session, ws)
        finally:
            session["ingest_ws"] = None
            from .db import end_session
            try:
                await end_session(session_id, len(session["seen_zones"]), 0.0)
            except Exception as e:
                print(f"[DB] end_session error: {e}")
            _sessions.pop(session_id, None)

    @api.websocket("/ws/view/{session_id}")
    async def view_ws(ws: WebSocket, session_id: str):
        await ws.accept()
        session = _sessions.get(session_id)
        if not session:
            from .db import get_session as db_get_session
            db_sess = await db_get_session(session_id)
            if not db_sess or db_sess["status"] != "active":
                await ws.send_json({"type": "error", "message": "Session not found or ended"})
                await ws.close()
                return
            session = {
                "id": session_id,
                "api_key_id": db_sess.get("api_key_id", ""),
                "user_id": db_sess.get("user_id", ""),
                "mode": db_sess.get("mode", "general"),
                "unit_serial": db_sess.get("unit_serial"),
                "unit_model": db_sess.get("model"),
                "fleet_tag": db_sess.get("fleet_tag"),
                "location": db_sess.get("location"),
                "unit_context": None,
                "ingest_ws": None,
                "viewer_wss": [],
                "seen_zones": set(),
                "zone_findings": {},
                "sensor_snapshot": {},
                "latest_frame_b64": None,
                "latest_frame_id": -1,
                "latest_frame_client_ts": 0.0,
                "last_vlm_run_ts": 0.0,
                "vlm_busy": False,
                "last_vlm_zone": None,
                "yolo_busy": False,
                "pending_frame": None,
                "equipment_info": None,
                "equipment_id_done": False,
                "dynamic_zones": [],
                "analysis_history": {},
                "last_yolo_labels": set(),
                "insight_cooldowns": {},
            }
            _sessions[session_id] = session
            print(f"[SESSION] Viewer recovered session {session_id} from database")

        was_empty = len(session["viewer_wss"]) == 0
        session["viewer_wss"].append(ws)
        await ws.send_json({
            "type": "session_state",
            "session_id": session_id,
            "mode": session["mode"],
            "zones_seen": len(session["seen_zones"]),
            "active": session["ingest_ws"] is not None,
            "unit_serial": session.get("unit_serial"),
            "unit_model": session.get("unit_model"),
            "fleet_tag": session.get("fleet_tag"),
            "location": session.get("location"),
        })
        if session.get("equipment_info"):
            await ws.send_json({"type": "equipment_identified", "data": session["equipment_info"]})

        if was_empty and session.get("ingest_ws"):
            try:
                await session["ingest_ws"].send_json({
                    "type": "viewer_joined",
                    "viewers": len(session["viewer_wss"]),
                })
            except Exception:
                pass
            print(f"[SESSION {session_id}] First viewer joined — GPU inference enabled")

        try:
            while True:
                raw = await ws.receive_text()
                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "unit_context":
                    session["unit_context"] = msg.get("context", "")
                    print(f"[MEMORY] Viewer sent unit context: {str(session['unit_context'])[:100]}")

                if msg_type == "voice_question":
                    frame = session.get("latest_frame_b64") or ""
                    asyncio.create_task(
                        _handle_viewer_voice(session, msg.get("text", ""), frame, qwen)
                    )
                elif msg_type == "audio_question":
                    asyncio.create_task(
                        _handle_viewer_audio(session, msg.get("audio", ""), qwen)
                    )
                elif msg_type == "generate_report":
                    asyncio.create_task(
                        _handle_viewer_report(session, msg, qwen)
                    )
                elif msg_type == "set_mode":
                    requested_mode = str(msg.get("mode", "")).lower()
                    if requested_mode in ("general", "cat"):
                        session["mode"] = requested_mode
                    await _broadcast(session, {"type": "mode", "mode": session["mode"]})
                elif msg_type == "request_vlm_analysis":
                    frame = session.get("latest_frame_b64") or ""
                    if frame and not session.get("vlm_busy"):
                        asyncio.create_task(
                            _handle_viewer_voice(session, "Describe what you see in detail.", frame, qwen)
                        )
                elif msg_type == "request_zone_brief":
                    asyncio.create_task(_run_zone_brief_session(
                        session, msg, lambda m: _send_to_all(session, m), qwen,
                    ))
                elif msg_type == "end_session":
                    asyncio.create_task(
                        _handle_end_session(session, qwen)
                    )

        except WebSocketDisconnect:
            pass
        finally:
            if ws in session.get("viewer_wss", []):
                session["viewer_wss"].remove(ws)

    async def _send_to_all(session, msg):
        """Send a message to the ingest SDK and all viewers."""
        ingest = session.get("ingest_ws")
        if ingest:
            try:
                await ingest.send_json(msg)
            except Exception:
                pass
        await _broadcast(session, msg)

    async def _handle_viewer_audio(session, audio_b64, qwen_ref):
        """Transcribe + answer in a single GPU call (avoids double Modal RPC)."""
        if not audio_b64:
            return
        try:
            audio_bytes = base64.b64decode(audio_b64)
            frame_b64 = session.get("latest_frame_b64") or ""
            context = "You are inspecting a CAT 797F mining haul truck." if session["mode"] == "cat" else "You are a visual copilot."
            result = await asyncio.wait_for(
                asyncio.to_thread(qwen_ref.voice_answer.remote, audio_bytes, frame_b64, context),
                timeout=30,
            )
        except asyncio.TimeoutError:
            await _send_to_all(session, {
                "type": "voice_answer",
                "text": "Still loading, try again in a moment.",
                "mode": session["mode"],
            })
            return
        except Exception as e:
            print(f"[VOICE] Error: {e}")
            await _send_to_all(session, {
                "type": "voice_answer",
                "text": "Could not process audio.",
                "mode": session["mode"],
            })
            return

        transcript = result.get("transcript", "")
        answer = result.get("answer", "")

        if not transcript:
            await _send_to_all(session, {
                "type": "voice_answer",
                "text": "Didn't catch that — could you repeat?",
                "mode": session["mode"],
            })
            return

        await _send_to_all(session, {"type": "transcript", "text": transcript})
        await _send_to_all(session, {"type": "voice_answer", "text": answer, "mode": session["mode"]})

    async def _handle_viewer_voice(session, question, frame_b64, qwen_ref):
        """Handle text voice question from a viewer."""
        if not frame_b64:
            await _send_to_all(session, {
                "type": "voice_answer",
                "text": "No camera frame available yet — waiting for drone feed.",
                "mode": session["mode"],
            })
            return
        try:
            context = "You are inspecting a CAT 797F mining haul truck." if session["mode"] == "cat" else "You are a visual copilot."
            prompt = (
                f'{context} The operator asks: "{question}"\n'
                "Answer based on what you see in the image. "
                "Keep each sentence short and direct. "
                "If it's a yes/no question, state yes or no first, then briefly explain why. "
                "For all other questions, give a specific and detailed answer with concrete observations — never be vague."
            )
            answer = await asyncio.wait_for(
                asyncio.to_thread(qwen_ref.generate.remote, prompt, frame_b64), timeout=30,
            )
        except asyncio.TimeoutError:
            answer = "Still loading, try again in a moment."
        except Exception:
            answer = "Could not process question."
        await _send_to_all(session, {"type": "voice_answer", "text": answer, "mode": session["mode"]})

    async def _handle_end_session(session, qwen_ref):
        """End the inspection session from the dashboard."""
        session_id = session["id"]
        zones_seen = len(session["seen_zones"])
        total_zones = len(session.get("dynamic_zones", [])) or 15
        coverage_pct = round((zones_seen / total_zones) * 100, 1) if total_zones > 0 else 0
        findings_count = sum(len(v) if isinstance(v, list) else 1 for v in session.get("zone_findings", {}).values())

        summary = {
            "session_id": session_id,
            "zones_inspected": zones_seen,
            "total_zones": total_zones,
            "coverage_pct": coverage_pct,
            "findings_count": findings_count,
            "mode": session["mode"],
        }

        await _send_to_all(session, {"type": "session_ended", "data": summary})

        ingest = session.get("ingest_ws")
        if ingest:
            try:
                await ingest.send_json({"type": "session_ended", "data": summary})
                await ingest.close()
            except Exception:
                pass

        from .db import end_session
        try:
            await end_session(session_id, zones_seen, coverage_pct)
        except Exception as e:
            print(f"[DB] end_session error: {e}")

        for vws in list(session.get("viewer_wss", [])):
            try:
                await vws.close()
            except Exception:
                pass

        _sessions.pop(session_id, None)
        print(f"[SESSION] {session_id} ended by operator — {zones_seen} zones, {findings_count} findings")

    async def _handle_viewer_report(session, msg, qwen_ref):
        """Handle report generation from a viewer."""
        try:
            from backend.prompts import REPORT_PROMPT
            now = datetime.utcnow()
            all_findings = [f for fs in session["zone_findings"].values() for f in (fs if isinstance(fs, list) else [fs])]
            prompt = REPORT_PROMPT.format(
                model=msg.get("model", session.get("model") or "Unknown"),
                serial=msg.get("serial", session.get("unit_serial") or ""),
                hours=msg.get("hours", 0), technician=msg.get("technician", ""),
                duration_minutes=msg.get("duration_minutes", 0),
                coverage_percent=msg.get("coverage_percent", 0),
                findings_json=json.dumps(all_findings, indent=2),
                date_compact=now.strftime("%Y%m%d"), timestamp=now.isoformat() + "Z",
            )
            report = await asyncio.wait_for(
                asyncio.to_thread(qwen_ref.generate_report.remote, prompt), timeout=120,
            )
        except asyncio.TimeoutError:
            report = "Report generation timed out."
        except Exception as e:
            report = f"Report error: {str(e)[:60]}"
        if isinstance(report, str):
            start = report.find("{")
            end = report.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    report = json.loads(report[start:end])
                except json.JSONDecodeError:
                    pass
        await _send_to_all(session, {"type": "report", "data": report})
        from .db import save_report
        try:
            await save_report(session["id"], report)
        except Exception as e:
            print(f"[DB] save_report error: {e}")

    @api.get("/health")
    async def health():
        return {"status": "ok", "service": "dronecat", "sessions": len(_sessions)}

    return api
