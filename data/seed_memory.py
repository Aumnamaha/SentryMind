import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from memory.hindsight_client import SentryMemoryManager


def seed_hindsight_bank():
    manager = SentryMemoryManager()
    data_path = os.path.join(os.path.dirname(__file__), "incident_logs.json")

    with open(data_path, "r") as f:
        incidents = json.load(f)

    print(f"Seeding {len(incidents)} incident post-mortems locally...")
    for item in incidents:
        content = f"Incident: {item['title']}. Error Log: {item['error_log']}. Root Cause: {item['root_cause']}. Verified Fix: {item['resolution']}"
        res = manager.retain_incident(content=content, context="production_postmortem")
        print(f"Retained [{item['id']}]: {res.get('status')}")

    print("Local memory seeding complete!")


if __name__ == "__main__":
    seed_hindsight_bank()
