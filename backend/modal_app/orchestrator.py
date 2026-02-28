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

# ── Tier 2 config ─────────────────────────────────────────────────────────

TRIAGE_THRESHOLD = 0.05          # anomaly_score above this → flagged
HOVER_FLAG_COOLDOWN_S = 5.0      # cadence fallback only fires this long after last T2 flag
VLM_FALLBACK_INTERVAL_S = 5.0   # slower cadence — used only as safety-net fallback
MAX_TIER3_QUEUE = 2              # max pending Tier 3 items


# ── Module-level helpers ───────────────────────────────────────────────────

def _extract_crop(frame_bytes, bbox, pad=0.175):
    """Crop a YOLO bbox from a JPEG frame, pad 17.5% on each side, resize to 384×384."""
    from PIL import Image
    import io

    img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
    w, h = img.size
    x1, y1, x2, y2 = bbox
    px1, py1, px2, py2 = x1 * w, y1 * h, x2 * w, y2 * h
    bw, bh = px2 - px1, py2 - py1
    px1 = max(0.0, px1 - bw * pad)
    py1 = max(0.0, py1 - bh * pad)
    px2 = min(float(w), px2 + bw * pad)
    py2 = min(float(h), py2 + bh * pad)
    crop = img.crop((int(px1), int(py1), int(px2), int(py2)))
    if crop.size[0] < 1 or crop.size[1] < 1:
        crop = img
    crop = crop.resize((384, 384), Image.BILINEAR)
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _iou(a, b):
    """IoU for two normalized [x1,y1,x2,y2] bboxes."""
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0.0 else 0.0


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

        # ── Session state ──────────────────────────────────────────────────
        seen_zones = set()
        zone_findings = {}
        sensor_snapshot = {}
        latest_frame_b64 = None
        latest_frame_id = -1
        latest_frame_client_ts = 0.0
        last_vlm_run_ts = 0.0
        vlm_min_interval_s = VLM_FALLBACK_INTERVAL_S
        vlm_busy = False
        inspection_mode = "general"
        last_tier2_flag_ts = 0.0
        tier3_queue = []   # list of pending Tier 3 work items

        # ── Tier 3 queue helpers ───────────────────────────────────────────

        def _enqueue_tier3(det_id, crop_b64, frame_b64, det, triage, frame_id, frame_client_ts):
            """Add a Tier 3 item, deduplicating by (label + IoU > 0.5)."""
            label = det["label"]
            bbox = det["bbox"]
            score = triage["anomaly_score"]

            for i, item in enumerate(tier3_queue):
                if item["label"] == label and _iou(item["bbox"], bbox) > 0.5:
                    if score > item["anomaly_score"]:
                        tier3_queue[i] = {
                            "det_id": det_id, "crop_b64": crop_b64,
                            "frame_b64": frame_b64, "det": det, "triage": triage,
                            "frame_id": frame_id, "frame_client_ts": frame_client_ts,
                            "label": label, "bbox": bbox, "anomaly_score": score,
                        }
                    return  # already queued (same component)

            if len(tier3_queue) >= MAX_TIER3_QUEUE:
                min_idx = min(range(len(tier3_queue)), key=lambda i: tier3_queue[i]["anomaly_score"])
                if tier3_queue[min_idx]["anomaly_score"] >= score:
                    return  # current item is worse than all queued items
                tier3_queue.pop(min_idx)

            tier3_queue.append({
                "det_id": det_id, "crop_b64": crop_b64,
                "frame_b64": frame_b64, "det": det, "triage": triage,
                "frame_id": frame_id, "frame_client_ts": frame_client_ts,
                "label": label, "bbox": bbox, "anomaly_score": score,
            })

        async def process_tier3_queue():
            if vlm_busy or not tier3_queue:
                return
            item = tier3_queue.pop(0)
            await run_tier3_analysis(item)

        # ── Tier 3: deep analysis triggered by Tier 2 flag ────────────────

        async def run_tier3_analysis(item):
            nonlocal vlm_busy, last_vlm_run_ts
            if vlm_busy:
                return
            vlm_busy = True
            last_vlm_run_ts = time.monotonic()

            det = item["det"]
            triage = item["triage"]
            frame_b64 = item["frame_b64"]
            frame_id = item["frame_id"]
            frame_client_ts = item["frame_client_ts"]
            top_anomaly = triage.get("top_anomaly_match", "anomaly")
            label = det.get("label", "component")

            print(f"[T3] Analyzing {label!r}: possible {top_anomaly!r} (score={triage.get('anomaly_score', 0):.3f})")
            try:
                from backend.prompts import (
                    CAT_INSPECTION_PERSONA, GENERAL_SCENE_PERSONA,
                    GENERAL_OUTPUT_SCHEMA, VLM_OUTPUT_SCHEMA, SMCS_CONTEXT,
                )
                tier2_note = (
                    f"\n\nTier 2 automated triage flagged a possible '{top_anomaly}' "
                    f"on '{label}' (anomaly score: {triage.get('anomaly_score', 0):.3f}). "
                    f"Focus your analysis specifically on this finding."
                )
                if inspection_mode == "cat":
                    persona = CAT_INSPECTION_PERSONA
                    schema = VLM_OUTPUT_SCHEMA + tier2_note + "\n\n" + SMCS_CONTEXT
                else:
                    persona = GENERAL_SCENE_PERSONA
                    schema = GENERAL_OUTPUT_SCHEMA + tier2_note

                analysis = await asyncio.wait_for(
                    asyncio.to_thread(qwen.analyze_frame.remote, frame_b64, persona, schema),
                    timeout=30,
                )
                if not isinstance(analysis, dict):
                    analysis = {"description": str(analysis), "severity": "GREEN", "findings": [], "callout": "", "confidence": 0.5, "zone": None}

                analysis["triggered_by"] = "tier2_flag"
                analysis["tier2_anomaly"] = top_anomaly
                print(f"[T3] Done {label!r}: [{analysis.get('severity','?')}] {analysis.get('callout','')[:60]}")
                await ws.send_json({
                    "type": "analysis",
                    "data": analysis,
                    "mode": inspection_mode,
                    "frame_id": frame_id,
                    "client_ts": frame_client_ts,
                    "server_ts": time.time(),
                })
            except asyncio.TimeoutError:
                print(f"[T3] Timeout for {label!r}")
                try:
                    await ws.send_json({
                        "type": "analysis",
                        "data": {"description": "Analysis timed out.", "severity": "GREEN", "findings": [],
                                 "callout": "", "confidence": 0.0, "zone": None, "triggered_by": "tier2_flag"},
                        "mode": inspection_mode, "frame_id": frame_id,
                        "client_ts": frame_client_ts, "server_ts": time.time(),
                    })
                except Exception:
                    pass
            except Exception as e:
                print(f"[T3] Error for {label!r}: {e}")
                traceback.print_exc()
            finally:
                vlm_busy = False
                if tier3_queue:
                    asyncio.create_task(process_tier3_queue())

        # ── Tier 3: cadence / manual / voice (same Qwen, different trigger) ──

        async def run_vlm_analysis(frame_b64, frame_id, frame_client_ts, triggered_by="cadence"):
            nonlocal vlm_busy, last_vlm_run_ts
            if vlm_busy:
                return
            vlm_busy = True
            last_vlm_run_ts = time.monotonic()
            print(f"[VLM] Starting analysis frame {frame_id} (trigger={triggered_by})")
            try:
                from backend.prompts import (
                    CAT_INSPECTION_PERSONA, GENERAL_OUTPUT_SCHEMA,
                    GENERAL_SCENE_PERSONA, VLM_OUTPUT_SCHEMA,
                )
                persona = CAT_INSPECTION_PERSONA if inspection_mode == "cat" else GENERAL_SCENE_PERSONA
                schema = VLM_OUTPUT_SCHEMA if inspection_mode == "cat" else GENERAL_OUTPUT_SCHEMA
                analysis = await asyncio.wait_for(
                    asyncio.to_thread(qwen.analyze_frame.remote, frame_b64, persona, schema),
                    timeout=120,
                )
                if not isinstance(analysis, dict):
                    analysis = {"description": str(analysis), "severity": "GREEN", "findings": [], "callout": "", "confidence": 0.5, "zone": None}
                analysis["triggered_by"] = triggered_by
                print(f"[VLM] Done frame {frame_id}: {analysis.get('description', '')[:80]}")
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
                if tier3_queue:
                    asyncio.create_task(process_tier3_queue())

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

        # ── YOLO + Tier 2 pipeline ─────────────────────────────────────────

        yolo_busy = False
        pending_frame = None

        async def process_yolo(frame_b64, frame_id, frame_client_ts):
            nonlocal yolo_busy, pending_frame, last_tier2_flag_ts

            yolo_busy = True
            try:
                # ── TIER 1: YOLO ──────────────────────────────────────────
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

                # ── TIER 2: SigLIP2 triage ────────────────────────────────
                if detections:
                    try:
                        frame_bytes = base64.b64decode(frame_b64)
                        crops_b64 = [_extract_crop(frame_bytes, det["bbox"]) for det in detections]
                        labels = [det["label"] for det in detections]

                        t2_start = time.monotonic()
                        triage_results = await asyncio.wait_for(
                            asyncio.to_thread(
                                siglip2.triage_crops.remote,
                                crops_b64,
                                labels,
                                TRIAGE_THRESHOLD,
                            ),
                            timeout=15.0,
                        )
                        t2_ms = round((time.monotonic() - t2_start) * 1000)

                        # Defensive length alignment
                        while len(triage_results) < len(detections):
                            triage_results.append({"anomaly_score": 0.0, "is_flagged": False, "top_anomaly_match": "", "top_normal_match": ""})

                        triage_items = []
                        any_flagged = False
                        for i, (det, triage) in enumerate(zip(detections, triage_results)):
                            det_id = f"{frame_id}_{i}"
                            triage_items.append({
                                "detection_id": det_id,
                                "label": det["label"],
                                "bbox": det["bbox"],
                                "anomaly_score": triage["anomaly_score"],
                                "is_flagged": triage["is_flagged"],
                                "top_anomaly_match": triage.get("top_anomaly_match", ""),
                            })
                            if triage["is_flagged"]:
                                any_flagged = True
                                last_tier2_flag_ts = time.monotonic()
                                await ws.send_json({
                                    "type": "anomaly_flag",
                                    "frame_id": frame_id,
                                    "detection_id": det_id,
                                    "label": det["label"],
                                    "bbox": det["bbox"],
                                    "anomaly_score": triage["anomaly_score"],
                                    "top_anomaly_match": triage.get("top_anomaly_match", ""),
                                    "mode": inspection_mode,
                                })
                                _enqueue_tier3(
                                    det_id, crops_b64[i],
                                    latest_frame_b64 or frame_b64,
                                    det, triage, frame_id, frame_client_ts,
                                )

                        await ws.send_json({
                            "type": "triage_summary",
                            "frame_id": frame_id,
                            "total_detections": len(detections),
                            "flagged_count": sum(1 for t in triage_results if t["is_flagged"]),
                            "results": triage_items,
                            "tier3_queued": bool(tier3_queue),
                            "t2_ms": t2_ms,
                            "mode": inspection_mode,
                        })

                        if any_flagged and tier3_queue and not vlm_busy:
                            asyncio.create_task(process_tier3_queue())

                    except asyncio.TimeoutError:
                        print(f"[T2] Timeout frame {frame_id} — SigLIP2 may be cold, falling back to cadence")
                    except Exception as e:
                        print(f"[T2] Error frame {frame_id}: {e}")

                # ── Tier 3 fallback cadence (only when quiet) ─────────────
                now_mono = time.monotonic()
                no_recent_flags = (now_mono - last_tier2_flag_ts) > HOVER_FLAG_COOLDOWN_S
                if (
                    not vlm_busy
                    and not tier3_queue
                    and latest_frame_b64
                    and no_recent_flags
                    and (now_mono - last_vlm_run_ts) >= vlm_min_interval_s
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

                elif msg_type == "audio":
                    pass

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

                elif msg_type == "identify_part":
                    frame_b64 = msg["data"]
                    parts = await asyncio.to_thread(siglip2.identify_part.remote, frame_b64)
                    await ws.send_json({"type": "parts_result", "parts": parts})

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

    @api.get("/health")
    async def health():
        return {"status": "ok", "service": "dronecat"}

    return api
