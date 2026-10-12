"""Load invoice histories into one simple schema.

Columns used everywhere else:
    client, invoice_id, issued, due, amount, paid   (paid is NaT for open invoices)
Optional columns: region, channel.
"""

from __future__ import annotations

from pathlib import Path
from urllib.request import urlretrieve

import pandas as pd

IBM_URL = (
    "https://raw.githubusercontent.com/pthiagu2/DataMining/master/"
    "WA_Fn-UseC_-Accounts-Receivable.csv"
)
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "ibm-accounts-receivable.csv"

REQUIRED = ["client", "invoice_id", "issued", "due", "amount"]


def fetch_ibm() -> Path:
    """Download IBM's public accounts receivable sample (not stored in the repo)."""
    if not RAW.exists():
        RAW.parent.mkdir(parents=True, exist_ok=True)
        urlretrieve(IBM_URL, RAW)
    return RAW


def load_ibm() -> pd.DataFrame:
    d = pd.read_csv(fetch_ibm(), dtype={"customerID": str, "invoiceNumber": str})
    out = pd.DataFrame(
        {
            "client": d["customerID"],
            "invoice_id": d["invoiceNumber"],
            "issued": pd.to_datetime(d["InvoiceDate"], format="%m/%d/%Y"),
            "due": pd.to_datetime(d["DueDate"], format="%m/%d/%Y"),
            "amount": d["InvoiceAmount"].astype(float),
            "paid": pd.to_datetime(d["SettledDate"], format="%m/%d/%Y"),
            "region": d["countryCode"].astype(str),
            "channel": d["PaperlessBill"].str.lower(),
        }
    )
    return out.sort_values(["issued", "invoice_id"]).reset_index(drop=True)


def load_csv(path_or_buffer) -> pd.DataFrame:
    """Load a user CSV with columns client, invoice_id, issued, due, amount, paid."""
    d = pd.read_csv(path_or_buffer, dtype={"client": str, "invoice_id": str})
    d.columns = [c.strip().lower() for c in d.columns]
    missing = [c for c in REQUIRED if c not in d.columns]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")
    if "paid" not in d.columns:
        d["paid"] = pd.NaT
    for c in ["issued", "due", "paid"]:
        d[c] = pd.to_datetime(d[c], errors="coerce")
    if d["issued"].isna().any() or d["due"].isna().any():
        raise ValueError("Every row needs a valid issued and due date.")
    d["amount"] = pd.to_numeric(d["amount"], errors="coerce")
    if d["amount"].isna().any():
        raise ValueError("Every row needs a numeric amount.")
    keep = REQUIRED + ["paid"] + [c for c in ("region", "channel") if c in d.columns]
    return d[keep].sort_values(["issued", "invoice_id"]).reset_index(drop=True)
