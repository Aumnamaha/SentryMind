import sys
import os
import json
import pytest

# Add project root directory to sys.path for relative imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import HINDSIGHT_BANK_ID
from agent.core import SentryMindAgent

def test_config_loading():
    assert HINDSIGHT_BANK_ID == "sentrymind-devops"

def test_synthetic_data_parsing():
    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "incident_logs.json")
    assert os.path.exists(data_path)
    with open(data_path, "r") as f:
        incidents = json.load(f)
    assert len(incidents) >= 3
    assert incidents[0]["id"] == "INC-001"

def test_agent_instantiation():
    agent = SentryMindAgent()
    res = agent.analyze_log("FATAL: remaining connection slots", use_memory=False)
    assert res["use_memory"] is False
    assert "raw_log" in res
