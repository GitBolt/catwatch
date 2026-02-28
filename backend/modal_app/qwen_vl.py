import modal

from . import app, vllm_image


@app.cls(
    gpu=modal.gpu.A100(size="40GB"),
    image=vllm_image,
    keep_warm=1,
    container_idle_timeout=300,
)
class Qwen25VLInspector:
    @modal.enter()
    def load(self):
        from vllm import LLM, SamplingParams

        self.llm = LLM(
            "Qwen/Qwen2.5-VL-7B-Instruct",
            max_model_len=8192,
            gpu_memory_utilization=0.9,
        )
        self.sampling_params = SamplingParams(
            temperature=0.3,
            max_tokens=2048,
        )

    @modal.method()
    def generate(self, prompt, image_b64=None):
        messages = [{"role": "user", "content": []}]

        if image_b64:
            messages[0]["content"].append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_b64}"},
            })

        messages[0]["content"].append({"type": "text", "text": prompt})

        outputs = self.llm.chat(messages, self.sampling_params)
        return outputs[0].outputs[0].text

    @modal.method()
    def zone_brief(self, prompt):
        messages = [{"role": "user", "content": prompt}]
        outputs = self.llm.chat(messages, self.sampling_params)
        return outputs[0].outputs[0].text

    @modal.method()
    def spec_assessment(self, prompt, image_b64):
        return self.generate(prompt, image_b64=image_b64)

    @modal.method()
    def generate_report(self, prompt):
        params = self.sampling_params.clone()
        params.max_tokens = 4096
        messages = [{"role": "user", "content": prompt}]
        outputs = self.llm.chat(messages, params)
        return outputs[0].outputs[0].text
