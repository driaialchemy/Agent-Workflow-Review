"""
Tests for Risk Agent, Value Agent, and Decision Synthesizer.
Run with: python -m pytest tests/ -v
"""

import sys
import os

# Ensure project root is on the path so agents can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agents import risk_agent, value_agent, decision_synthesizer


# ── Risk Agent ────────────────────────────────────────────────────────────────

class TestRiskAgent:
    def test_returns_expected_keys(self):
        result = risk_agent.evaluate("Some workflow proposal")
        assert result["agent"] == "RiskAgent"
        assert "scores" in result
        assert "overall_risk_score" in result
        assert "rationale" in result

    def test_scores_have_four_dimensions(self):
        result = risk_agent.evaluate("Some workflow proposal")
        assert set(result["scores"].keys()) == {
            "operational", "safety", "compliance", "reliability"
        }

    def test_high_risk_proposal_scores_higher(self):
        risky = (
            "Autonomous system with no human oversight, no guardrails, "
            "no logging, single server, no backup, handles PII, "
            "no compliance policy, unaudited, bypass all safety checks."
        )
        safe = "A small documented, tested, monitored internal tool with human review."
        risky_result = risk_agent.evaluate(risky)
        safe_result = risk_agent.evaluate(safe)
        assert risky_result["overall_risk_score"] > safe_result["overall_risk_score"]

    def test_scores_bounded_0_to_10(self):
        result = risk_agent.evaluate(
            "autonomous bypass unreviewed no monitoring gdpr hipaa sox "
            "single point no fallback unstable prototype no sla no test "
            "personal data pii financial decision self-modifying"
        )
        for score in result["scores"].values():
            assert 0.0 <= score <= 10.0
        assert 0.0 <= result["overall_risk_score"] <= 10.0

    def test_mitigators_reduce_score(self):
        base = "The system will handle sensitive data."
        mitigated = base + (
            " It is monitored, tested, reviewed, approved, compliant, "
            "with human in the loop and an audit trail."
        )
        assert risk_agent.evaluate(base)["overall_risk_score"] >= \
               risk_agent.evaluate(mitigated)["overall_risk_score"]

    def test_empty_proposal_returns_zero_scores(self):
        result = risk_agent.evaluate("")
        assert result["overall_risk_score"] == 0.0

    def test_rationale_is_string_per_dimension(self):
        result = risk_agent.evaluate("workflow with api and automation")
        for dim in ["operational", "safety", "compliance", "reliability"]:
            assert isinstance(result["rationale"][dim], str)
            assert len(result["rationale"][dim]) > 0


# ── Value Agent ───────────────────────────────────────────────────────────────

class TestValueAgent:
    def test_returns_expected_keys(self):
        result = value_agent.evaluate("Some workflow proposal")
        assert result["agent"] == "ValueAgent"
        assert "scores" in result
        assert "overall_value_score" in result
        assert "rationale" in result

    def test_scores_have_four_dimensions(self):
        result = value_agent.evaluate("Some workflow proposal")
        assert set(result["scores"].keys()) == {
            "business_value", "efficiency_gain", "cost_reduction", "deployment_upside"
        }

    def test_high_value_proposal_scores_higher(self):
        high_value = (
            "This automation pipeline will drive significant revenue growth, "
            "improve customer retention, reduce cost and overhead, enable scalable "
            "api-driven microservice deployment with CI/CD and documented reusable templates."
        )
        low_value = "A one-off manual step with no documentation."
        high_result = value_agent.evaluate(high_value)
        low_result = value_agent.evaluate(low_value)
        assert high_result["overall_value_score"] > low_result["overall_value_score"]

    def test_scores_bounded_0_to_10(self):
        result = value_agent.evaluate(
            "revenue customer automate streamline cost saving scalable "
            "reusable api microservice documented tested ci/cd deploy "
            "roi kpi strategic growth competitive"
        )
        for score in result["scores"].values():
            assert 0.0 <= score <= 10.0
        assert 0.0 <= result["overall_value_score"] <= 10.0

    def test_detractors_reduce_score(self):
        base = "Automation pipeline to streamline the revenue workflow and reduce cost."
        with_detractors = base + (
            " However it is expensive, complex integration, hard coded, "
            "vendor lock, proprietary and not scalable."
        )
        assert value_agent.evaluate(base)["overall_value_score"] >= \
               value_agent.evaluate(with_detractors)["overall_value_score"]

    def test_empty_proposal_returns_zero_scores(self):
        result = value_agent.evaluate("")
        assert result["overall_value_score"] == 0.0

    def test_rationale_is_string_per_dimension(self):
        result = value_agent.evaluate("automate and reduce cost with api")
        for dim in ["business_value", "efficiency_gain", "cost_reduction", "deployment_upside"]:
            assert isinstance(result["rationale"][dim], str)
            assert len(result["rationale"][dim]) > 0


