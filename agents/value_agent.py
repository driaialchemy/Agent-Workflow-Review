"""
Value Agent: evaluates an AI workflow proposal for business value, efficiency
gain, cost reduction, and deployment upside using deterministic keyword scoring.
"""

from typing import Any

VALUE_KEYWORDS = {
    "business_value": [
        "revenue", "customer", "user experience", "competitive", "market",
        "brand", "retention", "acquisition", "growth", "strategic", "kpi",
        "roi", "stakeholder", "product", "feature",
    ],
    "efficiency_gain": [
        "automate", "automation", "streamline", "faster", "speed", "reduce time",
        "batch", "parallel", "pipeline", "workflow", "eliminate manual",
        "scheduled", "real-time", "throughput", "less effort",
    ],
    "cost_reduction": [
        "cost", "saving", "reduce spend", "cheaper", "budget", "overhead",
        "headcount", "resource", "licence", "subscription", "infrastructure",
        "cloud", "optimize", "efficient", "lean",
    ],
    "deployment_upside": [
        "scalable", "reusable", "modular", "extensible", "api", "microservice",
        "plug-in", "template", "framework", "open source", "documented",
        "maintainable", "tested", "ci/cd", "deploy",
    ],
}

DETRACTOR_KEYWORDS = [
    "expensive", "complex integration", "high maintenance", "vendor lock",
    "proprietary", "single use", "hard coded", "manual step", "no documentation",
    "one-off", "prototype only", "not scalable",
]


def _count_hits(text: str, keywords: list[str]) -> int:
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)


def _base_score(hits: int, detractors: int) -> float:
    """Map keyword hits to a 0–10 value score, reduced by detractors."""
    raw = min(hits * 1.2, 10.0)
    reduction = min(detractors * 0.6, raw * 0.35)
    return round(max(0.0, raw - reduction), 2)


def evaluate(proposal: str) -> dict[str, Any]:
    """
    Analyse a workflow proposal for four value dimensions.

    Returns a dict with per-dimension scores (0-10, higher = more valuable),
    an overall value score, and a brief rationale per dimension.
    """
    detractors = _count_hits(proposal, DETRACTOR_KEYWORDS)

    scores: dict[str, float] = {}
    rationale: dict[str, str] = {}

    for dimension, keywords in VALUE_KEYWORDS.items():
        hits = _count_hits(proposal, keywords)
        score = _base_score(hits, detractors)
        scores[dimension] = score

        if score >= 7:
            level = "HIGH"
        elif score >= 4:
            level = "MEDIUM"
        else:
            level = "LOW"

        rationale[dimension] = (
            f"{level} value — {hits} value indicator(s) found"
            + (f", {detractors} detractor(s) detected" if detractors else "")
            + "."
        )

    overall = round(sum(scores.values()) / len(scores), 2)

    return {
        "agent": "ValueAgent",
        "scores": scores,
        "overall_value_score": overall,
        "rationale": rationale,
    }
