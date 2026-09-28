#!/bin/bash
# SentryMind Demo Startup Script
# Starts the local inference server, the official Vectorize Hindsight memory
# service, and the Streamlit UI for hackathon demonstration.
#
# Usage:
#   ./start_demo.sh              # Start all services
#   ./start_demo.sh --stop       # Stop all services
#   ./start_demo.sh --status     # Check service status
#   ./start_demo.sh --cpu        # Start with CPU fallback (no GPU)
#   ./start_demo.sh --no-memory  # Start without Hindsight (local fallback only)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_PATH="${SCRIPT_DIR}/models/Qwen2.5-3B-Instruct-Q4_K_M.gguf"
LLAMA_SERVER="/tmp/opencode/llama.cpp/build/bin/llama-server"
LLAMA_LOG="/tmp/opencode/llama-server.log"
HINDSIGHT_LOG="/tmp/opencode/hindsight-official.log"
STREAMLIT_PORT=8501
LLAMA_PORT=1234
HINDSIGHT_PORT=8888

# Hindsight's fact-extraction prompt needs ~2.4k tokens and reflect needs ~7.8k.
# llama-server splits --ctx-size across its default 4 slots, so --parallel 1 is
# mandatory; without it every extraction fails with "Context size has been
# exceeded." See OPTIMIZATION_BASELINE.md section 2.1.
CONTEXT_SIZE=8192
PARALLEL_SLOTS=1

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_model() {
    if [ ! -f "$MODEL_PATH" ]; then
        log_error "Model not found: $MODEL_PATH"
        log_info "Download it with:"
        log_info "  mkdir -p ${SCRIPT_DIR}/models"
        log_info "  wget -O $MODEL_PATH https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
        exit 1
    fi
    log_info "Model found: $MODEL_PATH"
}

check_llama_server() {
    if [ ! -f "$LLAMA_SERVER" ]; then
        log_error "llama-server not found: $LLAMA_SERVER"
        log_info "Build it with:"
        log_info "  git clone --depth 1 --branch v0.5.0 https://github.com/ggml-org/llama.cpp.git /tmp/opencode/llama.cpp"
        log_info "  cd /tmp/opencode/llama.cpp && cmake -B build -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release && cmake --build build --config Release -j 12"
        exit 1
    fi
    log_info "llama-server found: $LLAMA_SERVER"
}

start_llama() {
    local gpu_flag="--n-gpu-layers 99"
    if [ "$1" = "--cpu" ]; then
        gpu_flag="--n-gpu-layers 0"
        log_warn "Using CPU fallback (slower)"
    fi

    if lsof -i :$LLAMA_PORT >/dev/null 2>&1; then
        log_warn "Port $LLAMA_PORT already in use — llama-server may already be running"
        return
    fi

    log_info "Starting llama-server on port $LLAMA_PORT..."
    cd "$SCRIPT_DIR/models"
    nohup "$LLAMA_SERVER" \
        -m "$(basename "$MODEL_PATH")" \
        --host 127.0.0.1 \
        --port $LLAMA_PORT \
        --ctx-size $CONTEXT_SIZE \
        --parallel $PARALLEL_SLOTS \
        $gpu_flag \
        --batch-size 512 \
        --ubatch-size 512 \
        --threads 6 \
        > "$LLAMA_LOG" 2>&1 &

    local pid=$!
    log_info "llama-server started (PID: $pid)"
    log_info "Waiting for server to be ready..."

    local attempts=0
    while [ $attempts -lt 60 ]; do
        if curl -s "http://127.0.0.1:$LLAMA_PORT/v1/models" >/dev/null 2>&1; then
            log_info "llama-server is ready!"
            return
        fi
        sleep 1
        attempts=$((attempts + 1))
    done

    log_error "llama-server failed to start within 60 seconds"
    log_info "Check logs: tail -20 $LLAMA_LOG"
    exit 1
}

start_hindsight() {
    if [ "$1" = "--no-memory" ]; then
        log_warn "Skipping Hindsight — memory will use the non-persistent local fallback"
        return
    fi

    if lsof -i :$HINDSIGHT_PORT >/dev/null 2>&1; then
        log_warn "Port $HINDSIGHT_PORT already in use — Hindsight may already be running"
        return
    fi

    if ! .venv/bin/python -c "import hindsight_api" >/dev/null 2>&1; then
        log_error "hindsight-api-slim is not installed"
        log_info "Install it with:"
        log_info "  .venv/bin/pip install 'hindsight-api-slim[embedded-db]'"
        log_info "  .venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu"
        log_info "  .venv/bin/pip install sentence-transformers"
        log_warn "Continuing without Hindsight (memory will use local fallback)"
        return
    fi

    log_info "Starting official Hindsight on port $HINDSIGHT_PORT..."
    cd "$SCRIPT_DIR"
    nohup bash "${SCRIPT_DIR}/start_hindsight.sh" > "$HINDSIGHT_LOG" 2>&1 &

    log_info "Hindsight started (PID: $!)"
    log_info "Waiting for Hindsight to be ready..."

    local attempts=0
    while [ $attempts -lt 180 ]; do
        if curl -sf "http://127.0.0.1:$HINDSIGHT_PORT/health" >/dev/null 2>&1; then
            log_info "Hindsight is ready and healthy!"
            return
        fi
        sleep 1
        attempts=$((attempts + 1))
    done

    log_error "Hindsight failed to become healthy within 180 seconds"
    log_info "Check logs: tail -20 $HINDSIGHT_LOG"
}

