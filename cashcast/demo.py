"""Build the replay data for the web demo and score it against what really happened.

Run: python -m cashcast.demo   (writes web/data/replay.json and results/replay.json)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from . import data, features, forecast

ROOT = Path(__file__).resolve().parent.parent
DATES = pd.date_range("2013-02-01", "2013-11-01", freq="MS")


def main():
    f = features.build(data.load_ibm())
    X = features.matrix(f)
    snaps = []
    for d in DATES:
        t0 = time.perf_counter()
        s = forecast.score(f, X, d)
        s["seconds"] = round(time.perf_counter() - t0, 1)
        snaps.append(s)
        print(f"{d.date()}: {s['open_count']} open, {s['seconds']} s", flush=True)

    inv = pd.DataFrame([dict(r, as_of=s["as_of"]) for s in snaps for r in s["invoices"]])
    inv["late"] = (pd.to_datetime(inv["actual_paid"]) > pd.to_datetime(inv["due"])).astype(int)
    paid = pd.to_datetime(inv["actual_paid"])
    inv["in_band"] = (paid >= pd.to_datetime(inv["pay_lo"])) & (paid <= pd.to_datetime(inv["pay_hi"]))
    inv["err"] = (paid - pd.to_datetime(inv["pay_mid"])).dt.days.abs()
    op = inv[inv.status == "open"]
    wk = pd.DataFrame([w for s in snaps for w in s["weeks"]])
    flagged = op[op.p_late >= 0.5]
    check = {
        "snapshots": len(snaps),
        "open_invoice_rows": int(len(inv)),
        "not_yet_due_rows": int(len(op)),
        "late_auc": round(roc_auc_score(op.late, op.p_late), 3),
        "late_brier": round(brier_score_loss(op.late, op.p_late), 3),
        "late_base_rate": round(float(op.late.mean()), 3),
        "reminder_now_rows": int(len(flagged)),
        "reminder_now_late_share": round(float(flagged.late.mean()), 3) if len(flagged) else None,
        "pay_band_coverage": round(float(inv.in_band.mean()), 3),
        "pay_date_mae_days": round(float(inv.err.mean()), 2),
        "cash_weeks": int(len(wk)),
        "cash_band_coverage": round(float(((wk.actual >= wk.lo) & (wk.actual <= wk.hi)).mean()), 3),
        "cash_week_mae": round(float((wk.actual - wk.expected).abs().mean()), 1),
        "cash_week_mean_actual": round(float(wk.actual.mean()), 1),
        "seconds_per_snapshot": round(float(np.mean([s["seconds"] for s in snaps])), 1),
    }
    print(json.dumps(check, indent=2))
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "replay.json").write_text(json.dumps(check, indent=2))
    web = ROOT / "web" / "data"
    web.mkdir(parents=True, exist_ok=True)
    (web / "replay.json").write_text(json.dumps({"check": check, "snapshots": snaps}, separators=(",", ":")))


if __name__ == "__main__":
    main()
