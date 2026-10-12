"""Write web/sample.csv: 20 clients from the IBM sample in Cashcast's CSV format.

Invoices issued after the cut-off are dropped, and payments made after it are blanked,
so the file looks like a real ledger on 2013-09-01 with some invoices still open.
"""

from pathlib import Path

import pandas as pd

from cashcast import data

CUT = pd.Timestamp("2013-09-01")
OUT = Path(__file__).resolve().parent.parent / "web" / "sample.csv"

d = data.load_ibm()
clients = sorted(d["client"].unique())[:20]
s = d[d["client"].isin(clients) & (d["issued"] < CUT)].copy()
s.loc[s["paid"] >= CUT, "paid"] = pd.NaT
for c in ["issued", "due", "paid"]:
    s[c] = s[c].dt.strftime("%Y-%m-%d")
s[["client", "invoice_id", "issued", "due", "amount", "paid"]].to_csv(OUT, index=False)
print(len(s), "rows,", s["paid"].isna().sum(), "open")
