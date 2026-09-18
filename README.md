# Agent Review Board

A Streamlit app that evaluates AI workflow proposals with a deterministic local
baseline and optional LLM reviewers from OpenAI, Anthropic, and Google. The LLM
review path is off by default and only runs when API keys are configured and the
sidebar checkbox is enabled.

## For A Novice Reader

Think of this app as a review board for AI project ideas. You paste in a proposed
AI workflow, and the app tells you whether the idea looks ready to approve, needs
revision, or should be rejected because the risk is too high.

The app can work completely locally with fixed scoring rules. If API keys are
configured, you can also ask outside AI models to act like additional reviewers,
then compare their opinions with the local baseline.

## For A Technical Reader

The app is a Streamlit workflow-review tool with deterministic risk/value agents,
a threshold-based decision synthesizer, optional structured LLM reviewer calls,
and a local arbiter. The deterministic path is testable and API-free. The LLM
path accepts OpenAI, Anthropic, and Google credentials through ignored `.env`
configuration, parses structured reviews, and records review outcomes to a local
audit log for traceability.

## What It Does

You paste an AI workflow proposal into the app. The board evaluates it with:

| Agent | Role |
|---|---|
| Risk Agent | Scores operational, safety, compliance, and reliability risk from 0-10 |
| Value Agent | Scores business value, efficiency gain, cost reduction, and deployment upside from 0-10 |
| Decision Synthesizer | Combines deterministic risk and value outputs into APPROVE, REVISE, or REJECT |
| Optional LLM Reviewers | Ask OpenAI, Anthropic, and Google for independent structured reviews |
| Arbiter | Combines the deterministic baseline and LLM reviews into one final recommendation |

Every review is appended to `outputs/audit_log.json` for traceability.

## Decision Logic

The deterministic synthesizer applies threshold logic:

```text
REJECT  : overall_risk >= 7.0
          OR (risk >= 5.5 AND value < 3.0)
APPROVE : risk < 4.0 AND value >= 5.0
REVISE  : everything else
```

When LLM review is enabled, the local arbiter compares the baseline with the LLM
reviewer outputs. It keeps the final recommendation explainable by using average
risk/value scores, decision agreement, and high-risk rejection flags.

## Installation

```powershell
git clone https://github.com/driaialchemy/Agent-Workflow-Review.git
cd Agent-Workflow-Review

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Optional LLM Environment Setup

Create a local `.env` file from the safe template:

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in the keys you want to use:

```text
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
GOOGLE_API_KEY=your_google_key_here

OPENAI_MODEL=gpt-4.1-mini
ANTHROPIC_MODEL=claude-sonnet-4-20250514
GOOGLE_MODEL=gemini-2.5-flash

LLM_REVIEW_TIMEOUT_SECONDS=45
GOOGLE_THINKING_BUDGET=0
```

Notes:

- `.env` is ignored by git. Do not commit real API keys.
- You can configure one, two, or all three providers.
- `GEMINI_API_KEY` is also accepted as a fallback for Google.
- Gemini 2.5 thinking is disabled by default for short JSON reviews. Set `GOOGLE_THINKING_BUDGET` higher only if you want deeper Gemini reasoning.
- LLM reviewers can create API costs. They only run when you enable the sidebar checkbox.

## Run The App

```powershell
streamlit run app.py
```

The app opens in your browser at `http://localhost:8501`.

## Run Tests

```powershell
python -m pytest tests/ -v
```

Tests are deterministic and do not call external APIs.

## Project Structure

```text
.
|-- app.py
|-- agents/
|   |-- risk_agent.py
|   |-- value_agent.py
|   |-- decision_synthesizer.py
|   `-- llm_review.py
|-- data/
|   `-- sample_cases.json
|-- outputs/
|   `-- audit_log.json
|-- tests/
|   |-- test_agents.py
|   `-- test_llm_review.py
|-- .env.example
|-- .gitignore
|-- requirements.txt
`-- README.md
```

## Limitations

- The deterministic baseline is keyword-based and does not fully understand context.
- LLM reviewer quality depends on the chosen provider models and prompt adherence.
- The arbiter is intentionally local and simple so it remains auditable.
- Audit log storage is a flat JSON file and is not designed for large volumes.
