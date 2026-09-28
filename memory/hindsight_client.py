import re
from threading import RLock
from typing import Any

import requests

from config import HINDSIGHT_API_URL, HINDSIGHT_BANK_ID


class SentryMemoryManager:
    def __init__(self, base_url: str | None = None, bank_id: str | None = None):
        self.base_url = base_url or HINDSIGHT_API_URL
        self.bank_id = bank_id or HINDSIGHT_BANK_ID
        self.local_store: list[dict[str, Any]] = []
        self._store_lock = RLock()

    def retain_incident(
        self, content: str, context: str = "incident_postmortem"
    ) -> dict[str, Any]:
        entry = {"content": content, "context": context, "bank_id": self.bank_id}

        # Try local Hindsight API endpoint
        try:
            url = f"{self.base_url}/banks/{self.bank_id}/retain"
            response = requests.post(
                url, json={"content": content, "context": context}, timeout=5
            )
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, dict):
                    return result
        except (requests.RequestException, ValueError):
            pass

        # Fallback to local in-memory store if standalone instance isn't active
        with self._store_lock:
            if not any(
                item["content"] == content and item["context"] == context
                for item in self.local_store
            ):
                self.local_store.append(entry)
        return {"status": "retained_locally", "entry": entry}

    def recall_resolution(self, query: str) -> dict[str, Any]:
        if not isinstance(query, str):
            query = str(query)
        # Try local Hindsight API endpoint
        try:
            url = f"{self.base_url}/banks/{self.bank_id}/recall"
            response = requests.post(url, json={"query": query}, timeout=5)
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, dict) and isinstance(result.get("results"), list):
                    return result
        except (requests.RequestException, ValueError):
            pass

        # Local keyword matching fallback — match on significant words only
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
            return {"status": "recalled_locally", "results": []}
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
        return {"status": "recalled_locally", "results": matched}

    def reflect_patterns(self, query: str) -> dict[str, Any]:
        with self._store_lock:
            incidents = list(self.local_store)
        if not incidents:
            return {
                "status": "reflected_locally",
                "reflection": "No incidents in memory yet.",
            }

        # Count keyword frequency across all stored incidents
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
        return {"status": "reflected_locally", "reflection": reflection}

    def backend_status(self) -> dict[str, Any]:
        """Report the verified status of the memory backend.

        Performs a live connectivity check against the Hindsight API and
        reports whether data is actually flowing through it or falling
        back to the local in-memory store.
        """
        status: dict[str, Any] = {
            "configured_backend": "hindsight",
            "configured_url": self.base_url,
            "bank_id": self.bank_id,
            "local_store_size": len(self.local_store),
        }
        try:
            # Lightweight probe: attempt to recall an empty query
            resp = requests.post(
                f"{self.base_url}/banks/{self.bank_id}/recall",
                json={"query": "__health_check__"},
                timeout=3,
            )
            if resp.status_code == 200:
                status["hindsight_reachable"] = True
                status["active_backend"] = "hindsight"
            else:
                status["hindsight_reachable"] = False
                status["active_backend"] = "local_fallback"
                status["hindsight_error"] = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            status["hindsight_reachable"] = False
            status["active_backend"] = "local_fallback"
            status["hindsight_error"] = str(exc)
        return status
