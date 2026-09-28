# SentryMind Model Configuration

**Date:** 2026-09-28  
**Purpose:** Exact model source, quantization, Vulkan build instructions, and recommended settings

---

## 1. Model Selection

### 1.1 Selected Model

| Property | Value |
|----------|-------|
| **Model** | Qwen2.5-3B-Instruct |
| **Quantization** | Q4_K_M |
| **Format** | GGUF |
| **Source** | Hugging Face: `Qwen/Qwen2.5-3B-Instruct-GGUF` |
| **File** | `qwen2.5-3b-instruct-q4_k_m.gguf` |
| **Size** | 2.1 GB |
| **Download URL** | `https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf` |

### 1.2 Why This Model

- **Fits in 4GB VRAM:** Q4_K_M quantization uses ~1.9GB VRAM with all layers offloaded
- **Good quality:** 3B parameters provide acceptable quality for incident triage
- **Fast inference:** ~40 tokens/sec on AMD RX 6500M with Vulkan
- **Low TTFT:** 23ms time to first token
- **Configurable:** Model choice is configurable via `SENTRYMIND_INFERENCE_MODEL`

### 1.3 Why Not 35B

The default `qwen2.5-35b-instruct` requires ~20GB+ VRAM even with Q4 quantization, which exceeds the 4GB RX 6500M. The 3B model is the largest that fits comfortably.

---

## 2. GPU Selection

### 2.1 Detected GPUs

| Index | Name | Type | VRAM | Vulkan Device |
|-------|------|------|------|---------------|
| 0 | AMD Radeon Graphics (RADV RENOIR) | Integrated | 512 MB | card2 |
| 1 | AMD Radeon RX 6500 (RADV NAVI24) | Discrete | 4 GB | card1 |

### 2.2 GPU Selection

**Selected:** GPU index 1 (discrete AMD Radeon RX 6500M)

**Configuration:**
```bash
export SENTRYMIND_VULKAN_DEVICE=1
```

**Verification:**
```bash
# Check VRAM usage
cat /sys/class/drm/card1/device/mem_info_vram_used  # Should show ~1.9GB when model loaded
cat /sys/class/drm/card1/device/mem_info_vram_total  # Should show ~4GB

# Check Vulkan device
vulkaninfo --summary | grep -A 5 "GPU1"
```

### 2.3 GPU Memory Monitoring

```bash
# Watch VRAM usage in real-time
watch -n 1 'cat /sys/class/drm/card1/device/mem_info_vram_used | awk "{printf \"%.2f GB\n\", \$1/1024/1024/1024}"'
```

---

## 3. llama.cpp Vulkan Build

### 3.1 Build Instructions

```bash
# Clone llama.cpp
cd /tmp/opencode
git clone --depth 1 --branch v0.5.0 https://github.com/ggml-org/llama.cpp.git llama.cpp

# Configure with Vulkan support
cd llama.cpp
cmake -B build -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release

# Build (uses 12 cores)
cmake --build build --config Release -j 12

# Verify Vulkan support
./build/bin/llama-cli --version
# Should show: built with Vulkan
```

### 3.2 Build Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| cmake | 4.4.3 | Build system |
| gcc/g++ | 16.2.1 | C++ compiler |
| Vulkan headers | 1.4.357 | GPU API |
| Vulkan ICD loader | 1.4.357 | GPU driver interface |
| Mesa RADV | 26.2.3 | AMD Vulkan driver |

### 3.3 Build Verification

```bash
# Check Vulkan devices
vulkaninfo --summary | grep -E "GPU|deviceName"

# Check llama.cpp Vulkan support
./build/bin/llama-cli -m /path/to/model.gguf -p "test" -n 1 --no-display-prompt -ngl 99 2>&1 | grep -i vulkan
```

---

## 4. Inference Server Configuration

### 4.1 Recommended Settings (4GB VRAM)

```bash
/tmp/opencode/llama.cpp/build/bin/llama-server \
  -m /home/knk/SentryMind/models/Qwen2.5-3B-Instruct-Q4_K_M.gguf \
  --host 127.0.0.1 \
  --port 1234 \
  --ctx-size 8192 \
  --parallel 1 \
  --n-gpu-layers 99 \
  --batch-size 512 \
  --ubatch-size 512 \
  --threads 6
```

### 4.2 `--parallel 1` Is Mandatory When Hindsight Is Enabled

llama-server defaults to **4 concurrent slots**. With `--parallel N`, the
context window is divided per slot, so the usable context is `n_ctx / N`.

Hindsight's fact-extraction prompt is ~2,400 tokens and `reflect` needs ~7,800.
With the default 4 slots an 8,192 context becomes 2,048 per slot and **every**
extraction fails:

```
APIStatusError (lmstudio/qwen2.5-3b-instruct, scope=retain_extract_facts):
  HTTP 500 {"code":500,"message":"Context size has been exceeded."}
```

Measured, same server, same model:

