"""The tools the model may call. Each has a JSON-schema-style spec and a Python function.

Read tools only read. The single write tool, `record_decision`, is the only way the
agent can change anything, and it refuses decisions outside the allowed set.
"""

DECISIONS = {"approve", "hold_no_po", "hold_price_mismatch", "hold_duplicate", "hold_vendor", "hold_po_problem"}

SPECS = [
    {"name": "get_invoice", "description": "Read one invoice.",
     "parameters": {"invoice_id": "string"}},
    {"name": "get_purchase_order", "description": "Read one purchase order.",
     "parameters": {"po_id": "string"}},
    {"name": "get_vendor", "description": "Read one vendor, including whether it is approved.",
     "parameters": {"vendor_id": "string"}},
    {"name": "find_duplicates", "description": "Other invoices from the same vendor with the same invoice number.",
     "parameters": {"invoice_id": "string"}},
    {"name": "record_decision", "description": f"Record the outcome. decision must be one of {sorted(DECISIONS)}.",
     "parameters": {"invoice_id": "string", "decision": "string", "reason": "string"}},
]
SPEC_BY_NAME = {s["name"]: s for s in SPECS}


class ToolError(Exception):
    """A problem the model can read and recover from (bad arguments, unknown record)."""


class Tools:
    def __init__(self, db):
        self.db = db

    def _one(self, sql, key, what):
        row = self.db.execute(sql, (key,)).fetchone()
        if row is None:
            raise ToolError(f"{what} {key!r} not found")
        return dict(row)

    def get_invoice(self, invoice_id):
        return self._one("SELECT * FROM invoice WHERE id = ?", invoice_id, "invoice")

    def get_purchase_order(self, po_id):
        return self._one("SELECT * FROM purchase_order WHERE id = ?", po_id, "purchase order")

    def get_vendor(self, vendor_id):
        return self._one("SELECT * FROM vendor WHERE id = ?", vendor_id, "vendor")

    def find_duplicates(self, invoice_id):
        inv = self.get_invoice(invoice_id)
        rows = self.db.execute(
            "SELECT id FROM invoice WHERE vendor_id = ? AND invoice_number = ? AND id < ? ORDER BY id",
            (inv["vendor_id"], inv["invoice_number"], invoice_id)).fetchall()
        # Only earlier invoices count, so the first copy is paid and later copies are held.
        return {"earlier_invoices": [r["id"] for r in rows]}

    def record_decision(self, invoice_id, decision, reason):
        if decision not in DECISIONS:
            raise ToolError(f"decision must be one of {sorted(DECISIONS)}")
        if not reason.strip():
            raise ToolError("a reason is required")
        self.get_invoice(invoice_id)
        status = "approved" if decision == "approve" else "on_hold"
        self.db.execute("UPDATE invoice SET status = ? WHERE id = ?", (status, invoice_id))
        self.db.commit()
        return {"recorded": decision}

    def call(self, name, arguments):
        """Validate a model-proposed call against the spec, then run it."""
        spec = SPEC_BY_NAME.get(name)
        if spec is None:
            raise ToolError(f"unknown tool {name!r}; available: {sorted(SPEC_BY_NAME)}")
        if not isinstance(arguments, dict):
            raise ToolError("arguments must be an object")
        expected = set(spec["parameters"])
        if set(arguments) != expected:
            raise ToolError(f"{name} takes exactly {sorted(expected)}, got {sorted(arguments)}")
        if not all(isinstance(v, str) for v in arguments.values()):
            raise ToolError("all arguments must be strings")
        return getattr(self, name)(**arguments)
