# Agent Review Board

A local-first, offline Streamlit app that simulates a multi-agent review board for evaluating AI workflow proposals. No external APIs, no database — runs entirely on your machine.

---

## What It Does

You paste an AI workflow proposal into the app. Three agents evaluate it:

| Agent | Role |
|---|---|
| **Risk Agent** | Scores operational, safety, compliance, and reliability risk (0–10, higher = riskier) |
| **Value Agent** | Scores business value, efficiency gain, cost reduction, and deployment upside (0–10, higher = better) |
| **Decision Synthesizer** | Weighs both outputs and issues a board-level recommendation |

The synthesizer issues one of three decisions:

- **APPROVE** — low risk, strong value. Proceed.
- **REVISE** — moderate risk or insufficient value. Refine first.
- **REJECT** — unacceptable risk or too little value to justify effort.

Every review is appended to `outputs/audit_log.json` for traceability.

---

## How the Agent Review Process Works

### Risk Agent (`agents/risk_agent.py`)

Uses keyword lists for four risk dimensions. Each keyword hit increases the score; mitigating language (e.g., "human review", "audit trail", "tested") reduces it. Scores are capped at 10.

### Value Agent (`agents/value_agent.py`)

Uses keyword lists for four value dimensions. Positive signals increase the score; detractors (e.g., "vendor lock", "not scalable", "hard coded") reduce it.

### Decision Synthesizer (`agents/decision_synthesizer.py`)

Applies threshold logic:

```
REJECT  : overall_risk >= 7.0
          OR (risk >= 5.5 AND value < 3.0)
APPROVE : risk < 4.0 AND value >= 5.0
REVISE  : everything else
```

A confidence score (0–1) is derived from each score's distance from the nearest decision boundary.

---

## Installation

```bash
# Clone the repo
git clone https://github.com/driaialchemy/2testingofsoftwareengineering.git
cd 2testingofsoftwareengineering

# Create and activate a virtual environment (recommended)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Run the App

```bash
streamlit run app.py
```

The app opens in your browser at `http://localhost:8501`.

---

## Run Tests

```bash
python -m pytest tests/ -v
```

All tests are deterministic and require no network access.

---

## Project Structure

```
.
├── app.py                        # Streamlit UI entry point
├── agents/
│   ├── __init__.py
│   ├── risk_agent.py             # Operational/safety/compliance/reliability scoring
│   ├── value_agent.py            # Business value / efficiency / cost / deployment scoring
│   └── decision_synthesizer.py  # APPROVE / REVISE / REJECT logic
├── data/
│   └── sample_cases.json         # Pre-loaded example proposals
├── outputs/
│   └── audit_log.json            # Appended after each review (auto-created)
├── tests/
│   └── test_agents.py            # pytest test suite
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Limitations

- Scoring is **keyword-based** — it does not understand context or nuance.
- A cleverly worded proposal with no risk keywords will score 0 risk even if risky.
- The scoring weights are fixed heuristics, not calibrated on real data.
- No authentication, no multi-user support.
- Audit log is a flat JSON file; not suitable for large volumes.

---

## Possible Future Improvements

- Replace keyword scoring with an LLM-based scoring pass (local via Ollama, or API-based).
- Add a weighting slider so users can adjust how much risk vs. value matters.
- Export audit log to CSV or PDF.
- Add a feedback loop: let users mark decisions as correct/incorrect to tune thresholds.
- Plug in a real compliance rulebook (GDPR, HIPAA checklists) for the compliance dimension.
- Role-based access: different reviewers see different agent panels.
