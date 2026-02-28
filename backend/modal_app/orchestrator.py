import asyncio
import json
import os
import secrets
import time
import traceback
from datetime import datetime

import modal

from . import app, web_image
from .yolo_detector import YoloDetector
from .qwen_vl import Qwen25VLInspector

# ── VLM-first config ──────────────────────────────────────────────────────

VLM_ANALYSIS_INTERVAL_S = 3.0   # run Qwen every 3s when equipment is in frame

# ── Live session registry (in-memory, ephemeral) ──────────────────────────

_sessions = {}   # session_id → session dict


@app.function(
    image=web_image,
    min_containers=1,
    scaledown_window=600,
    secrets=[modal.Secret.from_name("catwatch-db")],
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
    qwen = Qwen25VLInspector()

    # ══════════════════════════════════════════════════════════════════════
    #  LEGACY DEV ENDPOINT — /ws (unchanged)
    # ══════════════════════════════════════════════════════════════════════

    @api.websocket("/ws")
    async def inspection_ws(ws: WebSocket):
        await ws.accept()

        # ── Session state ──────────────────────────────────────────────────
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

        # ── VLM analysis (primary inspector) ──────────────────────────────

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
                    analysis = {"description": str(analysis), "severity": "GREEN", "findings": [], "callout": "", "confidence": 0.5, "zone": None}
                analysis["triggered_by"] = triggered_by

                new_zone = analysis.get("zone")
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
                        "data": {"description": "VLM warming up, please wait...", "severity": "GREEN", "findings": [], "callout": "VLM loading", "confidence": 0.0, "zone": None},
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
                        "data": {"description": f"VLM error: {str(e)[:80]}", "severity": "GREEN", "findings": [], "callout": "", "confidence": 0.0, "zone": None},
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
                prompt = REPORT_PROMPT.format(
                    model=msg.get("model", "CAT 325"), serial=msg.get("serial", ""),
                    hours=msg.get("hours", 0), technician=msg.get("technician", ""),
                    duration_minutes=msg.get("duration_minutes", 0),
                    coverage_percent=msg.get("coverage_percent", 0),
                    findings_json=json.dumps(list(zone_findings.values()), indent=2),
                    work_order_json=msg.get("work_order_json", "[]"),
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
            print(f"[REPORT] Done ({len(str(report))} chars)")
            await ws.send_json({"type": "report", "data": report})

        async def run_voice_answer(question, frame_b64):
            print(f"[VOICE Q] {question[:60]}")
            try:
                context = "You are inspecting a CAT 325 excavator." if inspection_mode == "cat" else "You are a visual copilot for general scene and safety monitoring."
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

        # ── YOLO + VLM-first pipeline ─────────────────────────────────────

        yolo_busy = False
        pending_frame = None

        async def process_yolo(frame_b64, frame_id, frame_client_ts):
            nonlocal yolo_busy, pending_frame

            yolo_busy = True
            try:
                result = await asyncio.to_thread(yolo.detect.remote, frame_b64)
                detections = result.get("detections", [])
                yolo_ms = result.get("yolo_ms", 0)

                from backend.zone_config import zone_from_label, zone_from_bbox
                zone_events = []
                for det in detections:
                    zone_id = zone_from_label(det["label"])
                    if not zone_id:
                        zone_id = zone_from_bbox(det["bbox"])
                    det["zone"] = zone_id
                    if zone_id and zone_id not in seen_zones:
                        seen_zones.add(zone_id)
                        zone_events.append(zone_id)

                await ws.send_json({
                    "type": "detection",
                    "detections": detections,
                    "coverage": len(seen_zones),
                    "total_zones": 15,
                    "mode": inspection_mode,
                    "yolo_ms": yolo_ms,
                    "frame_id": frame_id,
                    "client_ts": frame_client_ts,
                    "server_ts": time.time(),
                })
                for zone_id in zone_events:
                    await ws.send_json({"type": "zone_first_seen", "zone": zone_id})

                # ── VLM analysis trigger (equipment-in-frame gate) ────────
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

        # ── WebSocket message loop ─────────────────────────────────────────

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
                    if incoming_mode in ("general", "cat"):
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
                    if requested_mode in ("general", "cat"):
                        inspection_mode = requested_mode
                    await ws.send_json({"type": "mode", "mode": inspection_mode})

        except WebSocketDisconnect:
            pass

    # ══════════════════════════════════════════════════════════════════════
    #  PLATFORM ENDPOINTS — REST + WebSocket
    # ══════════════════════════════════════════════════════════════════════

    # ── REST: Create session ──────────────────────────────────────────────

    @api.post("/api/sessions")
    async def create_session(request: Request):
        from .db import validate_api_key, create_session as db_create_session

        body = await request.json()
        api_key = body.get("api_key", "")
        mode = body.get("mode", "general")
        unit_serial = body.get("unit_serial")
        unit_model = body.get("model")
        fleet_tag = body.get("fleet_tag")

        if not api_key:
            return JSONResponse({"error": "api_key required"}, status_code=400)

        key_info = await validate_api_key(api_key)
        if not key_info:
            return JSONResponse({"error": "Invalid API key"}, status_code=401)

        session_id = secrets.token_hex(6)  # 12-char hex like "a1b2c3d4e5f6"

        await db_create_session(
            session_id, key_info["api_key_id"], key_info["user_id"], mode,
            unit_serial=unit_serial, model=unit_model, fleet_tag=fleet_tag,
        )

        # Initialize in-memory session state
        _sessions[session_id] = {
            "id": session_id,
            "api_key_id": key_info["api_key_id"],
            "user_id": key_info["user_id"],
            "mode": mode,
            "unit_serial": unit_serial,
            "unit_model": unit_model,
            "fleet_tag": fleet_tag,
            "unit_context": None,   # populated by frontend via Supermemory
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

    # ── Broadcast helper ──────────────────────────────────────────────────

    async def _broadcast(session, msg):
        """Send a message to the ingest SDK and all viewer WebSockets."""
        dead = []
        for i, viewer_ws in enumerate(session["viewer_wss"]):
            try:
                await viewer_ws.send_json(msg)
            except Exception:
                dead.append(i)
        for i in reversed(dead):
            session["viewer_wss"].pop(i)

    # ── Session pipeline (parameterized by session dict) ──────────────────

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
                    session["last_vlm_zone"], mode=session["mode"]
                )
                # Inject unit memory context from Supermemory (sent by frontend)
                unit_ctx = session.get("unit_context")
                if unit_ctx:
                    persona = f"{persona}\n\n--- Unit Memory ---\n{unit_ctx}"
                analysis = await asyncio.wait_for(
                    asyncio.to_thread(qwen.analyze_frame.remote, frame_b64, persona, schema),
                    timeout=120,
                )
                if not isinstance(analysis, dict):
                    analysis = {"description": str(analysis), "severity": "GREEN", "findings": [], "callout": "", "confidence": 0.5, "zone": None}
                analysis["triggered_by"] = triggered_by
                new_zone = analysis.get("zone")
                if new_zone:
                    session["last_vlm_zone"] = new_zone

                msg = {
                    "type": "analysis", "data": analysis,
                    "mode": session["mode"], "frame_id": frame_id,
                    "client_ts": frame_client_ts, "server_ts": time.time(),
                }
                await send_all(msg)

                # Persist findings from VLM analysis
                from .db import save_finding
                for f in analysis.get("findings", []):
                    if isinstance(f, str) and f.strip():
                        zone = analysis.get("zone") or "unknown"
                        severity = analysis.get("severity", "GREEN")
                        try:
                            await save_finding(session["id"], zone, severity, f)
                        except Exception as e:
                            print(f"[DB] save_finding error: {e}")

            except asyncio.TimeoutError:
                try:
                    await send_all({
                        "type": "analysis",
                        "data": {"description": "VLM warming up...", "severity": "GREEN", "findings": [], "callout": "VLM loading", "confidence": 0.0, "zone": None},
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
                prompt = REPORT_PROMPT.format(
                    model=msg.get("model", "CAT 325"), serial=msg.get("serial", ""),
                    hours=msg.get("hours", 0), technician=msg.get("technician", ""),
                    duration_minutes=msg.get("duration_minutes", 0),
                    coverage_percent=msg.get("coverage_percent", 0),
                    findings_json=json.dumps(list(session["zone_findings"].values()), indent=2),
                    work_order_json=msg.get("work_order_json", "[]"),
                    date_compact=now.strftime("%Y%m%d"), timestamp=now.isoformat() + "Z",
                )
                report = await asyncio.wait_for(
                    asyncio.to_thread(qwen.generate_report.remote, prompt), timeout=120,
                )
            except asyncio.TimeoutError:
                report = "Report generation timed out."
            except Exception as e:
                report = f"Report error: {str(e)[:60]}"
            await send_all({"type": "report", "data": report})
            # Persist report
            from .db import save_report
            try:
                await save_report(session["id"], report)
            except Exception as e:
                print(f"[DB] save_report error: {e}")

        async def run_voice_session(question, frame_b64):
            try:
                context = "You are inspecting a CAT 325 excavator." if session["mode"] == "cat" else "You are a visual copilot for general scene and safety monitoring."
                prompt = f'{context} The technician asks: "{question}"\nAnswer in one concise sentence based on the image. Be specific and avoid repeating the question.'
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
                result = await asyncio.to_thread(yolo.detect.remote, frame_b64)
                detections = result.get("detections", [])
                yolo_ms = result.get("yolo_ms", 0)

                from backend.zone_config import zone_from_label, zone_from_bbox
                zone_events = []
                for det in detections:
                    zone_id = zone_from_label(det["label"])
                    if not zone_id:
                        zone_id = zone_from_bbox(det["bbox"])
                    det["zone"] = zone_id
                    if zone_id and zone_id not in session["seen_zones"]:
                        session["seen_zones"].add(zone_id)
                        zone_events.append(zone_id)

                det_msg = {
                    "type": "detection", "detections": detections,
                    "coverage": len(session["seen_zones"]), "total_zones": 15,
                    "mode": session["mode"], "yolo_ms": yolo_ms,
                    "frame_id": frame_id, "client_ts": frame_client_ts,
                    "server_ts": time.time(),
                }
                await send_all(det_msg)
                for zid in zone_events:
                    await send_all({"type": "zone_first_seen", "zone": zid})

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

        # ── Message loop ────────────────────────────────────────────────
        try:
            while True:
                raw = await ingest_ws.receive_text()
                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "frame":
                    frame_b64 = msg["data"]
                    frame_id = int(msg.get("frame_id", 0))
                    frame_client_ts = float(msg.get("client_ts", 0))
                    incoming_mode = str(msg.get("mode", "")).lower()
                    if incoming_mode in ("general", "cat"):
                        session["mode"] = incoming_mode
                    session["latest_frame_b64"] = frame_b64
                    session["latest_frame_id"] = frame_id
                    session["latest_frame_client_ts"] = frame_client_ts

                    # Relay frame to viewers
                    await _broadcast(session, {
                        "type": "frame", "data": frame_b64,
                        "frame_id": frame_id,
                    })

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
                    if requested_mode in ("general", "cat"):
                        session["mode"] = requested_mode
                    await send_all({"type": "mode", "mode": session["mode"]})

                elif msg_type == "unit_context":
                    # Frontend sends compiled unit history from Supermemory
                    session["unit_context"] = msg.get("context", "")
                    print(f"[MEMORY] Received unit context for session {session['id']}: {str(session['unit_context'])[:100]}")

                elif msg_type == "request_zone_brief":
                    asyncio.create_task(_run_zone_brief_session(
                        session, msg, send_all, qwen,
                    ))

        except WebSocketDisconnect:
            pass

    async def _run_zone_brief_session(session, msg, send_all, qwen_ref):
        """Run zone brief for a platform session, using Supermemory context if available."""
        zone_id = msg["zone"]
        hours = msg.get("hours", 0)
        spec_knowledge = msg.get("spec_knowledge", "")
        # Frontend can pass enriched history from Supermemory
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

    # ── WebSocket: SDK ingest ─────────────────────────────────────────────

    @api.websocket("/ws/ingest/{session_id}")
    async def ingest_ws(ws: WebSocket, session_id: str):
        await ws.accept()
        session = _sessions.get(session_id)

        # Auth handshake: first message must be {"type": "auth", "api_key": "..."}
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
            await ws.send_json({"type": "error", "message": "Session not found"})
            await ws.close()
            return

        await ws.send_json({"type": "auth_ok", "session_id": session_id})

        session["ingest_ws"] = ws

        try:
            await _run_session_pipeline(session, ws)
        finally:
            session["ingest_ws"] = None
            # End session in DB
            from .db import end_session
            try:
                await end_session(session_id, len(session["seen_zones"]), 0.0)
            except Exception as e:
                print(f"[DB] end_session error: {e}")
            _sessions.pop(session_id, None)

    # ── WebSocket: Dashboard viewer ───────────────────────────────────────

    @api.websocket("/ws/view/{session_id}")
    async def view_ws(ws: WebSocket, session_id: str):
        await ws.accept()
        session = _sessions.get(session_id)
        if not session:
            await ws.send_json({"type": "error", "message": "Session not found or ended"})
            await ws.close()
            return

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
        })

        try:
            while True:
                raw = await ws.receive_text()
                msg = json.loads(raw)
                msg_type = msg.get("type")

                # Accept unit_context from frontend (Supermemory profile)
                if msg_type == "unit_context":
                    session["unit_context"] = msg.get("context", "")
                    print(f"[MEMORY] Viewer sent unit context: {str(session['unit_context'])[:100]}")

                # Forward viewer actions to the pipeline
                if msg_type in ("voice_question", "generate_report", "set_mode", "request_vlm_analysis", "request_zone_brief"):
                    ingest = session.get("ingest_ws")
                    if ingest:
                        # Inject into pipeline by processing directly
                        if msg_type == "voice_question":
                            frame = session.get("latest_frame_b64", "")
                            asyncio.create_task(
                                _handle_viewer_voice(session, msg.get("text", ""), frame, qwen)
                            )
                        elif msg_type == "set_mode":
                            requested_mode = str(msg.get("mode", "")).lower()
                            if requested_mode in ("general", "cat"):
                                session["mode"] = requested_mode
                            await _broadcast(session, {"type": "mode", "mode": session["mode"]})
                        elif msg_type == "request_zone_brief":
                            async def _viewer_send_all(m):
                                try:
                                    await ingest.send_json(m)
                                except Exception:
                                    pass
                                await _broadcast(session, m)
                            asyncio.create_task(_run_zone_brief_session(
                                session, msg, _viewer_send_all, qwen,
                            ))

        except WebSocketDisconnect:
            pass
        finally:
            if ws in session.get("viewer_wss", []):
                session["viewer_wss"].remove(ws)

    async def _handle_viewer_voice(session, question, frame_b64, qwen_ref):
        """Handle voice question from a viewer."""
        try:
            context = "You are inspecting a CAT 325 excavator." if session["mode"] == "cat" else "You are a visual copilot."
            prompt = f'{context} The operator asks: "{question}"\nAnswer concisely.'
            answer = await asyncio.wait_for(
                asyncio.to_thread(qwen_ref.generate.remote, prompt, frame_b64), timeout=30,
            )
        except Exception:
            answer = "Could not process question."
        msg = {"type": "voice_answer", "text": answer, "mode": session["mode"]}
        # Send to SDK + all viewers
        ingest = session.get("ingest_ws")
        if ingest:
            try:
                await ingest.send_json(msg)
            except Exception:
                pass
        await _broadcast(session, msg)

    # ── Health ────────────────────────────────────────────────────────────

    @api.get("/health")
    async def health():
        return {"status": "ok", "service": "dronecat", "sessions": len(_sessions)}

    return api
