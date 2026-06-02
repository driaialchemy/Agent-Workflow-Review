"""
Optional LLM review panel for the Agent Review Board.

The deterministic agents remain the baseline. When API keys are configured, this
module asks each provider for an independent JSON review and then applies a local
arbiter so the final recommendation is explainable and resilient to disagreement.
"""

from __future__ import annotations

import json
import os
import re
from statistics import mean
from typing import Any
from urllib.parse import quote

try:
    import requests
except ImportError:  # pragma: no cover - exercised only in incomplete installs
    requests = None

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is optional at import time
    load_dotenv = None


if load_dotenv is not None:
    load_dotenv()


VALID_DECISIONS = {"APPROVE", "REVISE", "REJECT"}
DECISION_RANK = {"APPROVE": 0, "REVISE": 1, "REJECT": 2}
RANK_DECISION = {0: "APPROVE", 1: "REVISE", 2: "REJECT"}

PROVIDER_CONFIG = {
    "openai": {
        "name": "OpenAI",
        "key_env": "OPENAI_API_KEY",
        "model_env": "OPENAI_MODEL",
        "default_model": "gpt-4.1-mini",
    },
    "anthropic": {
        "name": "Anthropic",
        "key_env": "ANTHROPIC_API_KEY",
        "model_env": "ANTHROPIC_MODEL",
        "default_model": "claude-sonnet-4-20250514",
    },
    "google": {
        "name": "Google Gemini",
        "key_env": "GOOGLE_API_KEY",
        "alternate_key_env": "GEMINI_API_KEY",
        "model_env": "GOOGLE_MODEL",
        "default_model": "gemini-2.5-flash",
    },
}

SYSTEM_PROMPT = """
You are an AI governance reviewer on an agent review board. Evaluate the proposal
for operational risk, safety risk, compliance risk, reliability risk, business
value, efficiency gain, cost reduction, and deployment upside.

Return JSON only, with this exact shape:
{
  "decision": "APPROVE" | "REVISE" | "REJECT",
  "risk_score": number from 0 to 10,
  "value_score": number from 0 to 10,
  "confidence": number from 0 to 1,
  "rationale": "short explanation",
  "top_risks": ["risk one", "risk two"],
  "top_values": ["value one", "value two"],
  "required_changes": ["change one", "change two"]
}
""".strip()


class ProviderError(RuntimeError):
    """Raised when a provider request cannot produce a usable review."""


def _get_api_key(provider_id: str) -> str | None:
    config = PROVIDER_CONFIG[provider_id]
    key = os.getenv(config["key_env"])
    if key:
        return key
    alternate = config.get("alternate_key_env")
    if alternate:
        return os.getenv(alternate)
    return None


def _get_model(provider_id: str) -> str:
    config = PROVIDER_CONFIG[provider_id]
    return os.getenv(config["model_env"], config["default_model"]).strip()


def available_providers() -> list[dict[str, str]]:
    """Return configured providers without exposing API key values."""
    providers = []
    for provider_id, config in PROVIDER_CONFIG.items():
        if _get_api_key(provider_id):
            providers.append(
                {
                    "id": provider_id,
                    "name": config["name"],
                    "model": _get_model(provider_id),
                }
            )
    return providers


