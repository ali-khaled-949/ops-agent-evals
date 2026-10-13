"""The agent loop: ask the model for the next step, run the tool, feed the result back.

The model is anything with `next_step(task, history) -> dict`, returning either
{"tool": name, "arguments": {...}} or {"final": text}. A real LLM adapter turns a
function-calling response into that shape; the loop does not care which model it is.
"""
from dataclasses import dataclass, field

from .tools import ToolError, Tools


@dataclass
class Run:
    invoice_id: str
    decision: str | None = None
    reason: str | None = None
    stopped: str = "final"          # final | step_limit | bad_output | wrong_invoice
    steps: list = field(default_factory=list)   # full trace: every call, result and error

    @property
    def tool_errors(self):
        return sum(1 for s in self.steps if "error" in s)


def run_agent(model, db, invoice_id, max_steps=8):
    tools = Tools(db)
    run = Run(invoice_id)
    task = f"Review invoice {invoice_id} and record exactly one decision for it."

    for _ in range(max_steps):
        step = model.next_step(task, run.steps)

        if not isinstance(step, dict) or not ({"tool", "final"} & set(step)):
            run.stopped = "bad_output"
            run.steps.append({"error": f"model output was not a tool call or a final answer: {step!r}"})
            break

        if "final" in step:
            break

        name, arguments = step.get("tool"), step.get("arguments", {})
        record = {"tool": name, "arguments": arguments}

        # Guardrail: the agent was asked about one invoice and may only decide that one.
        if name == "record_decision" and isinstance(arguments, dict) and arguments.get("invoice_id") != invoice_id:
            record["error"] = f"refused: this run may only decide {invoice_id}"
            run.steps.append(record)
            run.stopped = "wrong_invoice"
            break

        # Guardrail: one decision per run. A second attempt is refused, not applied.
        if name == "record_decision" and run.decision is not None:
            record["error"] = "refused: a decision is already recorded for this run"
            run.steps.append(record)
            continue

        try:
            record["result"] = tools.call(name, arguments)
        except ToolError as e:
            record["error"] = str(e)   # the model sees the error and can correct itself
        else:
            if name == "record_decision":
                run.decision, run.reason = arguments["decision"], arguments["reason"]
        run.steps.append(record)
    else:
        run.stopped = "step_limit"

    return run
