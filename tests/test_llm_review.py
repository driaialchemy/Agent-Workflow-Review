"""
Tests for optional LLM review and arbiter behavior.
These tests do not make network calls.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents import llm_review


def _baseline(
    decision: str = "REVISE",
    risk_score: float = 5.0,
    value_score: float = 5.0,
    confidence: float = 0.6,
) -> dict:
    return {
        "decision": decision,
        "risk_score": risk_score,
        "value_score": value_score,
        "confidence": confidence,
        "rationale": "Baseline rationale.",
        "high_risk_dimensions": [],
        "high_value_dimensions": [],
    }


def _clear_provider_env(monkeypatch) -> None:
    for key in [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "OPENAI_MODEL",
        "ANTHROPIC_MODEL",
        "GOOGLE_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_extract_json_object_from_fenced_response():
    parsed = llm_review.extract_json_object(
        """```json
        {"decision": "APPROVE", "risk_score": 2, "value_score": 8}
        ```"""
    )

    assert parsed["decision"] == "APPROVE"
    assert parsed["risk_score"] == 2
    assert parsed["value_score"] == 8


def test_review_with_llms_no_keys_returns_baseline_without_network(monkeypatch):
    _clear_provider_env(monkeypatch)

    result = llm_review.review_with_llms("Proposal", _baseline("APPROVE", 2.0, 7.0))

    assert result["enabled"] is False
    assert result["reviews"] == []
    assert result["errors"] == []
    assert result["arbiter"]["decision"] == "APPROVE"


def test_review_with_llms_uses_configured_provider(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    def fake_call_provider(provider_id, proposal, baseline, timeout):
        assert provider_id == "openai"
        assert proposal == "Proposal"
        assert baseline["decision"] == "REVISE"
        assert timeout >= 5
        return {
            "provider": "openai",
            "provider_name": "OpenAI",
            "model": "test-model",
            "decision": "APPROVE",
            "risk_score": 2.0,
            "value_score": 8.0,
            "confidence": 0.8,
            "rationale": "Looks good.",
            "top_risks": [],
            "top_values": ["High upside"],
            "required_changes": [],
        }

    monkeypatch.setattr(llm_review, "_call_provider", fake_call_provider)

    result = llm_review.review_with_llms("Proposal", _baseline())

    assert result["enabled"] is True
    assert len(result["reviews"]) == 1
    assert result["reviews"][0]["provider"] == "openai"
    assert result["arbiter"]["review_count"] == 1


def test_google_request_uses_json_schema(monkeypatch):
    captured = {}

    def fake_post_json(url, headers, payload, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        captured["timeout"] = timeout
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"decision":"REVISE","risk_score":5,'
                                    '"value_score":6,"confidence":0.7,'
                                    '"rationale":"Needs cleanup.",'
                                    '"top_risks":["Risk"],'
                                    '"top_values":["Value"],'
                                    '"required_changes":["Change"]}'
                                )
                            }
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr(llm_review, "_post_json", fake_post_json)

    text = llm_review._call_google(
        "test-key",
        "gemini-2.5-flash",
        "Review this proposal.",
        30,
    )

    generation_config = captured["payload"]["generationConfig"]
    assert captured["url"].startswith("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash")
    assert captured["payload"]["systemInstruction"]["parts"][0]["text"] == llm_review.SYSTEM_PROMPT
    assert generation_config["thinkingConfig"]["thinkingBudget"] == 0
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["responseSchema"]["type"] == "OBJECT"
    assert "required_changes" in generation_config["responseSchema"]["required"]
    assert "REVISE" in text


def test_arbiter_approves_when_reviews_converge_on_low_risk_high_value():
    result = llm_review.arbitrate_reviews(
        _baseline("APPROVE", 2.5, 7.0, 0.8),
        [
            {
                "provider": "openai",
                "decision": "APPROVE",
                "risk_score": 2.0,
                "value_score": 8.0,
                "confidence": 0.9,
                "required_changes": [],
            },
            {
                "provider": "anthropic",
                "decision": "APPROVE",
                "risk_score": 3.0,
                "value_score": 7.0,
                "confidence": 0.8,
                "required_changes": [],
            },
        ],
    )

    assert result["decision"] == "APPROVE"
    assert result["confidence"] > 0.5


def test_arbiter_rejects_when_a_reviewer_flags_high_risk_reject():
    result = llm_review.arbitrate_reviews(
        _baseline("REVISE", 5.0, 5.0, 0.6),
        [
            {
                "provider": "google",
                "decision": "REJECT",
                "risk_score": 8.0,
                "value_score": 4.0,
                "confidence": 0.85,
                "required_changes": ["Add human approval before deployment."],
            }
        ],
    )

    assert result["decision"] == "REJECT"
    assert "Add human approval before deployment." in result["required_changes"]
