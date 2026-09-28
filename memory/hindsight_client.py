"""SentryMemoryManager — official Hindsight API with local fallback.

Supports:
- Official Vectorize Hindsight server (persistent, semantic search)
- Local in-memory fallback (non-persistent, keyword matching)
- Clear backend provenance tracking
"""

import json
import re
from threading import RLock
from typing import Any

import requests

from config import HINDSIGHT_API_URL, HINDSIGHT_BANK_ID
from inference_config import HINDSIGHT_REFLECT_TIMEOUT, HINDSIGHT_TIMEOUT


class SentryMemoryManager:
    def __init__(
        self,
        base_url: str | None = None,
        bank_id: str | None = None,
        timeout: int = HINDSIGHT_TIMEOUT,
        reflect_timeout: int = HINDSIGHT_REFLECT_TIMEOUT,
    ):
        self.base_url = (base_url or HINDSIGHT_API_URL).rstrip("/")
        self.bank_id = bank_id or HINDSIGHT_BANK_ID
        self.timeout = timeout
        # Reflect is an LLM synthesis over the whole bank and takes far longer
        # than retain/recall, so it gets its own budget.
        self.reflect_timeout = reflect_timeout
        self.local_store: list[dict[str, Any]] = []
        self._store_lock = RLock()
        self._bank_ready: set[str] = set()

    def _ensure_bank(self, force: bool = False) -> bool:
        """Best-effort provisioning of the memory bank.

        Returns True when the bank is known to exist (either because we just
        created it, or because it was already cached). It never gates retention
        on its own: the authoritative signal is the retain response, which
        reports 404 when the bank is genuinely absent. Treating a failed
        provisioning attempt as fatal would misreport a transient outage as
        "bank missing".
        """
        if not force and self.bank_id in self._bank_ready:
            return True
        try:
            resp = requests.put(
                f"{self.base_url}/v1/default/banks/{self.bank_id}",
                json={},
                timeout=self.timeout,
            )
        except requests.RequestException:
            # Service unreachable — retain will fall back on its own.
            return False
        if resp.status_code in (200, 201, 409):
            self._bank_ready.add(self.bank_id)
            return True
        return False

    def retain_incident(
        self, content: str, context: str = "incident_postmortem"
    ) -> dict[str, Any]:
        entry = {"content": content, "context": context, "bank_id": self.bank_id}

        # Ensure content is a string
        if not isinstance(content, str):
            content = str(content)
        request_data = json.dumps(
            {
                "files_metadata": [
                    {
                        "context": context,
                        "metadata": {"source": "sentrymind", "context": context},
                    }
                ]
            }
        )
        url = f"{self.base_url}/v1/default/banks/{self.bank_id}/files/retain"

        for attempt in (1, 2):
            try:
                from io import BytesIO

                # A fresh BytesIO per attempt: the first read drains it.
                file_obj = BytesIO(content.encode("utf-8"))
                response = requests.post(
                    url,
                    files={"files": ("incident.txt", file_obj, "text/plain")},
                    data={"request": request_data},
                    timeout=self.timeout,
                )
                if response.status_code in (200, 201, 202):
                    result = response.json()
                    if isinstance(result, dict):
                        self._bank_ready.add(self.bank_id)
                        return {
                            **result,
                            "backend": "hindsight",
                            "status": "retained",
                        }
                if response.status_code == 404 and attempt == 1:
                    # The official API rejects retain with 404 until the bank
                    # has been provisioned. Provision, then retry once.
                    self._ensure_bank(force=True)
                    continue
            except (requests.RequestException, ValueError, AttributeError, TypeError):
                pass
            break

        return self._retain_local(entry)

    def _retain_local(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Store an incident in the non-persistent in-process fallback."""
        with self._store_lock:
            if not any(
                item["content"] == entry["content"]
                and item["context"] == entry["context"]
                for item in self.local_store
            ):
                self.local_store.append(entry)
        return {
            "status": "retained_locally",
            "entry": entry,
            "backend": "local_fallback",
        }

    def recall_resolution(self, query: str) -> dict[str, Any]:
        if not isinstance(query, str):
            query = str(query)

        # Try official Hindsight API
        try:
            url = f"{self.base_url}/v1/default/banks/{self.bank_id}/memories/recall"
            response = requests.post(
                url,
                json={"query": query},
                timeout=self.timeout,
            )
            if response.status_code == 200:
                result = response.json()
                # Strictly validate the official envelope. A malformed 200
                # response must fall through to the local fallback rather than
                # being reported as a successful official recall.
                if isinstance(result, dict) and isinstance(result.get("results"), list):
                    memories = result["results"]
                    results: list[str] = []
                    for mem in memories:
                        if isinstance(mem, dict):
                            # Official Hindsight uses "text"; older mock used
                            # "content". Accept either.
                            value = mem.get("text", mem.get("content"))
                            if isinstance(value, str):
                                results.append(value)
                        elif isinstance(mem, str):
                            results.append(mem)
                    return {
                        "results": results,
                        "status": "recalled",
                        "backend": "hindsight",
                        "raw_response": result,
                    }
        except (requests.RequestException, ValueError):
            pass

        # Local keyword matching fallback
        stop_words = {
            "the",
            "and",
            "for",
            "with",
            "from",
            "that",
            "this",
            "are",
            "was",
            "has",
            "have",
            "not",
            "but",
            "all",
            "can",
            "had",
            "her",
            "one",
            "our",
            "out",
            "day",
            "get",
            "him",
            "his",
            "how",
            "its",
            "may",
            "new",
            "now",
            "old",
            "see",
            "two",
            "way",
            "who",
            "did",
            "let",
            "put",
            "say",
            "she",
            "too",
            "use",
        }
        query_words = {
            w.lower()
            for w in re.findall(r"[a-zA-Z0-9_]+", query)
            if len(w) > 3 and w.lower() not in stop_words
        }
        matched = []
        if not query_words:
            return {
                "results": [],
                "status": "recalled_locally",
                "backend": "local_fallback",
            }
        with self._store_lock:
            for item in self.local_store:
                content_words = set(
                    re.findall(r"[a-zA-Z0-9_]+", item["content"].lower())
                )
                overlap = len(query_words & content_words)
                threshold = (
                    1 if len(query_words) == 1 else (3 * len(query_words) + 3) // 4
                )
                if overlap >= threshold:
                    matched.append(item["content"])
        return {
            "results": matched,
            "status": "recalled_locally",
            "backend": "local_fallback",
        }

    def reflect_patterns(self, query: str) -> dict[str, Any]:
        # Try official Hindsight API
        try:
            url = f"{self.base_url}/v1/default/banks/{self.bank_id}/reflect"
            response = requests.post(
                url,
                json={"query": query},
                timeout=self.reflect_timeout,
            )
            if response.status_code == 200:
                result = response.json()
                # Official Hindsight returns the synthesis under "text".
                if isinstance(result, dict):
                    text = result.get("text")
                    if not isinstance(text, str):
                        # Legacy mock shape
                        text = result.get("response", result.get("reflection", ""))
                    if isinstance(text, str) and text.strip():
                        return {
                            "reflection": text,
                            "status": "reflected",
                            "backend": "hindsight",
                            "usage": result.get("usage"),
                            "raw_response": result,
                        }
        except (requests.RequestException, ValueError):
            pass

        # Local fallback
        with self._store_lock:
            incidents = list(self.local_store)
        if not incidents:
            return {
                "reflection": "No incidents in memory yet.",
                "status": "reflected_locally",
                "backend": "local_fallback",
            }

        all_text = " ".join(item["content"].lower() for item in incidents)
        keywords = [
            "connection",
            "timeout",
            "memory",
            "cache",
            "oom",
            "fatal",
            "error",
            "crash",
        ]
        found = [kw for kw in keywords if kw in all_text]
        reflection = (
            f"Observed patterns: {', '.join(found)}."
            if found
            else "No recurring patterns detected yet."
        )
        return {
            "reflection": reflection,
            "status": "reflected_locally",
            "backend": "local_fallback",
        }

    def backend_status(self) -> dict[str, Any]:
        """Report the verified status of the memory backend."""
        status: dict[str, Any] = {
            "configured_backend": "hindsight",
            "configured_url": self.base_url,
            "bank_id": self.bank_id,
            "local_store_size": len(self.local_store),
        }
        try:
            # GET /health is the service's own readiness probe and answers in
            # ~2 ms. It must not be a recall: recall contends for the single
            # LLM inference slot with fact extraction and can take many seconds,
            # which previously produced false "unreachable" reports.
            resp = requests.get(f"{self.base_url}/health", timeout=3)
            if resp.status_code == 200:
                status["hindsight_reachable"] = True
                status["active_backend"] = "hindsight"
                try:
                    health = resp.json()
                except ValueError:
                    health = {}
                if isinstance(health, dict):
                    status["hindsight_health"] = health.get("status", "unknown")
                    status["database"] = health.get("database", "unknown")
            else:
                status["hindsight_reachable"] = False
                status["active_backend"] = "local_fallback"
                status["hindsight_error"] = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            status["hindsight_reachable"] = False
            status["active_backend"] = "local_fallback"
            status["hindsight_error"] = str(exc)
        return status
