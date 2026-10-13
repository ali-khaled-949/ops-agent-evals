"""Synthetic accounts-payable data in SQLite. Vendors, purchase orders and invoices are made up."""
import sqlite3

DDL = """
CREATE TABLE vendor (id TEXT PRIMARY KEY, name TEXT NOT NULL, approved INTEGER NOT NULL);
CREATE TABLE purchase_order (id TEXT PRIMARY KEY, vendor_id TEXT NOT NULL, amount_cents INTEGER NOT NULL, open INTEGER NOT NULL);
CREATE TABLE invoice (id TEXT PRIMARY KEY, vendor_id TEXT NOT NULL, po_id TEXT, invoice_number TEXT NOT NULL,
                      amount_cents INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'received');
"""

VENDORS = [("V1", "Northwind Paper", 1), ("V2", "Acme Janitorial", 1), ("V3", "Unvetted Supplies", 0)]
PURCHASE_ORDERS = [("PO-100", "V1", 50_000, 1), ("PO-101", "V1", 120_000, 1), ("PO-200", "V2", 30_000, 1),
                   ("PO-201", "V2", 80_000, 0), ("PO-300", "V3", 10_000, 1)]
# id, vendor, po, invoice_number, amount_cents, status
INVOICES = [
    ("INV-1", "V1", "PO-100", "N-5001", 50_000, "received"),    # exact match
    ("INV-2", "V1", "PO-101", "N-5002", 121_000, "received"),   # 0.8% over: inside tolerance
    ("INV-3", "V1", "PO-101", "N-5003", 135_000, "received"),   # 12.5% over
    ("INV-4", "V2", None, "A-900", 15_000, "received"),         # no PO
    ("INV-5", "V2", "PO-200", "A-901", 30_000, "received"),     # exact match
    ("INV-6", "V2", "PO-200", "A-901", 30_000, "received"),     # same vendor + number as INV-5
    ("INV-7", "V2", "PO-201", "A-902", 80_000, "received"),     # PO is closed
    ("INV-8", "V3", "PO-300", "U-1", 10_000, "received"),       # vendor not approved
    ("INV-9", "V1", "PO-999", "N-5004", 20_000, "received"),    # PO does not exist
    ("INV-10", "V2", "PO-100", "A-903", 50_000, "received"),    # PO belongs to another vendor
    ("INV-11", "V1", "PO-100", "N-5005", 48_000, "received"),   # under the PO: fine
    ("INV-12", "V1", "PO-101", "N-5006", 122_400, "received"),  # exactly 2.0% over: at the limit
]


def build(path=":memory:"):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(DDL)
    db.executemany("INSERT INTO vendor VALUES (?,?,?)", VENDORS)
    db.executemany("INSERT INTO purchase_order VALUES (?,?,?,?)", PURCHASE_ORDERS)
    db.executemany("INSERT INTO invoice VALUES (?,?,?,?,?,?)", INVOICES)
    db.commit()
    return db
