"""
src/app.py
-----------------------------------------------------------------------------
Streamlit Web Interface for AI Workflow Agent.

Displays:
  • Sidebar: Provider info, quick test request buttons for WF001-WF010, file uploader.
  • Panel A: Selected Workflow details (ID, Name, Trigger, Parameters, Reason).
  • Panel B: Execution Trace (Step number, Tool name, Status, Result summary).
  • Panel C: Final Output (Markdown formatted results).
-----------------------------------------------------------------------------
"""

import sys
import os
import json
import streamlit as st
from pathlib import Path

# Ensure root directory is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agent.registry import WorkflowRegistry
from src.agent.router import WorkflowRouter
from src.agent.engine import WorkflowEngine
from src.config import LLM_PROVIDER, WORKFLOWS_EXCEL, validate_config

st.set_page_config(
    page_title="AI Workflow Agent",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚡ AI Workflow Agent")
st.caption("LLM-driven dynamic workflow automation engine powered by structured tools & Excel catalog.")

# ── Load Registry ─────────────────────────────────────────────────────────────
@st.cache_resource
def load_registry():
    return WorkflowRegistry(WORKFLOWS_EXCEL)

try:
    registry = load_registry()
except Exception as e:
    st.error(f"Failed to load Workflow Registry: {e}")
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.header("Configuration & Quick Test")
st.sidebar.info(f"**Current Provider:** `{LLM_PROVIDER.upper()}`")

test_questions = registry.get_test_questions()

st.sidebar.subheader("Sample Test Requests")
selected_sample = st.sidebar.selectbox(
    "Choose a pre-set test request:",
    ["-- Select a sample query --"] + [f"{tq['workflow_id']}: {tq['test_request']}" for tq in test_questions]
)

uploaded_file = st.sidebar.file_uploader(
    "Upload custom data file (CSV/JSON/XLSX):",
    type=["csv", "json", "xlsx"],
    help="Optional file input override for processing."
)

# ── Input Area ────────────────────────────────────────────────────────────────
query_input = st.text_input(
    "Enter your request in natural language:",
    value=selected_sample.split(": ", 1)[1] if selected_sample != "-- Select a sample query --" else "",
    placeholder="e.g. Where is order ORD-1001? or Which products need restocking?",
)

run_button = st.button("🚀 Execute Workflow", type="primary", use_container_width=True)

if run_button:
    if not query_input.strip():
        st.warning("Please enter a query or select a sample test request.")
    else:
        # Save uploaded file if present
        temp_file_path = None
        if uploaded_file is not None:
            temp_dir = ROOT_DIR / "scratch"
            temp_dir.mkdir(exist_ok=True)
            temp_file_path = temp_dir / uploaded_file.name
            with open(temp_file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

        with st.spinner("Routing request and matching workflow..."):
            router = WorkflowRouter(registry)
            route = router.route(query_input)

        wf_id = route.get("workflow_id")
        params = route.get("parameters", {})
        reason = route.get("reason", "")

        if wf_id is None:
            st.error(f"❌ No matching workflow found. Reason: {reason}")
        else:
            workflow = registry.get_workflow(wf_id)
            
            # Panel A: Selected Workflow
            st.markdown("### 📋 Panel A: Selected Workflow")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Workflow ID", wf_id)
            with col2:
                st.metric("Workflow Name", workflow.get("workflow_name", ""))
            with col3:
                st.metric("Extracted Parameters", json.dumps(params) if params else "None")
            
            st.markdown(f"**Trigger:** {workflow.get('trigger', '')}")
            st.markdown(f"**Routing Rationale:** {reason}")
            st.divider()

            # Execute engine
            with st.spinner(f"Executing workflow {wf_id}..."):
                engine = WorkflowEngine()
                input_file_str = str(temp_file_path) if temp_file_path else None
                result = engine.run(workflow, params, input_file=input_file_str)

            # Panel B: Steps Executed Trace
            st.markdown("### ⚙️ Panel B: Execution Trace")
            if result.steps:
                trace_data = []
                for s in result.steps:
                    trace_data.append({
                        "Step #": s.step_num,
                        "Tool Name": s.tool_name,
                        "Status": s.status.upper(),
                        "Result Output": s.result.split("\n")[0][:120],
                    })
                st.dataframe(trace_data, use_container_width=True)
            else:
                st.info("No tool steps executed.")

            st.divider()

            # Panel C: Final Output
            st.markdown("### 🎯 Panel C: Final Output")
            if result.status == "error":
                st.error(result.final_output)
            else:
                st.markdown(result.final_output)
