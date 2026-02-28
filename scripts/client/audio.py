"""
Text-to-speech output, microphone capture with Silero VAD, and voice command routing.
"""

import queue
import subprocess
import sys
import threading
import time

import numpy as np

from .constants import SAMPLE_RATE, VAD_THRESHOLD


# ── TTS via macOS `say` ─────────────────────────────────────────────────────

_tts_queue    = queue.Queue()
_tts_proc     = None
_tts_proc_lock = threading.Lock()
_tts_speaking  = False


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


threading.Thread(target=_tts_worker, daemon=True).start()


def speak(text):
    """Interrupt any in-progress utterance and speak text (macOS only)."""
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


# ── Microphone capture with Silero VAD ─────────────────────────────────────

class VoiceCapture:
    """
    Streams microphone audio and uses Silero VAD to segment speech utterances.

    Call start() to begin capturing; get_utterance() returns a complete numpy
    audio array once a pause is detected after speech. Muting suppresses capture
    while TTS is playing to avoid feedback.
    """

    def __init__(self):
        self.running        = False
        self.muted          = False
        self._utterances    = []
        self._lock          = threading.Lock()
        self._vad_model     = None
        self._buffer        = []
        self._speech_active = False
        self._silence_frames = 0
        self._max_silence   = 30

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
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def _capture_loop(self):
        import sounddevice as sd
        import torch

        def callback(indata, frames, time_info, status):
            if self.muted or not self.running or _tts_speaking:
                return
            audio = indata[:, 0].copy()
            try:
                prob = self._vad_model(torch.from_numpy(audio).float(), SAMPLE_RATE).item()
            except Exception:
                prob = 0.0

            if prob > VAD_THRESHOLD:
                self._speech_active  = True
                self._silence_frames = 0
                self._buffer.append(audio)
            elif self._speech_active:
                self._silence_frames += 1
                self._buffer.append(audio)
                if self._silence_frames >= self._max_silence:
                    self._flush()

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                blocksize=512, callback=callback):
                while self.running:
                    time.sleep(0.1)
        except Exception as e:
            print(f"  Audio stream error: {e}", file=sys.stderr)

    def _flush(self):
        if self._buffer:
            with self._lock:
                self._utterances.append(np.concatenate(self._buffer))
            self._buffer = []
        self._speech_active  = False
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


# ── Voice intent classification ─────────────────────────────────────────────

_Q_WORDS = {"what", "how", "why", "where", "is", "does", "can", "tell",
            "describe", "show", "explain", "do", "are", "which"}

_COMMANDS = {
    "generate report":  "report",
    "create report":    "report",
    "make report":      "report",
    "save evidence":    "evidence",
    "capture evidence": "evidence",
    "take photo":       "evidence",
    "unmute":           "unmute",
    "mute":             "mute",
    "stop":             "stop",
    "cat mode":         "mode_cat",
    "switch to cat":    "mode_cat",
    "general mode":     "mode_general",
    "switch to general":"mode_general",
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


# ── Utterance handler (transcribe → classify → act) ────────────────────────

def handle_utterance(whisper_model, audio_array, shared, lock, spec_kb):
    """
    Transcribe a captured utterance, classify its intent, and act:
      - command  → dispatch to the matching action (mode switch, report, mute, …)
      - question → send a voice_question to the backend with the current frame
      - finding  → extract zone/rating via NLP and log it; fall back to question if unrecognised
    """
    try:
        segments, _ = whisper_model.transcribe(audio_array, beam_size=1, language="en")
        transcript  = " ".join(s.text.strip() for s in segments).strip()
    except Exception as e:
        print(f"  local whisper error: {e}")
        return

    if not transcript or len(transcript) < 3:
        return

    shared["transcript"] = transcript
    print(f"  voice: {transcript}")

    intent, cmd = _classify_intent(transcript)

    if intent == "command":
        _dispatch_command(cmd, shared, lock)
    elif intent == "question":
        _send_voice_question(transcript, shared, lock)
    else:
        _record_voiced_finding(transcript, shared, lock, spec_kb)


def _dispatch_command(cmd, shared, lock):
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
        with lock:
            shared["pending_actions"].append(("set_mode", {"type": "set_mode", "mode": "cat"}))
        speak("CAT mode enabled.")
    elif cmd == "mode_general":
        shared["inspection_mode"] = "general"
        with lock:
            shared["pending_actions"].append(("set_mode", {"type": "set_mode", "mode": "general"}))
        speak("General mode enabled.")


def _send_voice_question(transcript, shared, lock):
    frame_b64 = shared.get("last_frame_b64")
    if frame_b64:
        with lock:
            shared["pending_actions"].append(("voice_question", {
                "type": "voice_question",
                "text": transcript,
                "frame": frame_b64,
            }))
    else:
        speak("No frame available yet.")


def _record_voiced_finding(transcript, shared, lock, spec_kb):
    from backend.nlp import extract_finding  # lazy: needs sys.path set by entry point
    from .constants import ALL_ZONES

    finding = extract_finding(transcript)
    if finding["zone"]:
        zone, rating = finding["zone"], finding["rating"]
        with lock:
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
        _send_voice_question(transcript, shared, lock)
