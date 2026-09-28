"""Tests for agent optimization features: truncation, structured output, recall limits."""

import os
import sys
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.core import SentryMindAgent
from memory.hindsight_client import SentryMemoryManager


@pytest.fixture
def offline_manager():
    manager = SentryMemoryManager(base_url="http://unused.invalid")
    with patch(
        "memory.hindsight_client.requests.post",
        side_effect=requests.ConnectionError("offline"),
    ):
        yield manager


@pytest.fixture
def agent(offline_manager):
    ag = SentryMindAgent(offline_manager)
    with patch.object(ag, "query_local_qwen", return_value="mocked"):
        yield ag


class TestLogTruncation:
    """Bounded incident-log selection and truncation."""

    def test_short_log_not_truncated(self, agent):
        log = "ERROR: database connection failed"
        result = agent._truncate_log(log, max_length=1000)
        assert result == log

    def test_long_log_truncated(self, agent):
        log = "ERROR: " + "x" * 10000
        result = agent._truncate_log(log, max_length=1000)
        assert len(result) < len(log)
        assert "truncated" in result

    def test_critical_lines_preserved(self, agent):
        """Critical error lines must never be discarded."""
        lines = [
            "INFO: starting service",
            "ERROR: database connection failed",
            "INFO: retrying",
            "FATAL: out of memory",
            "INFO: cleanup",
        ]
        log = "\n".join(lines) + "\n" + "x" * 10000
        result = agent._truncate_log(log, max_length=200)
        assert "ERROR: database connection failed" in result
        assert "FATAL: out of memory" in result

    def test_oom_lines_preserved(self, agent):
        log = (
            "INFO: normal operation\n" * 100
            + "OOMKilled: container exceeded memory limit"
        )
        result = agent._truncate_log(log, max_length=100)
        assert "OOMKilled" in result

    def test_crash_lines_preserved(self, agent):
        log = "INFO: normal\n" * 100 + "CRASH: segmentation fault"
        result = agent._truncate_log(log, max_length=100)
        assert "CRASH" in result

    def test_empty_log(self, agent):
        result = agent._truncate_log("", max_length=100)
        assert result == ""

    def test_log_exactly_at_limit(self, agent):
        log = "x" * 1000
        result = agent._truncate_log(log, max_length=1000)
        assert result == log


class TestStructuredOutputParsing:
    """Structured output schema parsing."""

    def test_valid_json_parsed(self, agent):
        output = '{"diagnosis": "test", "confidence": "high"}'
        result = agent._parse_structured_output(output)
        assert result is not None
        assert result["diagnosis"] == "test"
        assert result["confidence"] == "high"

    def test_json_with_markdown_fences(self, agent):
        output = '```json\n{"diagnosis": "test", "confidence": "low"}\n```'
        result = agent._parse_structured_output(output)
        assert result is not None
        assert result["diagnosis"] == "test"

    def test_invalid_json_returns_none(self, agent):
        output = "not json at all"
        result = agent._parse_structured_output(output)
        assert result is None

    def test_json_without_diagnosis_returns_none(self, agent):
        output = '{"foo": "bar"}'
        result = agent._parse_structured_output(output)
        assert result is None

    def test_empty_string_returns_none(self, agent):
        result = agent._parse_structured_output("")
        assert result is None

    def test_full_schema_parsed(self, agent):
        output = (
            '{"diagnosis": "db timeout", "evidence": ["line1", "line2"], '
            '"confidence": "medium", "uncertainty": "unknown load", '
            '"next_checks": ["check connections"], "remediation": "restart"}'
        )
        result = agent._parse_structured_output(output)
        assert result is not None
        assert result["diagnosis"] == "db timeout"
        assert result["evidence"] == ["line1", "line2"]
        assert result["confidence"] == "medium"
        assert result["uncertainty"] == "unknown load"
        assert result["next_checks"] == ["check connections"]
        assert result["remediation"] == "restart"


