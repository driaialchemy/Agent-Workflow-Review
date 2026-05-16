"""
Risk Agent: evaluates an AI workflow proposal for operational, safety, compliance,
and reliability risks using deterministic keyword-based scoring.
"""

import re
from typing import Any

RISK_KEYWORDS = {
    "operational": [
        "manual", "untested", "complex", "integrate", "legacy", "migration",
        "downtime", "rollback", "dependency", "bottleneck", "single point",
        "no fallback", "no monitoring", "no logging",
    ],
    "safety": [
        "autonomous", "unreviewed", "no human", "override", "bypass",
        "self-modifying", "unrestricted", "no guardrail", "sensitive data",
        "personal data", "pii", "medical", "financial decision", "life-critical",
        "no oversight",
    ],
    "compliance": [
        "gdpr", "hipaa", "sox", "pci", "regulation", "legal",
        "unlicensed", "third-party data", "consent", "retention", "privacy",
        "no policy", "unaudited", "terms of service", "intellectual property",
        "no audit", "audit violation",
    ],
    "reliability": [
        "no test", "untested", "prototype", "poc", "proof of concept", "unstable",
        "experimental", "no sla", "no backup", "single server", "no redundancy",
        "no failover", "timeout", "rate limit", "no retry",
    ],
}

MITIGATOR_KEYWORDS = [
    "monitored", "tested", "reviewed", "approved", "compliant", "redundant",
    "fallback", "backup", "logging", "audit trail", "human in the loop",
    "human review", "rollback plan", "sla", "documented", "automated tests",
    "ci/cd", "staged rollout", "sandboxed",
]


def _count_hits(text: str, keywords: list[str]) -> int:
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)


def _base_score(hits: int, mitigators: int) -> float:
    """Map keyword hits to a 0–10 risk score, reduced by mitigators."""
    raw = min(hits * 1.5, 10.0)
    reduction = min(mitigators * 0.5, raw * 0.4)
    return round(max(0.0, raw - reduction), 2)


def evaluate(proposal: str) -> dict[str, Any]:
    """
    Analyse a workflow proposal for four risk dimensions.

    Returns a dict with per-dimension scores (0-10, higher = riskier),
    an overall risk score, and a brief rationale per dimension.
    """
    mitigators = _count_hits(proposal, MITIGATOR_KEYWORDS)

    scores: dict[str, float] = {}
    rationale: dict[str, str] = {}

    for dimension, keywords in RISK_KEYWORDS.items():
        hits = _count_hits(proposal, keywords)
        score = _base_score(hits, mitigators)
        scores[dimension] = score

        if score >= 7:
            level = "HIGH"
        elif score >= 4:
            level = "MEDIUM"
        else:
            level = "LOW"

        rationale[dimension] = (
            f"{level} risk — {hits} risk indicator(s) found"
            + (f", {mitigators} mitigator(s) detected" if mitigators else "")
            + "."
        )

    overall = round(sum(scores.values()) / len(scores), 2)

    return {
        "agent": "RiskAgent",
        "scores": scores,
        "overall_risk_score": overall,
        "rationale": rationale,
    }
