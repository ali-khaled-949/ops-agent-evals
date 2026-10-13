"""Evaluation harness: run the agent over labelled cases and score it.

Usage:  python -m agent.evals
"""
from . import data
from .loop import run_agent
from .models import PolicyModel

# invoice id -> the decision a careful accounts-payable clerk would make
EXPECTED = {
    "INV-1": "approve", "INV-2": "approve", "INV-3": "hold_price_mismatch", "INV-4": "hold_no_po",
    "INV-5": "approve", "INV-6": "hold_duplicate", "INV-7": "hold_po_problem", "INV-8": "hold_vendor",
    "INV-9": "hold_po_problem", "INV-10": "hold_po_problem", "INV-11": "approve", "INV-12": "approve",
}


def evaluate(model, expected=EXPECTED):
    """Each case gets a fresh database so one decision cannot leak into the next."""
    cases = []
    for invoice_id, want in expected.items():
        run = run_agent(model, data.build(), invoice_id)
        cases.append({"invoice_id": invoice_id, "expected": want, "got": run.decision, "ok": run.decision == want,
                      "stopped": run.stopped, "steps": len(run.steps), "tool_errors": run.tool_errors})
    wrong = [c for c in cases if not c["ok"]]
    # The costly mistake is paying something that should have been held.
    wrong_approvals = [c for c in wrong if c["got"] == "approve"]
    return {
        "cases": cases,
        "accuracy": (len(cases) - len(wrong)) / len(cases),
        "wrong": wrong,
        "wrong_approvals": len(wrong_approvals),
        "avg_steps": sum(c["steps"] for c in cases) / len(cases),
    }


def render(report):
    lines = [f"accuracy {report['accuracy']:.0%}   wrong approvals {report['wrong_approvals']}   "
             f"avg steps {report['avg_steps']:.1f}"]
    lines += [f"  MISS {c['invoice_id']}: expected {c['expected']}, got {c['got']}" for c in report["wrong"]]
    return "\n".join(lines)


def gate(report, min_accuracy=1.0, max_wrong_approvals=0):
    """Release gate for CI: fail the build when a prompt or model change makes the agent worse."""
    return report["accuracy"] >= min_accuracy and report["wrong_approvals"] <= max_wrong_approvals


if __name__ == "__main__":
    result = evaluate(PolicyModel())
    print(render(result))
    raise SystemExit(0 if gate(result) else 1)
