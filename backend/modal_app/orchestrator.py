import base64
import json
from datetime import datetime

import modal

from . import app, web_image
from .florence2 import Florence2Processor
from .whisper import WhisperTranscriber
from .qwen_vl import Qwen25VLInspector
from .siglip2 import SigLIP2PartsIdentifier


@app.function(image=web_image, keep_warm=1, container_idle_timeout=600)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect

    api = FastAPI()

    florence2 = Florence2Processor()
    whisper = WhisperTranscriber()
    qwen = Qwen25VLInspector()
    siglip2 = SigLIP2PartsIdentifier()

    @api.websocket("/ws")
    async def inspection_ws(ws: WebSocket):
        await ws.accept()

        seen_zones = set()
        zone_findings = {}
        sensor_snapshot = {}

        try:
            while True:
                raw = await ws.receive_text()
                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "frame":
                    frame_b64 = msg["data"]
                    detections = florence2.process_frame.remote(frame_b64)

                    from backend.zone_config import zone_from_bbox

                    zone_events = []
                    for det in detections:
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
                    })

                    for zone_id in zone_events:
                        await ws.send_json({
                            "type": "zone_first_seen",
                            "zone": zone_id,
                        })

                elif msg_type == "audio":
                    audio_b64 = msg["data"]
                    audio_bytes = base64.b64decode(audio_b64)
                    transcript = whisper.transcribe.remote(audio_bytes)

                    await ws.send_json({
                        "type": "transcript",
                        "text": transcript,
                    })

                    from backend.nlp import extract_finding
                    finding = extract_finding(transcript)

                    if finding["zone"]:
                        zone_findings[finding["zone"]] = finding
                        await ws.send_json({
                            "type": "finding",
                            "data": finding,
                        })

                elif msg_type == "sensor":
                    sensor_snapshot = msg.get("data", {})

                elif msg_type == "request_zone_brief":
                    zone_id = msg["zone"]
                    hours = msg.get("hours", 0)
                    unit_history = msg.get("unit_history", "No prior history available")
                    fleet_stats = msg.get("fleet_stats", "No fleet data available")
                    spec_knowledge = msg.get("spec_knowledge", "")

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
                        unit_history=unit_history,
                        fleet_stats=fleet_stats,
                        spec_knowledge=spec_knowledge,
                        audio_score=audio_data.get("anomaly_score", 0),
                        ir_score=ir_data.get("anomaly_score", 0),
                        light_quality=light_data.get("quality", "unknown"),
                    )

                    brief = qwen.zone_brief.remote(prompt)
                    await ws.send_json({
                        "type": "zone_brief",
                        "zone": zone_id,
                        "text": brief,
                    })

                elif msg_type == "request_spec_assessment":
                    zone_id = msg["zone"]
                    tech_rating = msg["rating"]
                    tech_description = msg["description"]
                    spec_knowledge = msg.get("spec_knowledge", "")
                    frame_b64 = msg.get("frame", "")

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

                    result = qwen.spec_assessment.remote(prompt, frame_b64)
                    await ws.send_json({
                        "type": "spec_assessment",
                        "zone": zone_id,
                        "result": result,
                    })

                elif msg_type == "identify_part":
                    frame_b64 = msg["data"]
                    parts = siglip2.identify_part.remote(frame_b64)
                    await ws.send_json({
                        "type": "parts_result",
                        "parts": parts,
                    })

                elif msg_type == "generate_report":
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

                    report = qwen.generate_report.remote(prompt)
                    await ws.send_json({
                        "type": "report",
                        "data": report,
                    })

        except WebSocketDisconnect:
            pass

    @api.get("/health")
    async def health():
        return {"status": "ok", "service": "dronecat"}

    return api
