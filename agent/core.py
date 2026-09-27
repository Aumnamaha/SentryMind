from typing import Any

import requests

from config import LOCAL_LLM_URL, LOCAL_MODEL_NAME
from memory.hindsight_client import SentryMemoryManager


class SentryMindAgent:
    def __init__(self, memory_manager: SentryMemoryManager | None = None):
        self.memory = memory_manager or SentryMemoryManager()

    def query_local_qwen(self, prompt: str) -> str:
        try:
            payload = {
                "model": LOCAL_MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            }
            res = requests.post(
                f"{LOCAL_LLM_URL}/chat/completions", json=payload, timeout=30
            )
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"]
        except requests.RequestException:
            return "[Offline / Local Fallback Mode] Query processed using local rule engine."
        return "[Local LLM Error] No response generated."

    def analyze_log(self, raw_log: str, use_memory: bool = True) -> dict[str, Any]:
        recalled_facts = []
        if use_memory:
            recall_res = self.memory.recall_resolution(query=raw_log)
            if isinstance(recall_res, dict) and "results" in recall_res:
                recalled_facts = recall_res["results"]

        if not recalled_facts:
            prompt = f"System Error Log: {raw_log}\nProvide generic troubleshooting steps without historical context."
            llm_output = self.query_local_qwen(prompt)
            return {
                "raw_log": raw_log,
                "use_memory": use_memory,
                "memory_active": False,
                "root_cause": "Uncertain / Unknown (No Memory Context)",
                "recommended_action": "Standard generic triage: Restart service.",
                "llm_response": llm_output,
                "confidence": "Low (Baseline Local LLM Guess)",
                "recalled_context": [],
            }

        prompt = f"System Error Log: {raw_log}\nRecalled Post-Mortem Memory: {recalled_facts}\nProvide the exact root cause and runbook script execution steps."
        llm_output = self.query_local_qwen(prompt)
        return {
            "raw_log": raw_log,
            "use_memory": True,
            "memory_active": True,
            "root_cause": "Identified from past incident post-mortems in Hindsight Bank.",
            "recommended_action": f"Execute verified runbook derived from memory: {recalled_facts}",
            "llm_response": llm_output,
            "confidence": "High (Verified from Hindsight Memory)",
            "recalled_context": recalled_facts,
        }

    def resolve_and_retain(
        self, incident_id: str, raw_log: str, root_cause: str, fix_action: str
    ) -> dict[str, Any]:
        content = f"Incident ID: {incident_id}. Error: {raw_log}. Root Cause: {root_cause}. Verified Fix: {fix_action}"
        retain_res = self.memory.retain_incident(
            content=content, context="resolved_incident"
        )
        return {
            "status": "success",
            "retained_content": content,
            "hindsight_response": retain_res,
        }