def review_with_llms(
    proposal: str,
    baseline: dict[str, Any],
    provider_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run configured LLM reviewers and return their reviews plus arbiter output.

    Network calls only happen for providers with configured API keys. Tests can
    monkeypatch _call_provider to exercise this path without touching the network.
    """
    configured_ids = [provider["id"] for provider in available_providers()]
    selected_ids = provider_ids if provider_ids is not None else configured_ids
    selected_ids = [provider_id for provider_id in selected_ids if provider_id in configured_ids]

    if not selected_ids:
        return {
            "enabled": False,
            "reviews": [],
            "errors": [],
            "arbiter": arbitrate_reviews(baseline, [], []),
        }

    timeout = _timeout_seconds()
    reviews: list[dict[str, Any]] = []
    errors: list[str] = []

    for provider_id in selected_ids:
        try:
            reviews.append(_call_provider(provider_id, proposal, baseline, timeout))
        except Exception as exc:  # noqa: BLE001 - provider failures should not stop the board
            provider_name = PROVIDER_CONFIG[provider_id]["name"]
            errors.append(f"{provider_name}: {exc}")

    return {
        "enabled": True,
        "reviews": reviews,
        "errors": errors,
        "arbiter": arbitrate_reviews(baseline, reviews, errors),
    }


def arbitrate_reviews(
    baseline: dict[str, Any],
    reviews: list[dict[str, Any]],
    errors: list[str] | None = None,
) -> dict[str, Any]:
    """Combine deterministic baseline output and LLM reviews into one recommendation."""
    errors = errors or []
    baseline_vote = _baseline_vote(baseline)

    if not reviews:
        note = "No LLM provider returned a review; using the deterministic baseline."
        if errors:
            note += " Provider errors were recorded for troubleshooting."
        return {
            "decision": baseline_vote["decision"],
            "confidence": baseline_vote["confidence"],
            "risk_score": baseline_vote["risk_score"],
            "value_score": baseline_vote["value_score"],
            "rationale": note,
            "disagreement_summary": "No LLM reviews available.",
            "required_changes": [],
            "review_count": 0,
        }

    votes = [baseline_vote, *reviews]
    avg_risk = mean(float(vote["risk_score"]) for vote in votes)
    avg_value = mean(float(vote["value_score"]) for vote in votes)
    avg_rank = mean(DECISION_RANK[vote["decision"]] for vote in votes)
    avg_confidence = mean(float(vote["confidence"]) for vote in votes)

    if any(
        vote["decision"] == "REJECT" and float(vote["risk_score"]) >= 6.5
        for vote in reviews
    ):
        decision = "REJECT"
    elif (
        all(vote["decision"] == "APPROVE" for vote in reviews)
        and avg_risk < 4.0
        and avg_value >= 5.0
    ):
        decision = "APPROVE"
    else:
        decision = RANK_DECISION[int(round(_clamp(avg_rank, 0, 2)))]

    decisions = {vote["decision"] for vote in votes}
    disagreement_penalty = min(0.35, (len(decisions) - 1) * 0.15)
    confidence = round(_clamp(avg_confidence - disagreement_penalty, 0.05, 1.0), 2)

    required_changes = _dedupe(
        change
        for review in reviews
        for change in review.get("required_changes", [])
        if change
    )[:6]

    mix = ", ".join(
        f"{_display_name(vote.get('provider', 'baseline'))}={vote['decision']}"
        for vote in votes
    )
    disagreement_summary = (
        f"Consensus: {next(iter(decisions))}."
        if len(decisions) == 1
        else f"Mixed review: {mix}."
    )

    rationale = (
        f"Arbiter compared the deterministic baseline with {len(reviews)} LLM "
        f"review(s). Average risk is {avg_risk:.1f}/10 and average value is "
        f"{avg_value:.1f}/10. {disagreement_summary}"
    )

    return {
        "decision": decision,
        "confidence": confidence,
        "risk_score": round(avg_risk, 1),
        "value_score": round(avg_value, 1),
        "rationale": rationale,
        "disagreement_summary": disagreement_summary,
        "required_changes": required_changes,
        "review_count": len(reviews),
    }


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from plain text or a fenced JSON response."""
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL | re.IGNORECASE)
    if fenced:
        stripped = fenced.group(1).strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ProviderError("response did not contain a JSON object") from None
        parsed = json.loads(stripped[start : end + 1])

    if not isinstance(parsed, dict):
        raise ProviderError("response JSON was not an object")
    return parsed


