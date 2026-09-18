"""
Decision Synthesizer: compares Risk Agent and Value Agent outputs and issues
one of three recommendations: APPROVE, REVISE, or REJECT.
"""

from typing import Any

# Thresholds
REJECT_RISK_THRESHOLD = 7.0       # overall risk >= this → leaning REJECT
APPROVE_RISK_THRESHOLD = 4.0      # overall risk < this → can lean APPROVE
APPROVE_VALUE_THRESHOLD = 5.0     # overall value >= this → helps APPROVE
REVISE_VALUE_THRESHOLD = 3.0      # overall value < this → may lean REJECT
AUTO_CLEAR_RISK_THRESHOLD = 4.0   # overall risk below this → auto-approve, skip review queue


def should_auto_clear(risk_result: dict[str, Any]) -> bool:
    return float(risk_result["overall_risk_score"]) < AUTO_CLEAR_RISK_THRESHOLD


def auto_clear_decision(risk_result: dict[str, Any], value_result: dict[str, Any]) -> dict[str, Any]:
    """Same decision schema as synthesize(); used for below-threshold auto-approve."""
    return synthesize(risk_result, value_result) | {
        "decision": "APPROVE",
        "rationale": (
            f"Risk score ({risk_result['overall_risk_score']}/10) is below the "
            f"auto-clear threshold ({AUTO_CLEAR_RISK_THRESHOLD}). Auto-approved."
        ),
    }


def synthesize(risk_result: dict[str, Any], value_result: dict[str, Any]) -> dict[str, Any]:
    """
    Combine risk and value evaluations into a final board decision.

    Decision logic:
      - REJECT  : risk >= 7.0  OR  (risk >= 5.5 AND value < 3.0)
      - APPROVE : risk < 4.0  AND  value >= 5.0
      - REVISE  : everything else
    """
    risk_score = risk_result["overall_risk_score"]
    value_score = value_result["overall_value_score"]

    # Derive decision
    if risk_score >= REJECT_RISK_THRESHOLD:
        decision = "REJECT"
        rationale = (
            f"Overall risk score ({risk_score}/10) exceeds the rejection threshold "
            f"({REJECT_RISK_THRESHOLD}). The proposal presents too many unmitigated "
            f"risks to proceed safely."
        )
    elif risk_score >= 5.5 and value_score < REVISE_VALUE_THRESHOLD:
        decision = "REJECT"
        rationale = (
            f"Elevated risk ({risk_score}/10) combined with low business value "
            f"({value_score}/10) does not justify approval or revision effort."
        )
    elif risk_score < APPROVE_RISK_THRESHOLD and value_score >= APPROVE_VALUE_THRESHOLD:
        decision = "APPROVE"
        rationale = (
            f"Risk is well-controlled ({risk_score}/10) and the proposal delivers "
            f"meaningful value ({value_score}/10). Recommend proceeding."
        )
    else:
        decision = "REVISE"
        rationale = (
            f"The proposal has potential (value {value_score}/10) but carries "
            f"moderate risk ({risk_score}/10). Address the flagged risk areas "
            f"before re-submission."
        )

    # Confidence: inverse of how close we are to a boundary
    # Simple heuristic: distance from nearest decision boundary normalised to 0-1
    risk_margin = abs(risk_score - APPROVE_RISK_THRESHOLD) / 10.0
    value_margin = abs(value_score - APPROVE_VALUE_THRESHOLD) / 10.0
    confidence = round(min(1.0, (risk_margin + value_margin) / 2 + 0.4), 2)

    # Collect dimension-level highlights
    risk_flags = [
        dim for dim, score in risk_result["scores"].items() if score >= 6.0
    ]
    value_highlights = [
        dim for dim, score in value_result["scores"].items() if score >= 6.0
    ]

    return {
        "decision": decision,
        "confidence": confidence,
        "rationale": rationale,
        "risk_score": risk_score,
        "value_score": value_score,
        "high_risk_dimensions": risk_flags,
        "high_value_dimensions": value_highlights,
    }
