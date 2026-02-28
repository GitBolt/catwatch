import asyncio
import base64
import json
import time
import traceback
from datetime import datetime

import modal

from . import app, web_image
from .yolo_detector import YoloDetector
from .whisper import WhisperTranscriber
from .qwen_vl import Qwen25VLInspector
from .siglip2 import SigLIP2PartsIdentifier


@app.function(image=web_image, min_containers=1, scaledown_window=600)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect

    api = FastAPI()

    yolo = YoloDetector()
    whisper = WhisperTranscriber()
    qwen = Qwen25VLInspector()
    siglip2 = SigLIP2PartsIdentifier()

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
        vlm_min_interval_s = 1.0
        vlm_busy = False
        inspection_mode = "general"

        async def run_vlm_analysis(frame_b64, frame_id, frame_client_ts):
            nonlocal vlm_busy, last_vlm_run_ts
            if vlm_busy:
                return
            vlm_busy = True
            last_vlm_run_ts = time.monotonic()
            print(f"[VLM] Starting analysis for frame {frame_id}")
            try:
                from backend.prompts import (
                    CAT_INSPECTION_PERSONA,
                    GENERAL_OUTPUT_SCHEMA,
                    GENERAL_SCENE_PERSONA,
                    VLM_OUTPUT_SCHEMA,
                )
                persona = CAT_INSPECTION_PERSONA if inspection_mode == "cat" else GENERAL_SCENE_PERSONA
                schema = VLM_OUTPUT_SCHEMA if inspection_mode == "cat" else GENERAL_OUTPUT_SCHEMA
                analysis = await asyncio.wait_for(
                    asyncio.to_thread(
                        qwen.analyze_frame.remote,
                        frame_b64,
                        persona,
                        schema,
                    ),
                    timeout=120,
                )
                if not isinstance(analysis, dict):
                    analysis = {"description": str(analysis), "severity": "GREEN", "findings": [], "callout": "", "confidence": 0.5, "zone": None}
                print(f"[VLM] Analysis done for frame {frame_id}: {analysis.get('description', '')[:80]}")
                await ws.send_json({
                    "type": "analysis",
                    "data": analysis,
                    "mode": inspection_mode,
                    "frame_id": frame_id,
                    "client_ts": frame_client_ts,
                    "server_ts": time.time(),
                })
            except asyncio.TimeoutError:
                print(f"[VLM] Timeout for frame {frame_id}")
                await ws.send_json({
                    "type": "analysis",
                    "data": {"description": "VLM warming up, please wait...", "severity": "GREEN", "findings": [], "callout": "VLM loading", "confidence": 0.0, "zone": None},
                    "mode": inspection_mode,
                    "frame_id": frame_id,
                    "client_ts": frame_client_ts,
                    "server_ts": time.time(),
                })
            except Exception as e:
                print(f"[VLM] Error for frame {frame_id}: {e}")
                traceback.print_exc()
                try:
                    await ws.send_json({
                        "type": "analysis",
                        "data": {"description": f"VLM error: {str(e)[:80]}", "severity": "GREEN", "findings": [], "callout": "", "confidence": 0.0, "zone": None},
                        "mode": inspection_mode,
                        "frame_id": frame_id,
                        "client_ts": frame_client_ts,
                        "server_ts": time.time(),
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
                    zone=zone_id,
                    hours=hours,
                    sub_section_title=sub_title,
                    unit_history="No prior history available",
                    fleet_stats="No fleet data available",
                    spec_knowledge=spec_knowledge,
                    audio_score=audio_data.get("anomaly_score", 0),
                    ir_score=ir_data.get("anomaly_score", 0),
                    light_quality=light_data.get("quality", "unknown"),
                )
                brief = await asyncio.wait_for(
                    asyncio.to_thread(qwen.zone_brief.remote, prompt),
                    timeout=60,
                )
            except asyncio.TimeoutError:
                brief = "Zone brief timed out — VLM may still be warming up."
            except Exception as e:
                print(f"[BRIEF] Error for {zone_id}: {e}")
                brief = f"Brief error: {str(e)[:60]}"
            print(f"[BRIEF] Done for {zone_id}")
            await ws.send_json({
                "type": "zone_brief",
                "zone": zone_id,
                "text": brief,
            })

        async def run_spec_assessment(zone_id, tech_rating, tech_description, spec_knowledge, frame_b64):
            print(f"[SPEC] Starting spec assessment for {zone_id}")
            try:
                from backend.prompts import SPEC_PROMPT, get_sub_section_prompt
                from backend.zone_config import ZONE_PROMPT_MAP
                prompt_key = ZONE_PROMPT_MAP.get(zone_id, "")
                sub_prompt = get_sub_section_prompt(prompt_key)
                prompt = SPEC_PROMPT.format(
                    zone=zone_id,
                    tech_rating=tech_rating,
                    tech_description=tech_description,
                    spec_knowledge=spec_knowledge,
                    sub_section_prompt=sub_prompt[:500],
                )
                result = await asyncio.wait_for(
                    asyncio.to_thread(qwen.spec_assessment.remote, prompt, frame_b64),
                    timeout=60,
                )
            except asyncio.TimeoutError:
                result = "Spec assessment timed out — VLM may still be warming up."
            except Exception as e:
                print(f"[SPEC] Error for {zone_id}: {e}")
                result = f"Spec error: {str(e)[:60]}"
            print(f"[SPEC] Done for {zone_id}")
            await ws.send_json({
                "type": "spec_assessment",
                "zone": zone_id,
                "result": result,
            })

        async def run_report(msg):
            print("[REPORT] Starting report generation")
            try:
                from backend.prompts import REPORT_PROMPT
                now = datetime.utcnow()
                prompt = REPORT_PROMPT.format(
                    model=msg.get("model", "CAT 325"),
                    serial=msg.get("serial", ""),
                    hours=msg.get("hours", 0),
                    technician=msg.get("technician", ""),
                    duration_minutes=msg.get("duration_minutes", 0),
                    coverage_percent=msg.get("coverage_percent", 0),
                    findings_json=json.dumps(list(zone_findings.values()), indent=2),
                    work_order_json=msg.get("work_order_json", "[]"),
                    date_compact=now.strftime("%Y%m%d"),
                    timestamp=now.isoformat() + "Z",
                )
                report = await asyncio.wait_for(
                    asyncio.to_thread(qwen.generate_report.remote, prompt),
                    timeout=120,
                )
            except asyncio.TimeoutError:
                report = "Report generation timed out — VLM may still be warming up. Try again in a moment."
            except Exception as e:
                print(f"[REPORT] Error: {e}")
                report = f"Report error: {str(e)[:60]}"
            print(f"[REPORT] Done ({len(str(report))} chars)")
            await ws.send_json({
                "type": "report",
                "data": report,
            })

        async def run_voice_answer(question, frame_b64):
            print(f"[VOICE Q] {question[:60]}")
            try:
                if inspection_mode == "cat":
                    context = "You are inspecting a CAT 325 excavator."
                else:
                    context = "You are a visual copilot for general scene and safety monitoring."
                prompt = (
                    f"{context} The technician asks: \"{question}\""
                    "\nAnswer in one concise sentence based on the image."
                    " Be specific and avoid repeating the question."
                )
                answer = await asyncio.wait_for(
                    asyncio.to_thread(qwen.generate.remote, prompt, frame_b64),
                    timeout=30,
                )
            except asyncio.TimeoutError:
                answer = "Still loading, try again in a moment."
            except Exception as e:
                print(f"[VOICE Q] Error: {e}")
                answer = "Could not process question."
            print(f"[VOICE A] {answer[:80]}")
            await ws.send_json({
                "type": "voice_answer",
                "text": answer,
                "mode": inspection_mode,
            })

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

                now_mono = time.monotonic()
                if (
                    not vlm_busy
                    and latest_frame_b64
                    and (now_mono - last_vlm_run_ts) >= vlm_min_interval_s
                ):
                    asyncio.create_task(
                        run_vlm_analysis(latest_frame_b64, latest_frame_id, latest_frame_client_ts)
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

                elif msg_type == "audio":
                    pass

                elif msg_type == "sensor":
                    sensor_snapshot = msg.get("data", {})

                elif msg_type == "request_zone_brief":
                    asyncio.create_task(run_zone_brief(
                        msg["zone"],
                        msg.get("hours", 0),
                        msg.get("spec_knowledge", ""),
                    ))

                elif msg_type == "request_spec_assessment":
                    asyncio.create_task(run_spec_assessment(
                        msg["zone"],
                        msg["rating"],
                        msg["description"],
                        msg.get("spec_knowledge", ""),
                        msg.get("frame", ""),
                    ))

                elif msg_type == "identify_part":
                    frame_b64 = msg["data"]
                    parts = await asyncio.to_thread(siglip2.identify_part.remote, frame_b64)
                    await ws.send_json({
                        "type": "parts_result",
                        "parts": parts,
                    })

                elif msg_type == "generate_report":
                    asyncio.create_task(run_report(msg))

                elif msg_type == "voice_question":
                    asyncio.create_task(run_voice_answer(
                        msg.get("text", ""),
                        msg.get("frame", ""),
                    ))

                elif msg_type == "request_vlm_analysis":
                    if latest_frame_b64 and not vlm_busy:
                        asyncio.create_task(
                            run_vlm_analysis(latest_frame_b64, latest_frame_id, latest_frame_client_ts)
                        )

                elif msg_type == "set_mode":
                    requested_mode = str(msg.get("mode", "")).lower()
                    if requested_mode in ("general", "cat"):
                        inspection_mode = requested_mode
                    await ws.send_json({"type": "mode", "mode": inspection_mode})

        except WebSocketDisconnect:
            pass

    @api.get("/health")
    async def health():
        return {"status": "ok", "service": "dronecat"}

    return api