def _call_provider(
    provider_id: str,
    proposal: str,
    baseline: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    key = _get_api_key(provider_id)
    if not key:
        raise ProviderError("API key is not configured")

    if requests is None:
        raise ProviderError("requests is not installed; run pip install -r requirements.txt")

    model = _get_model(provider_id)
    prompt = _build_user_prompt(proposal, baseline)

    if provider_id == "openai":
        text = _call_openai(key, model, prompt, timeout)
    elif provider_id == "anthropic":
        text = _call_anthropic(key, model, prompt, timeout)
    elif provider_id == "google":
        text = _call_google(key, model, prompt, timeout)
    else:
        raise ProviderError(f"unknown provider: {provider_id}")

    review = extract_json_object(text)
    return _normalize_review(provider_id, model, review)


def _build_user_prompt(proposal: str, baseline: dict[str, Any]) -> str:
    baseline_summary = {
        "decision": baseline.get("decision"),
        "risk_score": baseline.get("risk_score"),
        "value_score": baseline.get("value_score"),
        "confidence": baseline.get("confidence"),
        "rationale": baseline.get("rationale"),
        "high_risk_dimensions": baseline.get("high_risk_dimensions", []),
        "high_value_dimensions": baseline.get("high_value_dimensions", []),
    }
    return (
        "Use the deterministic baseline as context, but make your own independent "
        "review. Return only the JSON object.\n\n"
        f"Deterministic baseline:\n{json.dumps(baseline_summary, indent=2)}\n\n"
        f"Proposal:\n{proposal}"
    )


def _call_openai(key: str, model: str, prompt: str, timeout: int) -> str:
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    data = _post_json(
        "https://api.openai.com/v1/responses",
        {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        payload,
        timeout,
    )

    if isinstance(data.get("output_text"), str):
        return data["output_text"]

    chunks: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    if chunks:
        return "\n".join(chunks)
    raise ProviderError("OpenAI response did not include text output")


def _call_anthropic(key: str, model: str, prompt: str, timeout: int) -> str:
    payload = {
        "model": model,
        "max_tokens": 1200,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }
    data = _post_json(
        "https://api.anthropic.com/v1/messages",
        {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        payload,
        timeout,
    )

    chunks = [
        content.get("text", "")
        for content in data.get("content", [])
        if content.get("type") == "text"
    ]
    text = "\n".join(chunk for chunk in chunks if chunk)
    if text:
        return text
    raise ProviderError("Anthropic response did not include text output")


def _call_google(key: str, model: str, prompt: str, timeout: int) -> str:
    model_name = model if model.startswith("models/") else f"models/{model}"
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"{quote(model_name, safe='/')}:generateContent?key={quote(key)}"
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1200,
            "responseMimeType": "application/json",
        },
    }
    data = _post_json(url, {"Content-Type": "application/json"}, payload, timeout)

    candidates = data.get("candidates", [])
    if not candidates:
        raise ProviderError("Google response did not include candidates")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "\n".join(part.get("text", "") for part in parts if part.get("text"))
    if text:
        return text
    raise ProviderError("Google response did not include text output")


def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if response.ok:
        return response.json()

    message = response.text[:500].replace("\n", " ")
    raise ProviderError(f"HTTP {response.status_code}: {message}")


def _normalize_review(provider_id: str, model: str, review: dict[str, Any]) -> dict[str, Any]:
    decision = str(review.get("decision", "REVISE")).strip().upper()
    if decision not in VALID_DECISIONS:
        decision = "REVISE"

    return {
        "provider": provider_id,
        "provider_name": PROVIDER_CONFIG[provider_id]["name"],
        "model": model,
        "decision": decision,
        "risk_score": round(_number(review.get("risk_score"), 5.0, 0.0, 10.0), 1),
        "value_score": round(_number(review.get("value_score"), 5.0, 0.0, 10.0), 1),
        "confidence": round(_number(review.get("confidence"), 0.5, 0.0, 1.0), 2),
        "rationale": _string(review.get("rationale"), "No rationale returned."),
        "top_risks": _string_list(review.get("top_risks")),
        "top_values": _string_list(review.get("top_values")),
        "required_changes": _string_list(review.get("required_changes")),
    }


def _baseline_vote(baseline: dict[str, Any]) -> dict[str, Any]:
    decision = str(baseline.get("decision", "REVISE")).strip().upper()
    if decision not in VALID_DECISIONS:
        decision = "REVISE"
    return {
        "provider": "baseline",
        "provider_name": "Deterministic Baseline",
        "decision": decision,
        "risk_score": _number(baseline.get("risk_score"), 5.0, 0.0, 10.0),
        "value_score": _number(baseline.get("value_score"), 5.0, 0.0, 10.0),
        "confidence": _number(baseline.get("confidence"), 0.5, 0.0, 1.0),
    }


def _timeout_seconds() -> int:
    raw = os.getenv("LLM_REVIEW_TIMEOUT_SECONDS", "45")
    try:
        return max(5, min(180, int(raw)))
    except ValueError:
        return 45


def _number(value: Any, default: float, low: float, high: float) -> float:
    try:
        return _clamp(float(value), low, high)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _string(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value[:6] if str(item).strip()]


def _dedupe(values: Any) -> list[str]:
    seen = set()
    output = []
    for value in values:
        normalized = str(value).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            output.append(normalized)
    return output


def _display_name(provider_id: str) -> str:
    if provider_id == "baseline":
        return "Baseline"
    return PROVIDER_CONFIG.get(provider_id, {}).get("name", provider_id)
