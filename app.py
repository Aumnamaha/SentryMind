"""SentryMind Streamlit UI — hackathon demo experience.

Features:
- Side-by-side first-time vs memory-assisted analysis
- Explainable diagnosis with evidence links
- Privacy protection display (secret redaction)
- Performance dashboard
- Clear distinction between suggested and verified remediation
"""

import json
import os
import time
from typing import cast

import streamlit as st

from agent.core import SentryMindAgent

st.set_page_config(page_title="SentryMind | DevOps Memory Agent", layout="wide")

# Load Synthetic Incident Log Scenarios
data_path = os.path.join(os.path.dirname(__file__), "data", "incident_logs.json")
try:
    with open(data_path, "r") as f:
        incident_scenarios = json.load(f)
except FileNotFoundError:
    st.error(f"Incident data file not found: {data_path}")
    st.stop()

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "memory_seeded" not in st.session_state:
    st.session_state.memory_seeded = False
if "analysis_count" not in st.session_state:
    st.session_state.analysis_count = 0
if "last_analysis" not in st.session_state:
    st.session_state.last_analysis = None

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("🛡️ SentryMind: AI Incident Response Agent")
st.caption("Local LLM-powered incident triage with Hindsight memory — runs entirely on your machine")

st.markdown("---")

# ---------------------------------------------------------------------------
# Sidebar Controls
# ---------------------------------------------------------------------------

st.sidebar.header("🕹️ Incident Simulator Controls")

scenario_titles = [f"{item['id']} - {item['title']}" for item in incident_scenarios]
selected_title = st.sidebar.selectbox("Select Production Alert", scenario_titles)

selected_incident: dict | None = next(
    (
        item
        for item in incident_scenarios
        if f"{item['id']} - {item['title']}" == selected_title
    ),
    None,
)
if selected_incident is None:
    st.error("Selected incident not found.")
    st.stop()
selected_incident = cast(dict, selected_incident)

# Memory toggle
use_memory_default = st.sidebar.toggle("Enable Memory (Hindsight)", value=True)

# Performance dashboard toggle
show_performance = st.sidebar.toggle("Show Performance Dashboard", value=False)

# ---------------------------------------------------------------------------
# Display Current Raw Log Alert
# ---------------------------------------------------------------------------

st.subheader("🚨 Incoming Production Alert Log")
st.code(selected_incident["error_log"], language="log")

# ---------------------------------------------------------------------------
# Instantiate Agent
# ---------------------------------------------------------------------------

@st.cache_resource
def get_agent():
    return SentryMindAgent()


agent = get_agent()

# Seed memory on first load
if not st.session_state.memory_seeded:
    st.session_state.memory_seeded = True
    for item in incident_scenarios:
        content = f"Incident: {item['title']}. Error Log: {item['error_log']}. Root Cause: {item['root_cause']}. Verified Fix: {item['resolution']}"
        agent.memory.retain_incident(content=content, context="production_postmortem")

# ---------------------------------------------------------------------------
# Side-by-Side Analysis
# ---------------------------------------------------------------------------

st.subheader("🔍 Side-by-Side Analysis: First-Time vs Memory-Assisted")

col1, col2 = st.columns(2)

# --- LEFT COLUMN: Without Memory ---
with col1:
    st.error("❌ First-Time Analysis (No Memory)")
    st.caption("Stateless LLM with zero historical context")

    if st.button("Analyze Log (Without Memory)", key="btn_no_mem"):
        with st.spinner("Generating baseline analysis..."):
            start = time.perf_counter()
            res_baseline = agent.analyze_log(
                selected_incident["error_log"], use_memory=False
            )
            latency = (time.perf_counter() - start) * 1000
            st.session_state.last_analysis = {
                "type": "no_memory",
                "result": res_baseline,
                "latency_ms": latency,
            }

    if st.session_state.last_analysis and st.session_state.last_analysis["type"] == "no_memory":
        res = st.session_state.last_analysis["result"]
        latency = st.session_state.last_analysis["latency_ms"]

        st.markdown(f"**Latency:** {latency:.0f}ms")
        st.markdown(f"**Confidence:** {res['confidence']}")
        st.markdown(f"**Diagnosis (what the log proves):** {res['root_cause']}")

        if res.get("hypotheses"):
            st.markdown("**Hypotheses (unverified):**")
            for hyp in res["hypotheses"]:
                st.markdown(f"- 🔍 {hyp}")

        if res.get("evidence"):
            st.markdown("**Evidence:**")
            for ev in res["evidence"]:
                st.markdown(f"- `{ev}`")

        if res.get("uncertainty"):
            st.markdown(f"**⚠️ Uncertainty:** {res['uncertainty']}")

        if res.get("next_checks"):
            st.markdown("**Next Checks:**")
            for check in res["next_checks"]:
                st.markdown(f"- {check}")

        st.markdown("**Suggested Remediation (NOT verified):**")
        st.warning(res["recommended_action"])

