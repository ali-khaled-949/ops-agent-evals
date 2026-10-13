"""Stand-in models for the demo and tests. No network and no API key.

`PolicyModel` plays the part of a well-behaved LLM: it decides the next tool call
from what it has seen so far. The others misbehave on purpose so the loop's
guardrails and the evaluation harness have something to catch.
"""
TOLERANCE_BP = 200  # an invoice may exceed its PO by up to 2.00%


def _results(history, tool):
    return [s["result"] for s in history if s.get("tool") == tool and "result" in s]


def _failed(history, tool):
    return any(s.get("tool") == tool and "error" in s for s in history)


class PolicyModel:
    """Follows the accounts-payable policy one tool call at a time."""

    def __init__(self, tolerance_bp=TOLERANCE_BP):
        self.tolerance_bp = tolerance_bp

    def next_step(self, task, history):
        invoice_id = task.split()[2]
        if any(s.get("tool") == "record_decision" and "result" in s for s in history):
            return {"final": "Decision recorded."}

        def decide(decision, reason):
            return {"tool": "record_decision",
                    "arguments": {"invoice_id": invoice_id, "decision": decision, "reason": reason}}

        invoices = _results(history, "get_invoice")
        if not invoices:
            return {"tool": "get_invoice", "arguments": {"invoice_id": invoice_id}}
        inv = invoices[0]

        vendors = _results(history, "get_vendor")
        if not vendors:
            return {"tool": "get_vendor", "arguments": {"vendor_id": inv["vendor_id"]}}
        if not vendors[0]["approved"]:
            return decide("hold_vendor", f"vendor {vendors[0]['name']} is not approved")

        duplicates = _results(history, "find_duplicates")
        if not duplicates:
            return {"tool": "find_duplicates", "arguments": {"invoice_id": invoice_id}}
        if duplicates[0]["earlier_invoices"]:
            return decide("hold_duplicate", f"same vendor and number as {duplicates[0]['earlier_invoices'][0]}")

        if inv["po_id"] is None:
            return decide("hold_no_po", "invoice has no purchase order")

        orders = _results(history, "get_purchase_order")
        if not orders:
            if _failed(history, "get_purchase_order"):
                return decide("hold_po_problem", f"purchase order {inv['po_id']} does not exist")
            return {"tool": "get_purchase_order", "arguments": {"po_id": inv["po_id"]}}
        po = orders[0]
        if po["vendor_id"] != inv["vendor_id"]:
            return decide("hold_po_problem", "purchase order belongs to a different vendor")
        if not po["open"]:
            return decide("hold_po_problem", "purchase order is closed")

        # Integer math: over tolerance when invoice * 10000 > po * (10000 + tolerance).
        if inv["amount_cents"] * 10_000 > po["amount_cents"] * (10_000 + self.tolerance_bp):
            over = (inv["amount_cents"] - po["amount_cents"]) * 100 / po["amount_cents"]
            return decide("hold_price_mismatch", f"invoice is {over:.1f}% over the purchase order")
        return decide("approve", "matches an open purchase order from an approved vendor")


class SkipsDuplicateCheck(PolicyModel):
    """A plausible regression: a prompt change that makes the model stop checking duplicates."""

    def next_step(self, task, history):
        if not _results(history, "find_duplicates") and _results(history, "get_vendor"):
            history = history + [{"tool": "find_duplicates", "result": {"earlier_invoices": []}}]
        return super().next_step(task, history)


class Scripted:
    """Replays a fixed list of steps; used to test how the loop handles bad model output."""

    def __init__(self, steps):
        self.steps = list(steps)

    def next_step(self, task, history):
        return self.steps[min(len(history), len(self.steps) - 1)]
