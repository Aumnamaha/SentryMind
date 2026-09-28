# SentryMind — 8 GB RAM / 4 GB VRAM Optimization Tasks

## Objective

Optimize SentryMind to run reliably on a constrained machine with:

- 8 GB system RAM target
- AMD RX 6500M
- 4 GB VRAM
- AMD Vulkan/RADV
- Ryzen 5 5600H
- Linux/CachyOS
- Qwen2.5-3B-Instruct Q4_K_M
- llama.cpp Vulkan
- Official Hindsight for persistent memory

The goal is maximum stability and efficiency without removing core SentryMind functionality.

DO NOT replace the real Hindsight service with a mock.

DO NOT switch to a larger model.

DO NOT install NVIDIA/CUDA dependencies.

DO NOT sacrifice security or evidence-grounded diagnosis merely to reduce resource usage.

---
main task:for every phase su should test each and evry line no room for error 
# PHASE 0 — SAFETY AND BASELINE

Before modifying anything:

1. Check git status.
2. Do not overwrite unrelated user changes.
3. Record current test count.
4. Record current inference performance.
5. Record current VRAM usage.
6. Record current RAM usage.
7. Record current API latency.
8. Record current model configuration.
9. Record current Hindsight configuration.

Create:

`OPTIMIZATION_BASELINE.md`

Record actual measurements, not estimates.

Run:

```bash
git status
