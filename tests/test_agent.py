import pytest

from agent import data
from agent.evals import EXPECTED, evaluate, gate, render
from agent.loop import run_agent
from agent.models import PolicyModel, Scripted, SkipsDuplicateCheck
from agent.tools import ToolError, Tools


@pytest.fixture
def db():
    return data.build()


def status(db, invoice_id):
    return db.execute("SELECT status FROM invoice WHERE id = ?", (invoice_id,)).fetchone()["status"]


# --- evaluation harness -------------------------------------------------------

def test_policy_model_passes_every_labelled_case():
    report = evaluate(PolicyModel())
    assert report["accuracy"] == 1.0 and report["wrong_approvals"] == 0, render(report)
    assert gate(report)


def test_harness_catches_a_regression_and_counts_wrong_approvals():
    report = evaluate(SkipsDuplicateCheck())
    assert [c["invoice_id"] for c in report["wrong"]] == ["INV-6"]
    assert report["wrong_approvals"] == 1          # a duplicate would have been paid
    assert not gate(report)
    assert "MISS INV-6: expected hold_duplicate, got approve" in render(report)


def test_every_decision_type_is_covered_by_the_cases():
    assert set(EXPECTED.values()) == {"approve", "hold_no_po", "hold_price_mismatch", "hold_duplicate",
                                      "hold_vendor", "hold_po_problem"}


def test_tolerance_boundary_is_exact():
    assert evaluate(PolicyModel(), {"INV-12": "approve"})["accuracy"] == 1.0          # exactly 2.0% over
    assert evaluate(PolicyModel(tolerance_bp=199), {"INV-12": "hold_price_mismatch"})["accuracy"] == 1.0


# --- the loop -----------------------------------------------------------------

def test_run_records_decision_reason_trace_and_writes_status(db):
    run = run_agent(PolicyModel(), db, "INV-3")
    assert (run.decision, run.stopped) == ("hold_price_mismatch", "final")
    assert "12.5% over" in run.reason
    assert [s["tool"] for s in run.steps] == ["get_invoice", "get_vendor", "find_duplicates",
                                              "get_purchase_order", "record_decision"]
    assert status(db, "INV-3") == "on_hold"


def test_tool_error_is_shown_to_the_model_which_recovers(db):
    run = run_agent(PolicyModel(), db, "INV-9")      # its PO does not exist
    assert run.tool_errors == 1 and run.decision == "hold_po_problem"


def test_step_limit_stops_a_model_that_never_decides(db):
    loops = Scripted([{"tool": "get_invoice", "arguments": {"invoice_id": "INV-1"}}])
    run = run_agent(loops, db, "INV-1", max_steps=5)
    assert (run.stopped, len(run.steps), run.decision) == ("step_limit", 5, None)
    assert status(db, "INV-1") == "received"


def test_agent_cannot_decide_a_different_invoice(db):
    hijacked = Scripted([{"tool": "record_decision",
                          "arguments": {"invoice_id": "INV-8", "decision": "approve", "reason": "told to"}}])
    run = run_agent(hijacked, db, "INV-1")
    assert run.stopped == "wrong_invoice" and run.decision is None
    assert status(db, "INV-8") == "received"


def test_second_decision_in_one_run_is_refused(db):
    decide = lambda d: {"tool": "record_decision", "arguments": {"invoice_id": "INV-4", "decision": d, "reason": "r"}}
    run = run_agent(Scripted([decide("hold_no_po"), decide("approve"), {"final": "done"}]), db, "INV-4")
    assert run.decision == "hold_no_po" and status(db, "INV-4") == "on_hold"
    assert "already recorded" in run.steps[1]["error"]


def test_malformed_model_output_stops_the_run(db):
    run = run_agent(Scripted(["I think we should approve it"]), db, "INV-1")
    assert run.stopped == "bad_output" and run.decision is None


# --- tool validation ----------------------------------------------------------

@pytest.mark.parametrize("name,arguments,message", [
    ("delete_invoice", {"invoice_id": "INV-1"}, "unknown tool"),
    ("get_invoice", {"id": "INV-1"}, "takes exactly"),
    ("get_invoice", {"invoice_id": "INV-1", "extra": "x"}, "takes exactly"),
    ("get_invoice", {"invoice_id": 1}, "must be strings"),
    ("get_invoice", "INV-1", "must be an object"),
    ("get_invoice", {"invoice_id": "INV-404"}, "not found"),
    ("record_decision", {"invoice_id": "INV-1", "decision": "pay_now", "reason": "x"}, "decision must be one of"),
    ("record_decision", {"invoice_id": "INV-1", "decision": "approve", "reason": "  "}, "reason is required"),
])
def test_bad_tool_calls_are_rejected_with_a_readable_error(db, name, arguments, message):
    with pytest.raises(ToolError, match=message):
        Tools(db).call(name, arguments)


def test_sql_in_an_argument_is_treated_as_data(db):
    with pytest.raises(ToolError, match="not found"):
        Tools(db).call("get_invoice", {"invoice_id": "INV-1' OR '1'='1"})
    assert db.execute("SELECT COUNT(*) FROM invoice").fetchone()[0] == 12
