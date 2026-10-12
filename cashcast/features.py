"""Issue-time features: only what you know on the day an invoice is sent."""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = [
    "amount",
    "terms_days",
    "amount_vs_client",
    "prior_paid",
    "prior_mean_days",
    "prior_late_share",
    "prior_mean_late",
    "last_days",
    "last_late",
    "days_since_last_invoice",
    "open_count",
    "open_amount",
    "issue_month",
    "issue_weekday",
]
OPTIONAL = ["region", "channel"]


def add_labels(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["days_to_pay"] = (d["paid"] - d["issued"]).dt.days
    d["days_late"] = (d["paid"] - d["due"]).dt.days.clip(lower=0)
    d["late"] = (d["paid"] > d["due"]).astype(float)
    d.loc[d["paid"].isna(), ["days_to_pay", "days_late", "late"]] = np.nan
    return d


def build(d: pd.DataFrame) -> pd.DataFrame:
    """Return one feature row per invoice, using only invoices paid before it was issued."""
    d = add_labels(d)
    rows = []
    for _, g in d.groupby("client", sort=False):
        g = g.sort_values("issued")
        issued = g["issued"].to_numpy()
        paid = g["paid"].to_numpy()
        amount = g["amount"].to_numpy()
        dtp = g["days_to_pay"].to_numpy()
        late = g["late"].to_numpy()
        dlate = g["days_late"].to_numpy()
        for i, idx in enumerate(g.index):
            t = issued[i]
            before = issued < t
            known = before & (paid < t)  # NaT compares False, so open invoices drop out
            still_open = before & ~(paid < t)
            k_order = np.where(known)[0]
            last = k_order[np.argmax(paid[k_order])] if len(k_order) else None
            prev_issued = issued[before]
            rows.append(
                {
                    "idx": idx,
                    "amount_vs_client": amount[i] / amount[before].mean() if before.any() else 1.0,
                    "prior_paid": int(known.sum()),
                    "prior_mean_days": dtp[known].mean() if known.any() else np.nan,
                    "prior_late_share": late[known].mean() if known.any() else np.nan,
                    "prior_mean_late": dlate[known].mean() if known.any() else np.nan,
                    "last_days": dtp[last] if last is not None else np.nan,
                    "last_late": late[last] if last is not None else np.nan,
                    "days_since_last_invoice": (
                        (t - prev_issued.max()) / np.timedelta64(1, "D") if len(prev_issued) else np.nan
                    ),
                    "open_count": int(still_open.sum()),
                    "open_amount": float(amount[still_open].sum()),
                }
            )
    f = pd.DataFrame(rows).set_index("idx").sort_index()
    out = d.join(f)
    out["terms_days"] = (out["due"] - out["issued"]).dt.days
    out["issue_month"] = out["issued"].dt.month
    out["issue_weekday"] = out["issued"].dt.weekday
    return out


def matrix(f: pd.DataFrame) -> pd.DataFrame:
    """Numeric model input. Optional text columns become category codes."""
    cols = FEATURES + [c for c in OPTIONAL if c in f.columns]
    X = f[cols].copy()
    for c in OPTIONAL:
        if c in X.columns:
            X[c] = X[c].astype("category").cat.codes.astype(float)
    return X.astype(float)
