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
  --ctx-size 2048 \
  --n-gpu-layers 99 \
  --batch-size 128 \
  --ubatch-size 128 \
  --threads 6
```

### 4.2 Configuration Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `--ctx-size` | 2048 | Context window (tokens). 2048 fits in 4GB VRAM with headroom |
| `--n-gpu-layers` | 99 | Offload all layers to GPU |
| `--batch-size` | 128 | Prompt batch size |
| `--ubatch-size` | 128 | Microbatch size |
| `--threads` | 6 | CPU threads (leaves 6 for system) |
| `--host` | 127.0.0.1 | Bind to localhost (security) |
| `--port` | 1234 | OpenAI-compatible API port |

### 4.3 Memory Usage

| Component | VRAM | RAM |
|-----------|------|-----|
| Model weights (Q4_K_M) | ~1.9 GB | ~2.1 GB |
| KV cache (2048 ctx) | ~0.2 GB | ~0.2 GB |
| **Total** | **~2.1 GB** | **~2.3 GB** |
| **Headroom** | **~1.9 GB** | **~13.7 GB** |

### 4.4 Context Size Options

| Context | VRAM Usage | Recommended |
|---------|------------|-------------|
| 2048 | ~2.1 GB | ✅ Yes — fits with headroom |
| 4096 | ~3.5 GB | ⚠️ Risky — may exceed 4GB with overhead |
| 8192 | ~6.0 GB | ❌ No — exceeds 4GB VRAM |

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
