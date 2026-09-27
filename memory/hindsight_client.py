import os
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
            response = requests.post(url, json={"content": content, "context": context}, timeout=2)
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
            response = requests.post(url, json={"query": query}, timeout=2)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass

        # Local semantic matching fallback
        matched = [
            item["content"] for item in self.local_store 
            if any(word.lower() in item["content"].lower() for word in query.split() if len(word) > 3)
        ]
        return {"status": "recalled_locally", "results": matched}

    def reflect_patterns(self, query: str) -> Dict[str, Any]:
        return {"status": "reflected_locally", "reflection": "Repeated connection and cache failure patterns observed."}
