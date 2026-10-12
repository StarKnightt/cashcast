"""Month-by-month backtest on IBM's public accounts receivable sample.

For each month of 2013 (January to October), every model is trained only on invoices
that were already paid before the month started, then predicts the invoices issued
during that month. Run: python -m cashcast.backtest
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import data, features, model

OUT = Path(__file__).resolve().parent.parent / "results"
MONTHS = pd.period_range("2013-01", "2013-10", freq="M")
CHASE_SHARE = 0.2


def baselines(Xtr, ytr, dtr, Xte, fte, base_rate, base_days):
    out = {}
    n = fte["prior_paid"].fillna(0).to_numpy()
    share = fte["prior_late_share"].fillna(base_rate).to_numpy()
    out["Base rate"] = (np.full(len(Xte), base_rate), np.full(len(Xte), base_days), None)
    out["Client history"] = (
        (share * n + base_rate * 2) / (n + 2),
        fte["prior_mean_days"].fillna(base_days).to_numpy(),
        None,
    )
    lin_c = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=2000))
    lin_r = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge())
    lin_c.fit(Xtr, ytr)
    lin_r.fit(Xtr, dtr)
    resid = dtr.to_numpy() - lin_r.predict(Xtr)
    r_lo, r_hi = np.quantile(resid, [0.1, 0.9])
    lin_days = lin_r.predict(Xte)
    out["Logistic / linear"] = (lin_c.predict_proba(Xte)[:, 1], lin_days, (lin_days + r_lo, lin_days + r_hi))
    hc = HistGradientBoostingClassifier(random_state=0).fit(Xtr, ytr)
    hr = HistGradientBoostingRegressor(random_state=0).fit(Xtr, dtr)
    lo = HistGradientBoostingRegressor(loss="quantile", quantile=0.1, random_state=0).fit(Xtr, dtr)
    hi = HistGradientBoostingRegressor(loss="quantile", quantile=0.9, random_state=0).fit(Xtr, dtr)
    out["Gradient-boosted trees"] = (
        hc.predict_proba(Xte)[:, 1],
        hr.predict(Xte),
        (lo.predict(Xte), hi.predict(Xte)),
    )
    return out


def chase_recall(month, p, y):
    """Chase the riskiest 20% of each month's invoices: what share of late ones is caught?"""
    caught = total = 0
    for m in np.unique(month):
        sel = month == m
        k = max(1, int(round(CHASE_SHARE * sel.sum())))
        top = np.argsort(-p[sel], kind="stable")[:k]
        caught += y[sel][top].sum()
        total += y[sel].sum()
    return caught / total


def main():
    raw = data.load_ibm()
    f = features.build(raw)
    X = features.matrix(f)
    preds = []
    timings = []
    for m in MONTHS:
        start = m.start_time
        tr = f.index[(f["paid"] < start)]
        te = f.index[f["issued"].dt.to_period("M") == m]
        Xtr, ytr = model.recent(X.loc[tr], f.loc[tr, "late"], f.loc[tr, "issued"])
        dtr = f.loc[Xtr.index, "days_to_pay"]
        ytr = ytr.astype(int)
        t0 = time.perf_counter()
        fc = model.Forecaster().fit(Xtr, ytr, dtr)
        res = fc.predict(X.loc[te])
        secs = time.perf_counter() - t0
        timings.append({"month": str(m), "train": len(Xtr), "test": len(te), "seconds": round(secs, 1)})
        print(f"{m}: train {len(Xtr)}, test {len(te)}, TabPFN {secs:.1f} s", flush=True)
        q = res["quantiles"]
        rows = {
            "TabPFN": (
                res["p_late"],
                model.quantile(q, 0.5),
                (model.quantile(q, 0.1), model.quantile(q, 0.9)),
            )
        }
        rows.update(
            baselines(
                Xtr, ytr, dtr, X.loc[te], f.loc[te],
                float(ytr.mean()), float(dtr.median()),
            )
        )
        for name, (p, days, band) in rows.items():
            part = pd.DataFrame(
                {
                    "invoice_id": f.loc[te, "invoice_id"].to_numpy(),
                    "month": str(m),
                    "model": name,
                    "p_late": np.clip(p, 1e-4, 1 - 1e-4),
                    "days_pred": days,
                    "lo": band[0] if band else np.nan,
                    "hi": band[1] if band else np.nan,
                    "late": f.loc[te, "late"].to_numpy(),
                    "days": f.loc[te, "days_to_pay"].to_numpy(),
                }
            )
            preds.append(part)
    P = pd.concat(preds, ignore_index=True)
    summary = []
    for name, g in P.groupby("model", sort=False):
        y = g["late"].to_numpy().astype(int)
        p = g["p_late"].to_numpy()
        row = {
            "model": name,
            "invoices": int(len(g)),
            "auc": round(roc_auc_score(y, p), 3) if name != "Base rate" else 0.5,
            "brier": round(brier_score_loss(y, p), 3),
            "log_loss": round(log_loss(y, p), 3),
            "accuracy": round(float(((p >= 0.5) == y).mean()), 3),
            "chase_recall": round(chase_recall(g["month"].to_numpy(), p, y), 3),
            "days_mae": round(float(np.abs(g["days_pred"] - g["days"]).mean()), 2),
        }
        if g["lo"].notna().all():
            row["coverage_80"] = round(float(((g["days"] >= g["lo"]) & (g["days"] <= g["hi"])).mean()), 3)
            row["band_width"] = round(float((g["hi"] - g["lo"]).mean()), 1)
        summary.append(row)
    tab = P[P.model == "TabPFN"]
    bins = np.linspace(0, 1, 6)
    calib = []
    for lo_, hi_ in zip(bins[:-1], bins[1:]):
        s = tab[(tab.p_late >= lo_) & (tab.p_late < hi_ if hi_ < 1 else tab.p_late <= hi_)]
        if len(s):
            calib.append({"bin": f"{lo_:.1f} to {hi_:.1f}", "n": int(len(s)),
                          "predicted": round(float(s.p_late.mean()), 3),
                          "actual": round(float(s.late.mean()), 3)})
    OUT.mkdir(exist_ok=True)
    out = {
        "dataset": {
            "name": "IBM Watson Analytics sample: accounts receivable (late payment histories)",
            "invoices": int(len(f)),
            "clients": int(f["client"].nunique()),
            "late_share": round(float(f["late"].mean()), 3),
            "first_invoice": str(f["issued"].min().date()),
            "last_invoice": str(f["issued"].max().date()),
        },
        "months": [str(m) for m in MONTHS],
        "max_train_rows": model.MAX_TRAIN,
        "summary": summary,
        "calibration": calib,
        "timings": timings,
    }
    (OUT / "backtest.json").write_text(json.dumps(out, indent=2))
    P.to_csv(OUT / "backtest_predictions.csv", index=False)
    print(json.dumps(summary, indent=2))
    print(json.dumps(calib, indent=2))


if __name__ == "__main__":
    main()
