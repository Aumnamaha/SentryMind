import os
import json
import streamlit as st
from agent.core import SentryMindAgent
from memory.hindsight_client import SentryMemoryManager

st.set_page_config(page_title="SentryMind | DevOps Memory Agent", layout="wide")

# Header & Mission
st.title("🛡️ SentryMind: Autonomous DevOps Incident Agent")
st.caption("Powered by Hindsight Persistent Memory System & Local Qwen 2.5 35B")

st.markdown("---")

# Load Synthetic Incident Log Scenarios
data_path = os.path.join(os.path.dirname(__file__), "data", "incident_logs.json")
try:
    with open(data_path, "r") as f:
        incident_scenarios = json.load(f)
except FileNotFoundError:
    st.error(f"Incident data file not found: {data_path}")
    st.stop()

# Sidebar Controls
st.sidebar.header("🕹️ Incident Simulator Controls")
scenario_titles = [f"{item['id']} - {item['title']}" for item in incident_scenarios]
selected_title = st.sidebar.selectbox("Select Production Alert", scenario_titles)

selected_incident = next(
    (item for item in incident_scenarios if f"{item['id']} - {item['title']}" == selected_title),
    None,
)
if selected_incident is None:
    st.error("Selected incident not found.")
    st.stop()

# Display Current Raw Log Alert
st.subheader("🚨 Incoming Production Alert Log")
st.code(selected_incident["error_log"], language="log")

# Instantiate Agent
@st.cache_resource
def get_agent():
    return SentryMindAgent()


agent = get_agent()

# Ensure seed data exists in memory (only once per session)
if "memory_seeded" not in st.session_state:
    st.session_state.memory_seeded = True
    for item in incident_scenarios:
        content = f"Incident: {item['title']}. Error Log: {item['error_log']}. Root Cause: {item['root_cause']}. Verified Fix: {item['resolution']}"
        agent.memory.retain_incident(content=content, context="production_postmortem")

col1, col2 = st.columns(2)

# --- LEFT COLUMN: Without Hindsight Memory ---
with col1:
    st.error("❌ Baseline AI Agent (Without Hindsight)")
    st.caption("Stateless LLM with zero historical context")

    if st.button("Analyze Log (Without Memory)"):
        with st.spinner("Generating baseline guess..."):
            res_baseline = agent.analyze_log(selected_incident["error_log"], use_memory=False)
            st.json(res_baseline)

# --- RIGHT COLUMN: With Hindsight Memory ---
with col2:
    st.success("🧠 SentryMind Agent (With Hindsight Memory)")
    st.caption("Augmented with past incident post-mortems & verified runbook fixes")

    if st.button("Analyze Log (With Hindsight Recall)"):
        with st.spinner("Querying Hindsight Memory Bank & Qwen..."):
            res_memory = agent.analyze_log(selected_incident["error_log"], use_memory=True)
            st.json(res_memory)

st.markdown("---")

# Incident Resolution & Memory Retain Section
st.subheader("📥 Retain New Incident Learnings")
st.write("Resolved a new incident? Push the verified root cause and fix back to Hindsight Bank.")

with st.form("retain_form"):
    inc_id = st.text_input("Incident ID", value="INC-004")
    raw_log_input = st.text_area("Raw Log Message", value="ERROR: Redis Connection Timeout on Port 6379")
    root_cause_input = st.text_input("Discovered Root Cause", value="Stale DNS record on Auth Gateway")
    fix_input = st.text_input("Verified Fix Action", value="Run systemctl restart systemd-resolved")

    submit_retain = st.form_submit_button("Store in Hindsight Memory")
    if submit_retain:
        res = agent.resolve_and_retain(inc_id, raw_log_input, root_cause_input, fix_input)
        st.success(f"Successfully stored in Hindsight Bank! Response: {res['status']}")
