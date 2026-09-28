"""Inference configuration for SentryMind.

Supports local llama.cpp server (OpenAI-compatible API) and LM Studio.
All settings are configurable via environment variables.
"""

import os

# ---------------------------------------------------------------------------
# Inference server configuration
# ---------------------------------------------------------------------------

# Local llama.cpp server (default) or LM Studio
INFERENCE_BACKEND = os.getenv("SENTRYMIND_INFERENCE_BACKEND", "llama-cpp")

# Server endpoint
INFERENCE_URL = os.getenv("SENTRYMIND_INFERENCE_URL", "http://127.0.0.1:1234/v1")

# Model name (must match the model loaded on the server)
INFERENCE_MODEL = os.getenv("SENTRYMIND_INFERENCE_MODEL", "qwen2.5-3b-instruct")

# Model file path (for llama.cpp server)
MODEL_PATH = os.getenv(
    "SENTRYMIND_MODEL_PATH", "models/Qwen2.5-3B-Instruct-Q4_K_M.gguf"
)

# llama.cpp server binary path
LLAMA_SERVER_PATH = os.getenv(
    "SENTRYMIND_LLAMA_SERVER", "/tmp/opencode/llama.cpp/build/bin/llama-server"
)

# ---------------------------------------------------------------------------
# Inference parameters
# ---------------------------------------------------------------------------

# Context size (tokens)
CONTEXT_SIZE = int(os.getenv("SENTRYMIND_CONTEXT_SIZE", "2048"))

# GPU offload layers (99 = all layers on GPU)
GPU_LAYERS = int(os.getenv("SENTRYMIND_GPU_LAYERS", "99"))

# Batch size and microbatch size
BATCH_SIZE = int(os.getenv("SENTRYMIND_BATCH_SIZE", "128"))
UBATCH_SIZE = int(os.getenv("SENTRYMIND_UBATCH_SIZE", "128"))

# Number of concurrent inference slots
NUM_SLOTS = int(os.getenv("SENTRYMIND_NUM_SLOTS", "1"))

# Temperature (lower = more deterministic)
TEMPERATURE = float(os.getenv("SENTRYMIND_TEMPERATURE", "0.2"))

# Maximum output tokens
MAX_OUTPUT_TOKENS = int(os.getenv("SENTRYMIND_MAX_OUTPUT_TOKENS", "512"))

# Request timeout (seconds)
REQUEST_TIMEOUT = int(os.getenv("SENTRYMIND_REQUEST_TIMEOUT", "60"))

# ---------------------------------------------------------------------------
# Agent behavior
# ---------------------------------------------------------------------------

# Maximum incident log length (characters) — logs are truncated to this
MAX_LOG_LENGTH = int(os.getenv("SENTRYMIND_MAX_LOG_LENGTH", "8000"))

# Maximum number of recalled memories
MAX_RECALL_RESULTS = int(os.getenv("SENTRYMIND_MAX_RECALL_RESULTS", "3"))

# Maximum tokens for recalled context
MAX_RECALL_TOKENS = int(os.getenv("SENTRYMIND_MAX_RECALL_TOKENS", "500"))

# Enable/disable memory by default
DEFAULT_USE_MEMORY = os.getenv("SENTRYMIND_USE_MEMORY", "true").lower() == "true"

# ---------------------------------------------------------------------------
# GPU selection
# ---------------------------------------------------------------------------

# Vulkan device index (0 = first GPU, 1 = second GPU, etc.)
# On this laptop: 0 = integrated, 1 = discrete RX 6500M
VULKAN_DEVICE = int(os.getenv("SENTRYMIND_VULKAN_DEVICE", "1"))

# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------

# llama.cpp server host and port
LLAMA_HOST = os.getenv("SENTRYMIND_LLAMA_HOST", "127.0.0.1")
LLAMA_PORT = int(os.getenv("SENTRYMIND_LLAMA_PORT", "1234"))

# Number of CPU threads for llama.cpp
LLAMA_THREADS = int(os.getenv("SENTRYMIND_LLAMA_THREADS", "6"))