# --- RIGHT COLUMN: With Memory ---
with col2:
    st.success("🧠 Memory-Assisted Analysis (Hindsight)")
    st.caption("Augmented with past incident post-mortems & verified runbook fixes")

    if st.button("Analyze Log (With Memory Recall)", key="btn_with_mem"):
        with st.spinner("Querying Hindsight Memory Bank & Local LLM..."):
            start = time.perf_counter()
            res_memory = agent.analyze_log(
                selected_incident["error_log"], use_memory=use_memory_default
            )
            latency = (time.perf_counter() - start) * 1000
            st.session_state.last_analysis = {
                "type": "with_memory",
                "result": res_memory,
                "latency_ms": latency,
            }

    if st.session_state.last_analysis and st.session_state.last_analysis["type"] == "with_memory":
        res = st.session_state.last_analysis["result"]
        latency = st.session_state.last_analysis["latency_ms"]

        # Memory source indicator — critical for distinguishing fallback from persistent
        memory_source = res.get("memory_source", "unknown")
        if memory_source == "local_fallback":
            st.error("⚠️ Memory source: LOCAL FALLBACK (in-memory only, NOT persistent)")
        elif memory_source == "hindsight":
            st.success("✅ Memory source: HINDSIGHT (persistent)")
        else:
            st.info(f"ℹ️ Memory source: {memory_source}")

        st.markdown(f"**Latency:** {latency:.0f}ms")
        st.markdown(f"**Confidence:** {res['confidence']}")
        st.markdown(f"**Diagnosis (what the log proves):** {res['root_cause']}")

        if res.get("hypotheses"):
            st.markdown("**Hypotheses (unverified):**")
            for hyp in res["hypotheses"]:
                st.markdown(f"- 🔍 {hyp}")

        if res.get("evidence"):
            st.markdown("**Evidence:**")
            for ev in res["evidence"]:
                st.markdown(f"- `{ev}`")

        if res.get("uncertainty"):
            st.markdown(f"**⚠️ Uncertainty:** {res['uncertainty']}")

        if res.get("next_checks"):
            st.markdown("**Next Checks:**")
            for check in res["next_checks"]:
                st.markdown(f"- {check}")

        if res.get("recalled_context"):
            st.markdown("**📚 Recalled Historical Incidents:**")
            for ctx in res["recalled_context"]:
                with st.expander("View recalled incident"):
                    st.markdown(ctx)

        st.markdown("**Suggested Remediation (NOT verified):**")
        st.warning(res["recommended_action"])

# ---------------------------------------------------------------------------
# Privacy Protection Display
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("🔒 Privacy Protection")

with st.expander("Show secret redaction in action"):
    st.markdown("SentryMind automatically redacts secrets before sending data to the LLM:")

    sample_log = "ERROR api_key=sk-test-12345 password=hunter2 database connection failed"
    st.markdown("**Original log:**")
    st.code(sample_log, language="log")

    redacted = agent._redact_secrets(sample_log)
    st.markdown("**After redaction:**")
    st.code(redacted, language="log")

    st.markdown("✅ Secrets are redacted before LLM calls, memory recall, and retention.")

# ---------------------------------------------------------------------------
# Performance Dashboard
# ---------------------------------------------------------------------------

if show_performance:
    st.markdown("---")
    st.subheader("📊 Performance Dashboard")

    # Memory stats
    mem_stats = agent.memory.reflect_patterns("all")
    st.markdown(f"**Memory Bank:** {len(agent.memory.local_store)} incidents stored")

    # Analysis stats
    if st.session_state.last_analysis:
        res = st.session_state.last_analysis["result"]
        latency = st.session_state.last_analysis["latency_ms"]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Analysis Latency", f"{latency:.0f}ms")
        col2.metric("Memory Active", "Yes" if res["memory_active"] else "No")
        col3.metric("Recalled Contexts", len(res.get("recalled_context", [])))
        col4.metric("Evidence Items", len(res.get("evidence", [])))

    # Inference status
    try:
        import requests
        resp = requests.get("http://127.0.0.1:1234/v1/models", timeout=2)
        if resp.status_code == 200:
            st.success("🟢 Local LLM (llama.cpp) is running")
        else:
            st.warning("🟡 Local LLM is not responding correctly")
    except (requests.RequestException, OSError):
        st.error("🔴 Local LLM is not available — analysis will use fallback mode")

# ---------------------------------------------------------------------------
# Incident Resolution & Memory Retain Section
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("📥 Retain New Incident Learnings")
st.write(
    "Resolved a new incident? Push the verified root cause and fix back to Hindsight Bank."
)

with st.form("retain_form"):
    inc_id = st.text_input("Incident ID", value="INC-004")
    raw_log_input = st.text_area(
        "Raw Log Message", value="ERROR: Redis Connection Timeout on Port 6379"
    )
    root_cause_input = st.text_input(
        "Discovered Root Cause", value="Stale DNS record on Auth Gateway"
    )
    fix_input = st.text_input(
        "Verified Fix Action", value="Run systemctl restart systemd-resolved"
    )

    submit_retain = st.form_submit_button("Store in Hindsight Memory")
    if submit_retain:
        res = agent.resolve_and_retain(
            inc_id, raw_log_input, root_cause_input, fix_input
        )
        st.success(f"Successfully stored in Hindsight Bank! Response: {res['status']}")