start_streamlit() {
    if lsof -i :$STREAMLIT_PORT >/dev/null 2>&1; then
        log_warn "Port $STREAMLIT_PORT already in use — Streamlit may already be running"
        return
    fi

    log_info "Starting Streamlit UI on port $STREAMLIT_PORT..."
    cd "$SCRIPT_DIR"
    nohup .venv/bin/streamlit run app.py --server.port $STREAMLIT_PORT \
        > /tmp/opencode/streamlit.log 2>&1 &

    local pid=$!
    log_info "Streamlit started (PID: $pid)"
    log_info "Open http://localhost:$STREAMLIT_PORT in your browser"
}

stop_services() {
    log_info "Stopping services..."

    if lsof -i :$LLAMA_PORT >/dev/null 2>&1; then
        kill $(lsof -t -i :$LLAMA_PORT) 2>/dev/null || true
        log_info "llama-server stopped"
    fi

    if lsof -i :$HINDSIGHT_PORT >/dev/null 2>&1; then
        kill $(lsof -t -i :$HINDSIGHT_PORT) 2>/dev/null || true
        log_info "Hindsight stopped (embedded PostgreSQL data is preserved in ~/.pg0)"
    fi

    if lsof -i :$STREAMLIT_PORT >/dev/null 2>&1; then
        kill $(lsof -t -i :$STREAMLIT_PORT) 2>/dev/null || true
        log_info "Streamlit stopped"
    fi

    log_info "All services stopped"
}

status_services() {
    echo "=== SentryMind Service Status ==="

    if lsof -i :$LLAMA_PORT >/dev/null 2>&1; then
        echo -e "llama-server: ${GREEN}running${NC}"
    else
        echo -e "llama-server: ${RED}stopped${NC}"
    fi

    if lsof -i :$HINDSIGHT_PORT >/dev/null 2>&1; then
        local hs=$(curl -s --max-time 3 "http://127.0.0.1:$HINDSIGHT_PORT/health" 2>/dev/null | grep -o '"status":"[a-z]*"' | cut -d'"' -f4)
        if [ "$hs" = "healthy" ]; then
            echo -e "Hindsight:    ${GREEN}healthy${NC} (official Vectorize, persistent)"
        else
            echo -e "Hindsight:    ${YELLOW}running but not healthy${NC}"
        fi
    else
        echo -e "Hindsight:    ${RED}stopped${NC} (memory falls back to non-persistent local store)"
    fi

    if lsof -i :$STREAMLIT_PORT >/dev/null 2>&1; then
        echo -e "Streamlit:    ${GREEN}running${NC}"
    else
        echo -e "Streamlit:    ${RED}stopped${NC}"
    fi

    if [ -f "$MODEL_PATH" ]; then
        echo -e "Model:         ${GREEN}present${NC}"
    else
        echo -e "Model:         ${RED}missing${NC}"
    fi

    local vram_used=$(cat /sys/class/drm/card1/device/mem_info_vram_used 2>/dev/null | awk '{printf "%.2f", $1/1024/1024/1024}')
    local vram_total=$(cat /sys/class/drm/card1/device/mem_info_vram_total 2>/dev/null | awk '{printf "%.2f", $1/1024/1024/1024}')
    echo -e "VRAM:          ${vram_used}GB / ${vram_total}GB"
}

case "${1:-}" in
    --stop)
        stop_services
        ;;
    --status)
        status_services
        ;;
    --cpu)
        check_model
        check_llama_server
        start_llama --cpu
        start_hindsight
        start_streamlit
        ;;
    --no-memory)
        check_model
        check_llama_server
        start_llama
        start_streamlit
        ;;
    *)
        check_model
        check_llama_server
        start_llama
        start_hindsight
        start_streamlit
        echo ""
        log_info "SentryMind is starting!"
        log_info "  Inference: http://127.0.0.1:$LLAMA_PORT"
        log_info "  Memory:    http://127.0.0.1:$HINDSIGHT_PORT  (official Vectorize Hindsight)"
        log_info "  UI:        http://localhost:$STREAMLIT_PORT"
        echo ""
        log_info "Run '$0 --status' to check status"
        log_info "Run '$0 --stop' to stop all services"
        ;;
esac
