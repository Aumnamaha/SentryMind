#!/bin/bash
# Start official Hindsight server
cd /home/knk/SentryMind

export HINDSIGHT_API_LLM_PROVIDER=lmstudio
export HINDSIGHT_API_LLM_BASE_URL=http://127.0.0.1:1234/v1
export HINDSIGHT_API_LLM_MODEL=qwen2.5-3b-instruct
export HINDSIGHT_API_LLM_API_KEY=local-not-used
export HINDSIGHT_API_LLM_STRICT_SCHEMA=true

# LLM deadlines. Hindsight ships DEFAULT_LLM_TIMEOUT=120s and
# DEFAULT_REFLECT_LLM_TIMEOUT=30s, both tuned for hosted models on fast
# networks. llama.cpp serves Qwen2.5-3B on a single Vulkan slot at ~48 tok/s, so
# a reflect synthesis (~7.8k input / ~660 output tokens) measures 38.5s
# uncontended and far longer when it queues behind fact extraction. At the
# 30s default every reflect call raised APITimeoutError and returned HTTP 500.
export HINDSIGHT_API_LLM_TIMEOUT=600
export HINDSIGHT_API_REFLECT_LLM_TIMEOUT=600
export HINDSIGHT_API_RETAIN_LLM_TIMEOUT=600

# Reflect's overall wall-clock budget (Hindsight's default is 300s). At ~48
# tok/s a synthesis over a populated bank does not finish inside 5 minutes on
# this hardware; measured 300.0s and returning HTTP 504 on the nose.
export HINDSIGHT_API_REFLECT_WALL_TIMEOUT=1200

export HINDSIGHT_API_EMBEDDINGS_PROVIDER=local
export HINDSIGHT_API_EMBEDDINGS_LOCAL_MODEL=BAAI/bge-small-en-v1.5
export HINDSIGHT_API_RERANKER_PROVIDER=local
export HINDSIGHT_API_RERANKER_LOCAL_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
export HINDSIGHT_API_WORKER_ID=sentrymind-hindsight

exec .venv/bin/python -m hindsight_api.server \
  --host 127.0.0.1 \
  --port 8888 \
  --workers 1
