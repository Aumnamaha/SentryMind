"""FastAPI backend for SentryMind — async inference with bounded queues."""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from inference_config import (
    INFERENCE_MODEL,
    INFERENCE_URL,
    MAX_OUTPUT_TOKENS,
    TEMPERATURE,
)
from pydantic import BaseModel, Field

# Bounded request queue — prevents VRAM exhaustion from overlapping requests
_inference_semaphore = asyncio.Semaphore(1)
_request_queue_size = 0
_max_queue_size = 5


class AnalyzeRequest(BaseModel):
    log: str = Field(..., description="Incident log to analyze")
    use_memory: bool = Field(True, description="Whether to use historical memory")


class AnalyzeResponse(BaseModel):
    raw_log: str
    use_memory: bool
    memory_active: bool
    root_cause: str
    recommended_action: str
    llm_response: str
    confidence: str
    recalled_context: list[str] = []
    evidence: list[str] = []
    uncertainty: str = ""
    next_checks: list[str] = []
    latency_ms: float = 0.0


class HealthResponse(BaseModel):
    status: str
    inference_available: bool = False
    queue_size: int = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    yield


app = FastAPI(title="SentryMind API", version="0.2.0", lifespan=lifespan)


@app.get("/")
async def read_root():
    return {"status": "ok", "message": "SentryMind Backend API is running!"}


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check with inference availability."""
    inference_available = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.get(f"{INFERENCE_URL}/health")
            inference_available = True
    except (httpx.RequestError, OSError):
        pass
    return HealthResponse(
        status="healthy",
        inference_available=inference_available,
        queue_size=_request_queue_size,
    )


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_incident(request: AnalyzeRequest):
    """Analyze an incident log using the local LLM.

    Uses a bounded semaphore to prevent overlapping inference requests
    from exhausting VRAM.
    """
    global _request_queue_size

    if _request_queue_size >= _max_queue_size:
        raise HTTPException(
            status_code=503,
            detail="Server is at capacity. Please retry in a few seconds.",
        )

    _request_queue_size += 1
    start_time = time.perf_counter()

    try:
        async with _inference_semaphore:
            result = await _run_inference(request.log, request.use_memory)
    except (httpx.RequestError, OSError, ValueError, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {e!s}")
    finally:
        _request_queue_size -= 1

    latency_ms = (time.perf_counter() - start_time) * 1000
    result["latency_ms"] = round(latency_ms, 2)
    return AnalyzeResponse(**result)


async def _run_inference(log: str, use_memory: bool) -> dict[str, Any]:
    """Run inference without blocking the event loop."""
    # Run the CPU-bound agent analysis in a thread pool
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _analyze_sync, log, use_memory)
    return result


def _analyze_sync(log: str, use_memory: bool) -> dict[str, Any]:
    """Synchronous analysis (runs in thread pool)."""
    from agent.core import SentryMindAgent

    agent = SentryMindAgent()
    return agent.analyze_log(log, use_memory=use_memory)


@app.get("/config")
async def get_config():
    """Get current inference configuration (non-sensitive)."""
    return {
        "model": INFERENCE_MODEL,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "temperature": TEMPERATURE,
        "max_queue_size": _max_queue_size,
    }
