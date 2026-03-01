import base64
import io
import json
import time

import modal

from . import app, qwen_image

MODEL_ID = "Qwen/Qwen2-VL-7B-Instruct"


@app.cls(
    gpu="A100",
    image=qwen_image,
    min_containers=1,
    scaledown_window=300,
)
class Qwen25VLInspector:
    @modal.enter()
    def load(self):
        from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
        import torch

        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        self.processor = AutoProcessor.from_pretrained(MODEL_ID)
        print(f"[Qwen2VL] Loaded {MODEL_ID} on A100.")

        from faster_whisper import WhisperModel
        self.whisper = WhisperModel("small.en", device="cuda", compute_type="float16")
        print("[Whisper] Loaded small.en on CUDA.")

    def _run(self, messages, max_new_tokens=512):
        from qwen_vl_utils import process_vision_info

        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self.model.device)

        import torch
        t0 = time.time()
        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=0.1,
                do_sample=True,
            )
        generated = output_ids[:, inputs["input_ids"].shape[1]:]
        text_out = self.processor.batch_decode(generated, skip_special_tokens=True)[0]
        print(f"[Qwen2VL] inference {round((time.time()-t0)*1000)}ms")
        return text_out

    def _image_message(self, image_b64):
        return {"type": "image", "image": f"data:image/jpeg;base64,{image_b64}"}

    @modal.method()
    def analyze_frame(self, image_b64, system_prompt, schema_prompt):
        messages = [
            {
                "role": "user",
                "content": [
                    self._image_message(image_b64),
                    {"type": "text", "text": f"{system_prompt}\n\n{schema_prompt}"},
                ],
            }
        ]
        raw = self._run(messages, max_new_tokens=512)

        # Try to extract JSON from freeform output
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
        return {
            "description": raw.strip(),
            "severity": "GREEN",
            "findings": [],
            "callout": "",
            "confidence": 0.5,
            "zone": None,
        }

    @modal.method()
    def generate(self, prompt, image_b64=None):
        content = []
        if image_b64:
            content.append(self._image_message(image_b64))
        content.append({"type": "text", "text": prompt})
        messages = [{"role": "user", "content": content}]
        return self._run(messages, max_new_tokens=512)

    @modal.method()
    def zone_brief(self, prompt):
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        return self._run(messages, max_new_tokens=512)

    @modal.method()
    def spec_assessment(self, prompt, image_b64=None):
        content = []
        if image_b64:
            content.append(self._image_message(image_b64))
        content.append({"type": "text", "text": prompt})
        messages = [{"role": "user", "content": content}]
        return self._run(messages, max_new_tokens=512)

    @modal.method()
    def generate_report(self, prompt):
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        return self._run(messages, max_new_tokens=2048)

    @modal.method()
    def identify_equipment(self, image_b64):
        """Identify equipment type, model, and inspectable zones from a single frame."""
        prompt = (
            "You are a Caterpillar equipment identification specialist.\n"
            "Look at this image carefully. Identify the equipment and read any visible text.\n\n"
            "Return ONLY valid JSON:\n"
            "{\n"
            '  "equipment_type": "excavator" | "wheel_loader" | "dozer" | "motor_grader" | '
            '"articulated_truck" | "telehandler" | "backhoe_loader" | "skid_steer" | "compact_track_loader" | "other",\n'
            '  "model_guess": "e.g. CAT 325, CAT 982M, CAT D8T — best guess from visual cues",\n'
            '  "visible_text": "any serial number, model plate, or hour meter text you can read" or null,\n'
            '  "inspectable_zones": ["list of major component areas that should be inspected on this equipment type"]\n'
            "}\n\n"
            "For inspectable_zones, list the actual component groups relevant to THIS equipment type. "
            "Examples:\n"
            "- Excavator: undercarriage, tracks, boom, stick, bucket, hydraulic_cylinders, hydraulic_hoses, cab, engine, cooling_system, swing_bearing, counterweight, attachments\n"
            "- Wheel loader: tires, rims, loader_arms, bucket, hydraulic_cylinders, hydraulic_hoses, cab, engine, cooling_system, drivetrain, axles, counterweight\n"
            "- Dozer: tracks, undercarriage, blade, push_arms, hydraulic_cylinders, cab, engine, cooling_system, ripper, final_drives\n"
            "Use snake_case. Be specific to what you see."
        )
        messages = [
            {"role": "user", "content": [
                self._image_message(image_b64),
                {"type": "text", "text": prompt},
            ]},
        ]
        raw = self._run(messages, max_new_tokens=512)
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
        return {"equipment_type": "unknown", "model_guess": None, "visible_text": None, "inspectable_zones": []}

    @modal.method()
    def transcribe_audio(self, audio_bytes: bytes) -> str:
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        try:
            segments, _ = self.whisper.transcribe(tmp_path, beam_size=3, language="en")
            return " ".join(s.text.strip() for s in segments).strip()
        finally:
            os.unlink(tmp_path)
