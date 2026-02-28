"""
Text-to-speech output and push-to-talk voice input.

Voice input is toggle push-to-talk via the OpenCV window:
  - Press Space to start recording (red border appears on frame)
  - Press Space again to stop — audio is sent to local Whisper, then forwarded to the backend
  - Everything else (equipment names, anomaly alerts) is driven by the inspection pipeline
"""

import queue
import subprocess
import sys
import threading
import time

import numpy as np

from .constants import SAMPLE_RATE


# ── TTS via macOS `say` ──────────────────────────────────────────────────────

_tts_queue     = queue.Queue()
_tts_proc      = None
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
        time.sleep(0.3)
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


def _kill_tts():
    """Silently stop any in-progress TTS without queuing new speech."""
    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
        except queue.Empty:
            break
    with _tts_proc_lock:
        if _tts_proc and _tts_proc.poll() is None:
            _tts_proc.kill()


# ── Push-to-talk voice capture ───────────────────────────────────────────────

class VoiceCapture:
    """
    Toggle push-to-talk via the OpenCV window's Space key.

    Press Space to begin recording; press Space again to stop and queue the
    utterance for Whisper transcription.  The audio stream runs continuously
    but only accumulates samples while ptt_recording is True.

    start_ptt() / stop_ptt() are called by the main keyboard handler.
    No OS-level keyboard hooks required.
    """

    def __init__(self):
        self.running       = False
        self.ptt_recording = False
        self._buffer       = []
        self._utterances   = []
        self._lock         = threading.Lock()

    def start(self):
        try:
            import sounddevice  # noqa: F401
        except ImportError as e:
            print(f"  Audio disabled ({e}). Install sounddevice.", file=sys.stderr)
            return

        self.running = True
        threading.Thread(target=self._audio_loop, daemon=True).start()
        print("  PTT ready — press Space to start/stop recording.")

    def start_ptt(self):
        """Begin a recording session. Kills any in-progress TTS first."""
        if self.ptt_recording:
            return
        _kill_tts()   # stop speaker so mic doesn't pick up TTS output
        self.ptt_recording = True
        self._buffer = []

    def stop_ptt(self):
        """End the recording session and queue the utterance."""
        if not self.ptt_recording:
            return
        self._flush()

    def _audio_loop(self):
        import sounddevice as sd

        def callback(indata, frames, time_info, status):
            if self.ptt_recording:
                self._buffer.append(indata[:, 0].copy())

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                blocksize=512, callback=callback):
                while self.running:
                    time.sleep(0.05)
        except Exception as e:
            print(f"  Audio stream error: {e}", file=sys.stderr)

    def _flush(self):
        self.ptt_recording = False
        if self._buffer:
            audio = np.concatenate(self._buffer)
            with self._lock:
                self._utterances.append(audio)
        self._buffer = []

    def get_utterance(self):
        with self._lock:
            if self._utterances:
                return self._utterances.pop(0)
        return None

    def stop(self):
        self.running = False
        if self.ptt_recording:
            self._flush()


# ── Utterance handler ────────────────────────────────────────────────────────

def handle_utterance(whisper_model, audio_array, shared, lock):
    """
    Transcribe a PTT recording and send it to the backend as a voice question.
    The backend responds with a voice_answer which is spoken aloud by ws_client.
    """
    try:
        segments, _ = whisper_model.transcribe(audio_array, beam_size=1, language="en")
        transcript  = " ".join(s.text.strip() for s in segments).strip()
    except Exception as e:
        print(f"  whisper error: {e}")
        return

    if not transcript or len(transcript) < 3:
        return

    shared["transcript"] = transcript
    print(f"  voice query: {transcript}")

    frame_b64 = shared.get("last_frame_b64")
    if frame_b64:
        with lock:
            shared["pending_actions"].insert(0, ("voice_question", {
                "type":  "voice_question",
                "text":  transcript,
                "frame": frame_b64,
            }))
    else:
        speak("No frame available yet.")
