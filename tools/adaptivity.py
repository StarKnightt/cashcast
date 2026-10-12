"""Do the 80% ranges adapt to the client? Split the backtest by how erratic each client was.

Reads results/backtest_predictions.csv (written by cashcast.backtest), adds an
"adaptivity" block to results/backtest.json and copies it to web/data/.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from cashcast import data, features

ROOT = Path(__file__).resolve().parent.parent
P = pd.read_csv(ROOT / "results" / "backtest_predictions.csv", dtype={"invoice_id": str})
f = features.add_labels(data.load_ibm())

spread = {}
for _, g in f.groupby("client"):
    for i, r in g.iterrows():
        prior = g[g["paid"] < r["issued"]]["days_to_pay"]
        spread[r["invoice_id"]] = prior.std() if len(prior) >= 3 else np.nan
P["client_spread"] = P["invoice_id"].map(spread)
tab = P[P.model == "TabPFN"]
cuts = tab["client_spread"].quantile([1 / 3, 2 / 3]).to_numpy()
labels = ["Steady clients", "Middle", "Erratic clients"]
P["group"] = pd.cut(P["client_spread"], [-np.inf, cuts[0], cuts[1], np.inf], labels=labels)

rows = []
for model in ["TabPFN", "Logistic / linear", "Gradient-boosted trees"]:
    for grp in labels:
        g = P[(P.model == model) & (P.group == grp)]
        rows.append(
            {
                "model": model,
                "group": grp,
                "invoices": int(len(g)),
                "coverage_80": round(float(((g.days >= g.lo) & (g.days <= g.hi)).mean()), 3),
                "band_width": round(float((g.hi - g.lo).mean()), 1),
            }
        )
out = {
    "spread_cuts_days": [round(float(c), 1) for c in cuts],
    "excluded_under_3_prior": int(P[P.model == "TabPFN"]["client_spread"].isna().sum()),
    "rows": rows,
}
bt = json.loads((ROOT / "results" / "backtest.json").read_text())
bt["adaptivity"] = out
(ROOT / "results" / "backtest.json").write_text(json.dumps(bt, indent=2))
(ROOT / "web" / "data" / "backtest.json").write_text(json.dumps(bt, indent=2))
for r in rows:
    print(r)
print(out["spread_cuts_days"], out["excluded_under_3_prior"])
