"""
Agent Review Board — Streamlit App
A local-first multi-agent review board for AI workflow proposals.
"""

import json
import os
from datetime import datetime, timezone

import streamlit as st

from agents import risk_agent, value_agent, decision_synthesizer

AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "outputs", "audit_log.json")
SAMPLE_CASES_PATH = os.path.join(os.path.dirname(__file__), "data", "sample_cases.json")

# ── helpers ──────────────────────────────────────────────────────────────────

def load_audit_log() -> list:
    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def append_audit_log(entry: dict) -> None:
    log = load_audit_log()
    log.append(entry)
    os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
    with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


def load_sample_cases() -> list:
    try:
        with open(SAMPLE_CASES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def decision_colour(decision: str) -> str:
    return {"APPROVE": "green", "REVISE": "orange", "REJECT": "red"}.get(decision, "grey")


def score_bar(label: str, score: float, max_score: float = 10.0) -> None:
    pct = int((score / max_score) * 100)
    st.write(f"**{label}**: {score:.1f} / {max_score:.0f}")
    st.progress(pct)


# ── page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Agent Review Board",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 Agent Review Board")
st.caption(
    "A local, offline multi-agent system that evaluates AI workflow proposals "
    "for risk and value, then issues a board-level decision."
)

# ── sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Sample Cases")
    samples = load_sample_cases()
    sample_labels = ["— select a sample —"] + [s["title"] for s in samples]
    selected_sample = st.selectbox("Load a sample proposal:", sample_labels)

    st.divider()
    st.header("Audit Log")
    log = load_audit_log()
    st.metric("Reviews logged", len(log))
    if log and st.button("Clear audit log"):
        with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
        st.success("Audit log cleared.")
        st.rerun()

# ── proposal input ───────────────────────────────────────────────────────────

st.subheader("1. Enter or paste an AI workflow proposal")

prefill = ""
if selected_sample and selected_sample != "— select a sample —":
    match = next((s for s in samples if s["title"] == selected_sample), None)
    if match:
        prefill = match["proposal"]

proposal_text = st.text_area(
    "Proposal",
    value=prefill,
    height=200,
    placeholder="Describe the AI workflow you want to evaluate…",
)

run_review = st.button("▶ Run Agent Review", type="primary", disabled=not proposal_text.strip())

# ── run review ───────────────────────────────────────────────────────────────

if run_review and proposal_text.strip():
    with st.spinner("Agents evaluating…"):
        risk_result = risk_agent.evaluate(proposal_text)
        value_result = value_agent.evaluate(proposal_text)
        synthesis = decision_synthesizer.synthesize(risk_result, value_result)

    decision = synthesis["decision"]
    colour = decision_colour(decision)

    st.divider()
    st.subheader("2. Agent Results")

    col_risk, col_value = st.columns(2)

    with col_risk:
        st.markdown("### 🔴 Risk Agent")
        st.metric("Overall Risk Score", f"{risk_result['overall_risk_score']:.1f} / 10")
        for dim, score in risk_result["scores"].items():
            score_bar(dim.replace("_", " ").title(), score)
        with st.expander("Risk rationale"):
            for dim, text in risk_result["rationale"].items():
                st.write(f"**{dim.replace('_', ' ').title()}**: {text}")

    with col_value:
        st.markdown("### 🟢 Value Agent")
        st.metric("Overall Value Score", f"{value_result['overall_value_score']:.1f} / 10")
        for dim, score in value_result["scores"].items():
            score_bar(dim.replace("_", " ").title(), score)
        with st.expander("Value rationale"):
            for dim, text in value_result["rationale"].items():
                st.write(f"**{dim.replace('_', ' ').title()}**: {text}")

    # ── decision ─────────────────────────────────────────────────────────────

    st.divider()
    st.subheader("3. Board Decision")

    st.markdown(
        f"<h2 style='color:{colour};'>⚖️ {decision}</h2>",
        unsafe_allow_html=True,
    )

    conf_pct = int(synthesis["confidence"] * 100)
    st.write(f"**Confidence**: {conf_pct}%")
    st.progress(conf_pct)

    st.info(synthesis["rationale"])

    if synthesis["high_risk_dimensions"]:
        st.warning(
            "High-risk dimensions: "
            + ", ".join(d.replace("_", " ").title() for d in synthesis["high_risk_dimensions"])
        )
    if synthesis["high_value_dimensions"]:
        st.success(
            "High-value dimensions: "
            + ", ".join(d.replace("_", " ").title() for d in synthesis["high_value_dimensions"])
        )

    # ── audit log ────────────────────────────────────────────────────────────

    audit_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "proposal_excerpt": proposal_text[:200],
        "risk_score": risk_result["overall_risk_score"],
        "value_score": value_result["overall_value_score"],
        "decision": decision,
        "confidence": synthesis["confidence"],
        "rationale": synthesis["rationale"],
    }
    append_audit_log(audit_entry)
    st.caption("✅ Review appended to outputs/audit_log.json")

# ── audit log viewer ─────────────────────────────────────────────────────────

st.divider()
st.subheader("4. Recent Audit Log")
log = load_audit_log()
if not log:
    st.write("No reviews logged yet.")
else:
    for entry in reversed(log[-10:]):
        colour = decision_colour(entry["decision"])
        with st.expander(
            f"[{entry['timestamp'][:19]}Z]  "
            f"**{entry['decision']}**  |  "
            f"Risk {entry['risk_score']} · Value {entry['value_score']}"
        ):
            st.write(f"**Excerpt**: {entry['proposal_excerpt']}…")
            st.write(f"**Rationale**: {entry['rationale']}")
            st.write(f"**Confidence**: {int(entry['confidence'] * 100)}%")
