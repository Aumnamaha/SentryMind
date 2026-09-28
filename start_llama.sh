#!/bin/bash
# Start llama.cpp server with a context size large enough for Hindsight.
#
# -np 1 is CRITICAL: llama-server defaults to 4 parallel slots, which splits
# the context window (n_ctx / 4) per slot. Hindsight's fact-extraction prompts
# need ~2.4k tokens and reflect needs ~7.8k, so a split context makes every
# extraction fail with "Context size has been exceeded".
cd /home/knk/SentryMind/models || exit 1
exec /tmp/opencode/llama.cpp/build/bin/llama-server \
  -m Qwen2.5-3B-Instruct-Q4_K_M.gguf \
  --host 127.0.0.1 \
  --port 1234 \
  --ctx-size 8192 \
  --parallel 1 \
  --n-gpu-layers 99 \
  --batch-size 512 \
  --ubatch-size 512 \
  --threads 6