| Prompt size | `-np 4` (default) | `-np 1` |
|-------------|-------------------|---------|
| 3,000 words | HTTP 200 | HTTP 200 |
| 5,000 words | **HTTP 500** | HTTP 200 |
| 7,000 words | **HTTP 500** | HTTP 200 |
| 8,000 words | **HTTP 500** | HTTP 500 (genuinely over budget) |

`--parallel 1` gives up request concurrency in exchange for the full context
being available to Hindsight. SentryMind already serialises analysis through a
worker pool and a bounded queue, so this does not reduce throughput.

### 4.3 Configuration Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `--ctx-size` | 8192 | Full context window (tokens) |
| `--parallel` | 1 | **Critical** — one slot so Hindsight gets the whole window |
| `--n-gpu-layers` | 99 | Offload all layers to GPU |
| `--batch-size` | 512 | Prompt batch size |
| `--ubatch-size` | 512 | Microbatch size |
| `--threads` | 6 | CPU threads (leaves 6 for system) |
| `--host` | 127.0.0.1 | Bind to localhost (security) |
| `--port` | 1234 | OpenAI-compatible API port |

### 4.4 Memory Usage (measured)

| Component | VRAM | RAM |
|-----------|------|-----|
| Model weights (Q4_K_M) | ~1.9 GB | ~2.1 GB |
| KV cache (8,192 ctx, 1 slot) | ~0.27 GB | ~0.2 GB |
| **Total (measured via `/sys/class/drm/card1/.../mem_info_vram_used`)** | **2.17 GB** | **594 MB RSS** |
| **Headroom on 3.98 GB card** | **1.81 GB** | — |

The previous estimate of "~6.0 GB VRAM for an 8,192 context" in this document
was wrong. Qwen2.5-3B uses grouped-query attention, so its KV cache is small
enough that the full 8,192-token context stays on the GPU.

### 4.5 Context Size Options

| Context | `--parallel 1` | VRAM (measured/est.) | Verdict |
|---------|----------------|---------------------|---------|
| 2048 | works | ~1.95 GB | Fails Hindsight — extraction prompts exceed it |
| 4096 | works | ~2.05 GB | Fails reflect; marginal for extraction |
| 8192 | works | **2.17 GB** | ✅ **Use this** — supports extraction and reflect |
| 16384 | works | ~2.45 GB (est.) | Fits VRAM but slows generation; unnecessary today |

---

## 5. Agent Configuration

### 5.1 Environment Variables

```bash
# Model settings
export SENTRYMIND_INFERENCE_MODEL="qwen2.5-3b-instruct"
export SENTRYMIND_MODEL_PATH="models/Qwen2.5-3B-Instruct-Q4_K_M.gguf"
export SENTRYMIND_INFERENCE_URL="http://127.0.0.1:1234/v1"

# Inference parameters
export SENTRYMIND_CONTEXT_SIZE=2048
export SENTRYMIND_GPU_LAYERS=99
export SENTRYMIND_MAX_OUTPUT_TOKENS=512
export SENTRYMIND_TEMPERATURE=0.2
export SENTRYMIND_REQUEST_TIMEOUT=60

# Agent behavior
export SENTRYMIND_MAX_LOG_LENGTH=8000
export SENTRYMIND_MAX_RECALL_RESULTS=3
export SENTRYMIND_MAX_RECALL_TOKENS=500

# GPU selection
export SENTRYMIND_VULKAN_DEVICE=1
```

### 5.2 Temperature Setting

**Selected:** 0.2 (low)

**Rationale:** Lower temperature produces more deterministic, reproducible output — critical for hackathon demonstrations where the same incident should produce the same analysis.

---

## 6. CPU Fallback

If Vulkan is unstable, the server can run on CPU only:

```bash
/tmp/opencode/llama.cpp/build/bin/llama-server \
  -m /home/knk/SentryMind/models/Qwen2.5-3B-Instruct-Q4_K_M.gguf \
  --host 127.0.0.1 \
  --port 1234 \
  --ctx-size 2048 \
  --n-gpu-layers 0 \
  --threads 12
```

**CPU Performance:** ~5-10 tokens/sec (vs ~40 on GPU) — significantly slower but functional.

---

## 7. Troubleshooting

### 7.1 Vulkan Not Detected

```bash
# Check Vulkan installation
vulkaninfo --summary

# Check ICD loader
ls /usr/share/vulkan/icd.d/

# Check RADV driver
pacman -Q | grep vulkan-radeon
```

### 7.2 Out of Memory

```bash
# Reduce context size
export SENTRYMIND_CONTEXT_SIZE=1024

# Or reduce GPU layers
--n-gpu-layers 50  # Partial offload
```

### 7.3 Server Won't Start

```bash
# Check if port is in use
lsof -i :1234

# Check model file
ls -la models/Qwen2.5-3B-Instruct-Q4_K_M.gguf

# Check server logs
tail -f /tmp/opencode/llama-server.log
```
