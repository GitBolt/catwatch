"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface Props {
  onAudio: (audioBase64: string) => void;
  voiceAnswer: string | null;
}

export function VoiceButton({ onAudio, voiceAnswer }: Props) {
  const [mounted, setMounted] = useState(false);
  const [recording, setRecording] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "audio/mp4";

      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;

        const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
        if (blob.size < 1000) return;

        const reader = new FileReader();
        reader.onload = () => {
          const base64 = (reader.result as string).split(",")[1];
          if (base64) {
            setWaiting(true);
            onAudio(base64);
          }
        };
        reader.readAsDataURL(blob);
      };

      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {}
  }, [onAudio]);

  const stopRecording = useCallback(() => {
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    }
    setRecording(false);
  }, []);

  const toggleRecording = useCallback(() => {
    if (recording) stopRecording();
    else startRecording();
  }, [recording, startRecording, stopRecording]);

  useEffect(() => {
    if (waiting && voiceAnswer !== null) {
      setWaiting(false);
    }
  }, [waiting, voiceAnswer]);

  const micAvailable = mounted && !!navigator.mediaDevices?.getUserMedia;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <button
        onClick={toggleRecording}
        disabled={waiting || !micAvailable}
        className={recording ? "btn pulse" : "btn btn-secondary"}
        style={
          recording
            ? { background: "var(--red)", color: "#fff", flexShrink: 0 }
            : { flexShrink: 0 }
        }
      >
        <svg
          style={{ width: 16, height: 16 }}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z"
          />
        </svg>
        {recording ? " Stop" : ""}
      </button>
      {waiting && (
        <span className="mono" style={{ fontSize: 12, color: "var(--text-dim)" }}>
          Processing...
        </span>
      )}
    </div>
  );
}
