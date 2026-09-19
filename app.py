"""
Agent Review Board Streamlit app.

Runs a deterministic local baseline through risk/value agents and
decision_synthesizer.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import streamlit as st

from agents import decision_synthesizer, risk_agent, value_agent

BASE_DIR = os.path.dirname(__file__)
AUDIT_LOG_PATH = os.path.join(BASE_DIR, "outputs", "audit_log.json")
SAMPLE_CASES_PATH = os.path.join(BASE_DIR, "data", "sample_cases.json")


def load_audit_log() -> list[dict[str, Any]]:
    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return []


def append_audit_log(entry: dict[str, Any]) -> None:
    log = load_audit_log()
    log.append(entry)
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as file:
        json.dump(log, file, indent=2)


def load_sample_cases() -> list[dict[str, str]]:
    try:
        with open(SAMPLE_CASES_PATH, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def decision_colour(decision: str) -> str:
    return {"APPROVE": "green", "REVISE": "orange", "REJECT": "red"}.get(decision, "grey")


def score_bar(label: str, score: float, max_score: float = 10.0) -> None:
    pct = int((score / max_score) * 100)
    st.write(f"**{label}**: {score:.1f} / {max_score:.0f}")
    st.progress(pct)


def render_agent_result(title: str, metric_label: str, result: dict[str, Any]) -> None:
    st.markdown(f"### {title}")
    score_key = "overall_risk_score" if "overall_risk_score" in result else "overall_value_score"
    st.metric(metric_label, f"{result[score_key]:.1f} / 10")
    for dimension, score in result["scores"].items():
        score_bar(dimension.replace("_", " ").title(), score)
    with st.expander(f"{title} rationale"):
        for dimension, text in result["rationale"].items():
            st.write(f"**{dimension.replace('_', ' ').title()}**: {text}")


def render_decision(title: str, decision_result: dict[str, Any]) -> None:
    decision = decision_result["decision"]
    colour = decision_colour(decision)
    st.markdown(f"### {title}")
    st.markdown(
        f"<h2 style='color:{colour};'>{decision}</h2>",
        unsafe_allow_html=True,
    )
    conf_pct = int(decision_result["confidence"] * 100)
    st.write(f"**Confidence**: {conf_pct}%")
    st.progress(conf_pct)
    st.info(decision_result["rationale"])


st.set_page_config(
    page_title="Agent Review Board",
    layout="wide",
)

st.title("Agent Review Board")
st.caption("Deterministic local scoring through the decision synthesizer.")

with st.sidebar:
    st.header("Sample Cases")
    samples = load_sample_cases()
    sample_labels = ["-- select a sample --"] + [sample["title"] for sample in samples]
    selected_sample = st.selectbox("Load a sample proposal:", sample_labels)

    st.divider()
    st.header("Audit Log")
    log = load_audit_log()
    st.metric("Reviews logged", len(log))
    if log and st.button("Clear audit log"):
        with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as file:
            json.dump([], file)
        st.success("Audit log cleared.")
        st.rerun()


st.subheader("1. Enter or paste an AI workflow proposal")

prefill = ""
if selected_sample and selected_sample != "-- select a sample --":
    match = next((sample for sample in samples if sample["title"] == selected_sample), None)
    if match:
        prefill = match["proposal"]

proposal_text = st.text_area(
    "Proposal",
    value=prefill,
    height=200,
    placeholder="Describe the AI workflow you want to evaluate...",
)

run_review = st.button("Run Agent Review", type="primary", disabled=not proposal_text.strip())

if run_review and proposal_text.strip():
    with st.spinner("Running deterministic agents..."):
        risk_result = risk_agent.evaluate(proposal_text)
        value_result = value_agent.evaluate(proposal_text)
        if decision_synthesizer.should_auto_clear(risk_result):
            synthesis = decision_synthesizer.auto_clear_decision(risk_result, value_result)
        else:
            synthesis = decision_synthesizer.synthesize(risk_result, value_result)

    final_result = synthesis
    decision_source = (
        "auto_logged" if decision_synthesizer.should_auto_clear(risk_result) else "deterministic_baseline"
    )

    st.divider()
    st.subheader("2. Agent Results")
    col_risk, col_value = st.columns(2)
    with col_risk:
        render_agent_result("Risk Agent", "Overall Risk Score", risk_result)
    with col_value:
        render_agent_result("Value Agent", "Overall Value Score", value_result)

    st.divider()
    st.subheader("3. Deterministic Board Decision")
    render_decision("Baseline Recommendation", synthesis)

    if synthesis["high_risk_dimensions"]:
        st.warning(
            "High-risk dimensions: "
            + ", ".join(dimension.replace("_", " ").title() for dimension in synthesis["high_risk_dimensions"])
        )
    if synthesis["high_value_dimensions"]:
        st.success(
            "High-value dimensions: "
            + ", ".join(dimension.replace("_", " ").title() for dimension in synthesis["high_value_dimensions"])
        )

    audit_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "proposal_excerpt": proposal_text[:200],
        "risk_score": final_result["risk_score"],
        "value_score": final_result["value_score"],
        "decision": final_result["decision"],
        "confidence": final_result["confidence"],
        "rationale": final_result["rationale"],
        "decision_source": decision_source,
        "deterministic_baseline": synthesis,
    }
    append_audit_log(audit_entry)
    from governance_logger import require_approval
    require_approval(
        "Agent-Workflow-Review",
        "Agent completed successfully",
        {
            "decision": final_result.get("decision"),
            "risk_score": final_result.get("risk_score"),
            "value_score": final_result.get("value_score"),
            "result": final_result,
        },
        confidence=final_result.get("confidence"),
    )
    st.caption("Review appended to outputs/audit_log.json")


st.divider()
st.subheader("Recent Audit Log")
log = load_audit_log()
if not log:
    st.write("No reviews logged yet.")
else:
    for entry in reversed(log[-10:]):
        timestamp = str(entry.get("timestamp", ""))[:19]
        decision = entry.get("decision", "UNKNOWN")
        risk = entry.get("risk_score", "?")
        value = entry.get("value_score", "?")
        source = entry.get("decision_source", "deterministic_baseline")
        with st.expander(f"[{timestamp}Z] {decision} | Risk {risk} | Value {value} | {source}"):
            st.write(f"**Excerpt**: {entry.get('proposal_excerpt', '')}...")
            st.write(f"**Rationale**: {entry.get('rationale', '')}")
            confidence = entry.get("confidence")
            if isinstance(confidence, (int, float)):
                st.write(f"**Confidence**: {int(confidence * 100)}%")
