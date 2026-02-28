import modal

from . import app, whisper_image


@app.cls(
    gpu=modal.gpu.T4(),
    image=whisper_image,
    keep_warm=1,
    container_idle_timeout=600,
)
class WhisperTranscriber:
    @modal.enter()
    def load(self):
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
        import torch

        model_id = "openai/whisper-large-v3"
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id, torch_dtype=torch.float16
        ).to("cuda")
        self.model.eval()

    @modal.method()
    def transcribe(self, audio_bytes, sample_rate=16000):
        import torch
        import numpy as np

        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
        inputs = self.processor(
            audio_array,
            sampling_rate=sample_rate,
            return_tensors="pt",
        ).to("cuda")

        with torch.no_grad():
            predicted_ids = self.model.generate(**inputs, max_new_tokens=256)

        transcript = self.processor.batch_decode(
            predicted_ids, skip_special_tokens=True
        )[0]
        return transcript.strip()
