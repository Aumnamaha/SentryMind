import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import SentryMindAgent


def test_before_vs_after_memory_comparison():
    agent = SentryMindAgent()
    sample_log = "FATAL: remaining connection slots are reserved for non-replication superuser connections"

    # Before Memory
    res_no_mem = agent.analyze_log(sample_log, use_memory=False)
    assert res_no_mem["use_memory"] is False
    assert "Low" in res_no_mem["confidence"]

    # Seed explicit item into local memory manager to guarantee recall
    agent.memory.retain_incident(
        "FATAL: remaining connection slots -> Run scripts/flush_pool.sh"
    )

    # After Memory
    res_with_mem = agent.analyze_log(sample_log, use_memory=True)
    assert res_with_mem["use_memory"] is True
    assert len(res_with_mem["recalled_context"]) > 0


def test_resolve_and_retain_execution():
    agent = SentryMindAgent()
    res = agent.resolve_and_retain(
        "INC-999", "ERR_MEM_LEAK", "Unbounded cache growth", "Purge LRU cache"
    )
    assert res["status"] == "success"
    assert "INC-999" in res["retained_content"]