class TestRecallLimiting:
    """Top-k and token budget limits for recalled memories."""

    def test_limit_by_count(self, agent):
        facts = ["fact1", "fact2", "fact3", "fact4", "fact5"]
        result = agent._limit_recall_results(facts, max_results=3, max_tokens=1000)
        assert len(result) == 3

    def test_limit_by_token_budget(self, agent):
        facts = ["x" * 400, "y" * 400, "z" * 400]  # ~100 tokens each
        result = agent._limit_recall_results(facts, max_results=10, max_tokens=150)
        assert len(result) <= 1  # Only first fact fits in 150 tokens

    def test_empty_facts(self, agent):
        result = agent._limit_recall_results([], max_results=3, max_tokens=100)
        assert result == []

    def test_facts_within_limits(self, agent):
        facts = ["short fact 1", "short fact 2"]
        result = agent._limit_recall_results(facts, max_results=5, max_tokens=1000)
        assert len(result) == 2


class TestOptimizedPrompt:
    """Compact prompt with structured output schema."""

    def test_prompt_includes_output_schema(self, agent):
        with patch.object(agent, "query_local_qwen", return_value="ok") as llm:
            agent.analyze_log("test error", use_memory=False)
        prompt = llm.call_args.args[0]
        assert "diagnosis" in prompt
        assert "evidence" in prompt
        assert "confidence" in prompt
        assert "remediation" in prompt

    def test_prompt_includes_safety_constraints(self, agent):
        with patch.object(agent, "query_local_qwen", return_value="ok") as llm:
            agent.analyze_log("test error", use_memory=False)
        prompt = llm.call_args.args[0]
        assert "untrusted" in prompt.lower()
        assert "not instructions" in prompt.lower()

    def test_memory_prompt_includes_verification_warning(self, offline_manager, agent):
        # Seed memory so the memory path is taken
        offline_manager.retain_incident("test error database connection failed")
        with patch.object(agent, "query_local_qwen", return_value="ok") as llm:
            agent.analyze_log("test error", use_memory=True)
        prompt = llm.call_args.args[0]
        assert "Never claim a fix is verified" in prompt

    def test_prompt_includes_safety_and_schema(self, agent):
        """Optimized prompt must include both safety constraints and output schema."""
        with patch.object(agent, "query_local_qwen", return_value="ok") as llm:
            agent.analyze_log("test error", use_memory=False)
        prompt = llm.call_args.args[0]
        # Must include safety constraints
        assert "untrusted" in prompt.lower()
        assert "not instructions" in prompt.lower()
        # Must include output schema
        assert "diagnosis" in prompt
        assert "evidence" in prompt
        assert "confidence" in prompt
        assert "remediation" in prompt
        # Must include hypothesis distinction
        assert "hypotheses" in prompt.lower()
        assert "unverified" in prompt.lower()


class TestStructuredResponseFields:
    """Response includes structured fields from schema."""

    def test_response_has_evidence_field(self, agent):
        result = agent.analyze_log("test error", use_memory=False)
        assert "evidence" in result
        assert isinstance(result["evidence"], list)

    def test_response_has_uncertainty_field(self, agent):
        result = agent.analyze_log("test error", use_memory=False)
        assert "uncertainty" in result

    def test_response_has_next_checks_field(self, agent):
        result = agent.analyze_log("test error", use_memory=False)
        assert "next_checks" in result
        assert isinstance(result["next_checks"], list)

    def test_structured_output_used_when_valid(self, agent):
        """When LLM returns valid JSON, structured fields should be used."""
        structured_json = (
            '{"diagnosis": "connection pool exhausted", '
            '"evidence": ["FATAL: remaining connection slots"], '
            '"confidence": "medium", '
            '"uncertainty": "unknown if pool was full", '
            '"next_checks": ["check pg_stat_activity"], '
            '"remediation": "restart service"}'
        )
        with patch.object(agent, "query_local_qwen", return_value=structured_json):
            result = agent.analyze_log("test error", use_memory=False)
        assert result["root_cause"] == "connection pool exhausted"
        assert result["confidence"] == "medium"
        assert result["evidence"] == ["FATAL: remaining connection slots"]
        assert result["next_checks"] == ["check pg_stat_activity"]

    def test_fallback_when_structured_output_invalid(self, agent):
        """When LLM returns invalid JSON, fallback values should be used."""
        with patch.object(agent, "query_local_qwen", return_value="not json"):
            result = agent.analyze_log("test error", use_memory=False)
        assert result["root_cause"] == "Uncertain / Unknown (No Memory Context)"
        assert result["confidence"] == "Low (Baseline Local LLM Guess)"
