# Dronecat: Model Context & Memory Improvement Ideas

## Problem 1: The model doesn't know what it's actually looking at

The CAT persona is injected unconditionally, causing the model to either hallucinate
equipment findings or give useless "no equipment visible" responses.

### A) YOLO-gated context
Only send the CAT persona when YOLO has actually detected relevant objects (or the
CAT yellow/black color check has fired). Otherwise fall back to general mode. The
model is only told it's inspecting CAT equipment when there is visual evidence it is.

### B) Pass YOLO results into the VLM prompt ✅ START HERE
Instead of just sending the image, tell Qwen what YOLO already detected:
"YOLO detected: excavator (0.87 conf), hydraulic cylinder (0.72 conf), person (0.91 conf)."
The model has a grounded starting point and doesn't have to guess what it's looking at.

### C) Zone-first prompting
The technician declares which zone they're pointing at (verbally or via keyboard),
and the prompt becomes specific to that zone: "The technician has positioned the camera
on the hydraulics zone." Rather than the model guessing the zone, it's told.

### D) Confidence-gated persona
The model first answers "is this heavy equipment?" and only runs the full CAT
inspection analysis if it answers yes with sufficient confidence. Adds a round-trip
so higher latency.

---

## Problem 2: The model has no memory across frames

Every Qwen call is fresh — it doesn't know what it assessed 10 seconds ago, what
findings are already logged, or how far along the inspection is.

### A) Rolling findings summary in every prompt
Maintain a short text blob of the last N findings and inject it into every VLM call.
"Already logged: hydraulics YELLOW (hose abrasion), tracks_left GREEN (nominal wear)."
Simple and cheap, but grows unbounded with inspection length.

### B) Zone-level state in every prompt ✅ HIGH IMPACT
Summarize at zone granularity: which zones are done/pending and their current status.
Bounded in size (15 zones max), directly relevant to inspection progress.
e.g. "Inspection progress: engine ✓ RED, hydraulics ✓ YELLOW, cab pending, 12 zones remaining."

### C) Temporal frame batching
Send 3-5 frames at once with timestamps rather than one at a time. The model sees
progression and can reason about change over time. Higher quality output but
significantly higher latency and token cost.

### D) Running narrative
After each VLM call, maintain a running text narrative and append each new analysis.
Inject the last few sentences as context into the next call. The model builds on its
own prior reasoning. Risk: compounding errors if early analysis was wrong.

### E) Supermemory for long-term / cross-session memory
Use the Supermemory client (already in codebase) to store findings from this session
and past sessions on this unit. Lets the model answer questions like "has this
hydraulic issue been seen before on this serial number?" Future concern — lower
priority than in-session memory.

---

## Key tensions to keep in mind

- **Latency vs. richness**: A100 inference is the bottleneck (~1-2s/frame). How much
  context can we inject before it becomes unusable?
- **Who declares the zone?**: Explicit technician declaration vs. automatic inference.
- **Memory depth**: Don't re-analyze what's already assessed vs. use prior findings
  to inform current analysis (is this getting worse?).
- **Cross-session memory**: Unit history informing current session — lower priority,
  revisit after in-session memory works well.
