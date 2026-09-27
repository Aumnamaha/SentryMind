import requests
from typing import Optional, Dict, Any, List
from config import HINDSIGHT_API_URL, HINDSIGHT_BANK_ID


class SentryMemoryManager:
    def __init__(self, base_url: Optional[str] = None, bank_id: Optional[str] = None):
        self.base_url = base_url or HINDSIGHT_API_URL
        self.bank_id = bank_id or HINDSIGHT_BANK_ID
        self.local_store: List[Dict[str, Any]] = []

    def retain_incident(self, content: str, context: str = "incident_postmortem") -> Dict[str, Any]:
        entry = {"content": content, "context": context, "bank_id": self.bank_id}

        # Try local Hindsight API endpoint
        try:
            url = f"{self.base_url}/banks/{self.bank_id}/retain"
            response = requests.post(url, json={"content": content, "context": context}, timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass

        # Fallback to local in-memory store if standalone instance isn't active
        self.local_store.append(entry)
        return {"status": "retained_locally", "entry": entry}

    def recall_resolution(self, query: str) -> Dict[str, Any]:
        # Try local Hindsight API endpoint
        try:
            url = f"{self.base_url}/banks/{self.bank_id}/recall"
            response = requests.post(url, json={"query": query}, timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass

        # Local keyword matching fallback — match on significant words only
        stop_words = {"the", "and", "for", "with", "from", "that", "this", "are", "was", "has", "have", "not", "but", "all", "can", "had", "her", "was", "one", "our", "out", "day", "get", "has", "him", "his", "how", "its", "may", "new", "now", "old", "see", "two", "way", "who", "did", "its", "let", "put", "say", "she", "too", "use"}
        query_words = [w.lower() for w in query.split() if len(w) > 3 and w.lower() not in stop_words]
        matched = []
        for item in self.local_store:
            content_lower = item["content"].lower()
            if any(w in content_lower for w in query_words):
                matched.append(item["content"])
        return {"status": "recalled_locally", "results": matched}

    def reflect_patterns(self, query: str) -> Dict[str, Any]:
        if not self.local_store:
            return {"status": "reflected_locally", "reflection": "No incidents in memory yet."}

        # Count keyword frequency across all stored incidents
        all_text = " ".join(item["content"].lower() for item in self.local_store)
        keywords = ["connection", "timeout", "memory", "cache", "oom", "fatal", "error", "crash"]
        found = [kw for kw in keywords if kw in all_text]
        reflection = (
            f"Observed patterns: {', '.join(found)}."
            if found
            else "No recurring patterns detected yet."
        )
        return {"status": "reflected_locally", "reflection": reflection}
