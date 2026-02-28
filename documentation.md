# Dronecat Documentation

## 1) What this project is

Dronecat is a voice-first, real-time inspection copilot for camera streams (webcam now, drone camera later).

It combines:

- Fast visual detection (YOLO on Modal)
- Multimodal reasoning (Qwen2-VL on Modal)
- Local speech-to-text (`faster-whisper`)
- Local text-to-speech (macOS `say`)
- A low-latency WebSocket orchestrator
- Session evidence + JSON/PDF report export

The system supports two runtime modes:

- `general`: scene/safety monitoring for common environments
- `cat`: Caterpillar-style heavy equipment inspection workflow

---

## 2) High-level architecture

### Backend (Modal)

- `backend/modal_app/orchestrator.py`
  - FastAPI WebSocket endpoint at `/ws`
  - Receives frames and control messages
  - Runs YOLO detection and mode-aware VLM analysis
  - Returns detection, analysis, voice answers, part ID, report output

- `backend/modal_app/yolo_detector.py`
  - YOLOv8 inference for frame object detection

- `backend/modal_app/qwen_vl.py`
  - Qwen2-VL image + prompt reasoning
  - Used for analysis, question answering, spec assessment, report generation

- `backend/modal_app/siglip2.py`
  - SigLIP2 embedding-based part identification

- `backend/prompts.py`
  - Prompt templates and JSON output schemas
  - Includes both general-mode and CAT-mode personas/schemas

### Client (local simulation harness)

- `scripts/e2e_webcam_demo.py`
  - Captures webcam frames
  - Performs frame quality gating
  - Sends latest frames to backend via WebSocket
  - Handles local voice input/output
  - Displays HUD + overlays
  - Saves evidence and session artifacts

### Data

- `data/cat_spec_kb.json` — CAT inspection knowledge
- `data/sub_section_prompts.json` — prompt mapping
- `data/seed_parts.json` — parts catalog seed
- `data/seed_inspections.json` — inspection history seed

---

## 3) Runtime behavior

### Frame path

1. Client captures a frame from camera.
2. Frame is sent to backend (`type: "frame"`).
3. Backend runs YOLO quickly and emits `detection`.
4. Backend runs VLM at a controlled cadence and emits `analysis`.
5. Client updates HUD, speaks notable callouts, and logs findings.

### Voice path

1. Local mic audio is segmented by VAD.
2. `faster-whisper` transcribes locally.
3. Intent router classifies transcript as:
   - command
   - question
   - finding
4. Commands execute locally or send WS control actions.
5. Questions are sent to backend (`type: "voice_question"`).
6. Backend returns `voice_answer`, client speaks first sentence.

### Report path

1. User requests report (`r` key or voice command).
2. Backend generates report text/JSON via Qwen.
3. Client stores report, then renders PDF with evidence thumbnails.
4. Session directory contains full artifacts.

---

## 4) Inspection modes

Mode can be switched at startup, via keyboard, or by voice command.

- Startup flag:
  - `--mode general`
  - `--mode cat`
- Runtime keys:
  - `g` for General
  - `c` for CAT
- Runtime voice commands:
  - “general mode”
  - “cat mode”

Mode effects:

- **General mode**
  - Prompting is safety/scene-change oriented
  - Non-command speech is treated more as question-style interaction

- **CAT mode**
  - Prompting is equipment-inspection oriented
  - Voice findings are parsed into zone/rating logs
  - Spec-assessment flow is used for YELLOW/RED cases

---

## 5) WebSocket contract (current)

### Client -> Backend messages

- `frame`
  - `type`, `data` (base64 image), `frame_id`, `client_ts`, `mode`
- `audio`
  - `type`, `data` (base64 audio) (currently no-op in orchestrator; local STT is primary)
- `set_mode`
  - `type`, `mode` (`general` or `cat`)
- `voice_question`
  - `type`, `text`, `frame`
- `request_vlm_analysis`
- `request_zone_brief`
- `request_spec_assessment`
- `identify_part`
- `generate_report`

### Backend -> Client messages

- `detection`
  - detections, coverage, yolo latency, frame metadata, mode
- `analysis`
  - severity/callout/findings/zone payload, frame metadata, mode
- `voice_answer`
- `zone_first_seen`
- `zone_brief`
- `spec_assessment`
- `parts_result`
- `report`
- `mode`

---

## 6) Running the system

### Prerequisites

- Python 3.9+ local environment
- Modal CLI authenticated (`modal token set` or `modal setup`)
- Dependencies installed from `requirements.txt`

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Deploy backend

```bash
modal deploy modal_deploy.py
```

### Health check

```bash
curl https://YOUR_WORKSPACE--dronecat-web.modal.run/health
```

### Run e2e client

```bash
export MODAL_WS_URL=wss://YOUR_WORKSPACE--dronecat-web.modal.run/ws
python3 scripts/e2e_webcam_demo.py --camera 0 --mode general
```

---

## 7) Controls and voice commands

### Keyboard

- `g` General mode
- `c` CAT mode
- `r` request report
- `e` save evidence snapshot
- `p` part identification
- `m` mute/unmute mic
- `q` quit

### Common voice commands

- “generate report”
- “save evidence”
- “mute”
- “unmute”
- “cat mode”
- “general mode”
- natural spoken question (answered from current frame context)

---

## 8) Output artifacts

Each run creates a session folder in `sessions/<timestamp>/` containing:

- `session.json` (metadata and timing)
- `findings.jsonl` (streamed findings)
- `report.json` (backend report output)
- `report.pdf` (if `fpdf2` available)
- `evidence/*.jpg` (manual + auto snapshots)

---

## 9) Reliability and latency notes

- Orchestrator uses latest-frame semantics with backlog dropping behavior.
- YOLO and VLM are decoupled; VLM runs at cadence to avoid blocking detection.
- Voice STT is local for lower latency than cloud round-trips.
- TTS is interruptible and queue-based.

If response feels stale:

- Ensure WebSocket is connected and `S/R` values are non-zero in HUD.
- Reduce `--frame-interval` and `--force-send-ms`.
- Check Modal app is warm (`scripts/warmup.py`).

---

## 10) Troubleshooting

- **No voice transcription**
  - Ensure `faster-whisper`, `sounddevice`, `silero-vad` are installed.
  - Verify mic permissions on macOS.

- **No spoken output**
  - macOS `say` is required for current local TTS path.
  - Ensure mic is not permanently muted and app is not blocked by audio device errors.

- **Frequent reconnect / ping timeout**
  - Verify stable network and correct `MODAL_WS_URL`.
  - Check Modal logs for long model startup.

- **Module import warnings in IDE**
  - Usually local interpreter/dependency indexing issue; runtime can still be correct if env is installed.

---

## 11) Suggested next improvements

- Add explicit event schema versioning shared by client/backend.
- Add runtime toggles for analysis cadence and voice verbosity over WS.
- Add export bundle endpoint for PDF + JSON + evidence zip.
- Add web mission-control UI that reuses the same WS contract.