# ── Decision Synthesizer ──────────────────────────────────────────────────────

class TestDecisionSynthesizer:
    def _make_risk(self, overall: float) -> dict:
        return {
            "overall_risk_score": overall,
            "scores": {
                "operational": overall,
                "safety": overall,
                "compliance": overall,
                "reliability": overall,
            },
        }

    def _make_value(self, overall: float) -> dict:
        return {
            "overall_value_score": overall,
            "scores": {
                "business_value": overall,
                "efficiency_gain": overall,
                "cost_reduction": overall,
                "deployment_upside": overall,
            },
        }

    def test_returns_expected_keys(self):
        result = decision_synthesizer.synthesize(self._make_risk(3.0), self._make_value(6.0))
        for key in ["decision", "confidence", "rationale", "risk_score", "value_score",
                    "high_risk_dimensions", "high_value_dimensions"]:
            assert key in result

    def test_high_risk_yields_reject(self):
        result = decision_synthesizer.synthesize(self._make_risk(8.0), self._make_value(5.0))
        assert result["decision"] == "REJECT"

    def test_low_risk_high_value_yields_approve(self):
        result = decision_synthesizer.synthesize(self._make_risk(2.0), self._make_value(7.0))
        assert result["decision"] == "APPROVE"

    def test_moderate_risk_yields_revise(self):
        result = decision_synthesizer.synthesize(self._make_risk(5.0), self._make_value(5.0))
        assert result["decision"] == "REVISE"

    def test_high_risk_low_value_yields_reject(self):
        result = decision_synthesizer.synthesize(self._make_risk(6.0), self._make_value(2.0))
        assert result["decision"] == "REJECT"

    def test_confidence_between_0_and_1(self):
        result = decision_synthesizer.synthesize(self._make_risk(3.0), self._make_value(6.0))
        assert 0.0 <= result["confidence"] <= 1.0

    def test_rationale_is_non_empty_string(self):
        result = decision_synthesizer.synthesize(self._make_risk(5.0), self._make_value(5.0))
        assert isinstance(result["rationale"], str)
        assert len(result["rationale"]) > 10

    def test_high_risk_dimensions_flagged(self):
        risk = {
            "overall_risk_score": 7.0,
            "scores": {"operational": 8.0, "safety": 2.0, "compliance": 2.0, "reliability": 7.0},
        }
        result = decision_synthesizer.synthesize(risk, self._make_value(4.0))
        assert "operational" in result["high_risk_dimensions"]
        assert "reliability" in result["high_risk_dimensions"]
        assert "safety" not in result["high_risk_dimensions"]

    def test_end_to_end_with_real_agents(self):
        """Integration: run all three agents on a real proposal."""
        proposal = (
            "Automate invoice processing with CI/CD, audit trail, human review, "
            "rollback plan. Reduces cost and improves efficiency. Scalable API."
        )
        risk_out = risk_agent.evaluate(proposal)
        value_out = value_agent.evaluate(proposal)
        synth = decision_synthesizer.synthesize(risk_out, value_out)
        assert synth["decision"] in {"APPROVE", "REVISE", "REJECT"}
        assert 0.0 <= synth["confidence"] <= 1.0
