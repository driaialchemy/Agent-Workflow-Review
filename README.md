# Agent Review Board

A Streamlit app that evaluates AI workflow proposals with a deterministic local
baseline. Risk and value agents feed `decision_synthesizer`, which is the only
decision path.

## For A Novice Reader

Think of this app as a review board for AI project ideas. You paste in a proposed
AI workflow, and the app tells you whether the idea looks ready to approve, needs
revision, or should be rejected because the risk is too high.

The app works locally with fixed scoring rules. Low-risk proposals can
auto-clear; everything else goes through the synthesizer.

## For A Technical Reader

The app is a Streamlit workflow-review tool with deterministic risk/value agents
and a threshold-based decision synthesizer. The path is testable and API-free.
Outcomes are recorded to a local audit log and, when configured, posted to the
governance governor.

## What It Does

You paste an AI workflow proposal into the app. The board evaluates it with:

| Agent | Role |
|---|---|
| Risk Agent | Scores operational, safety, compliance, and reliability risk from 0-10 |
| Value Agent | Scores business value, efficiency gain, cost reduction, and deployment upside from 0-10 |
| Decision Synthesizer | Combines deterministic risk and value outputs into APPROVE, REVISE, or REJECT |

Every review is appended to `outputs/audit_log.json` for traceability.

## Decision Logic

The deterministic synthesizer applies threshold logic:

```text
REJECT  : overall_risk >= 7.0
          OR (risk >= 5.5 AND value < 3.0)
APPROVE : risk < 4.0 AND value >= 5.0
REVISE  : everything else
```

## Installation

```powershell
git clone https://github.com/driaialchemy/Agent-Workflow-Review.git
cd Agent-Workflow-Review

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
```

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
|   `-- decision_synthesizer.py
|-- data/
|   `-- sample_cases.json
|-- outputs/
|   `-- audit_log.json
|-- tests/
|   `-- test_agents.py
|-- .env.example
|-- .gitignore
|-- requirements.txt
`-- README.md
```

## Limitations

- The deterministic baseline is keyword-based and does not fully understand context.
- Audit log storage is a flat JSON file and is not designed for large volumes.
