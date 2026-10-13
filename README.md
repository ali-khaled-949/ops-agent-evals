# ops-agent-evals

A tool-using **agent loop with guardrails and an evaluation harness**, applied to a
back-office task: reviewing supplier invoices against purchase orders and deciding
whether to approve or hold each one. Python, SQLite, standard library only.

**This is a demo I built to show how I structure and test an agent, not a working
AI product.** There is no LLM in this repo: the "model" is a deterministic stand-in
that follows the policy, plus deliberately broken ones. The point is everything
around the model, which is where agents fail in production. Data is synthetic.

## What it covers

| Concern | How it is handled |
|---|---|
| Model boundary | The loop only needs `next_step(task, history)` returning a tool call or a final answer. A real function-calling LLM plugs in behind that one method. |
| Tool validation | Every model-proposed call is checked: known tool, exact argument names, string types. Bad calls return a readable error the model can correct. |
| Least privilege | Four read tools and one write tool. The write tool accepts only six named decisions and requires a reason. |
| Guardrails | A run may decide only the invoice it was given, only once, within a step limit. Free-text output that is not a tool call stops the run. |
| Injection | Tool arguments go to SQL as parameters; a test passes `' OR '1'='1` and nothing happens. |
| Audit trail | Each run keeps every call, result, and error. |
| Evaluation | 12 labelled cases covering every decision type and the tolerance boundary. Reports accuracy, average steps, and **wrong approvals** (the costly error). |
| Release gate | `python -m agent.evals` exits non-zero when accuracy drops or any wrong approval appears; CI runs it on every push. |
| Regression test | A stand-in model that "forgets" the duplicate check is caught by the harness: one miss, one wrong approval, gate fails. |

## Run it

```bash
pip install -r requirements.txt
pytest -q               # 19 tests
python -m agent.evals   # accuracy 100%   wrong approvals 0   avg steps 4.7
```

## Layout

`agent/loop.py` the loop and guardrails · `agent/tools.py` tool specs and validation ·
`agent/models.py` stand-in models · `agent/evals.py` cases, scoring, gate · `agent/data.py` synthetic data

## Limits

- No LLM adapter is included, so nothing here measures a real model's accuracy, cost, or latency.
- 12 cases is a smoke set; a real evaluation needs hundreds of cases drawn from real exceptions.
- The policy (2% tolerance, exact duplicate match) is simplified.
- No human review queue for held invoices and no retries on tool failures.
