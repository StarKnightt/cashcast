"""Score open invoices as of a date: late risk, payment date range, next weeks of cash."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import features, model

WEEKS = 8
DRAWS = 2000


def action(status: str, p_late: float) -> str:
    if status == "overdue":
        return "Overdue: contact today"
    if p_late >= 0.5:
        return "Send a reminder now"
    if p_late >= 0.3:
        return "Remind on the due date"
    return "No action needed"


def history_note(r: pd.Series) -> str:
    n = int(r["prior_paid"])
    if n == 0:
        return "New client: no paid invoices yet."
    late_n = int(round(r["prior_late_share"] * n))
    return (
        f"Paid {late_n} of {n} past invoices late, "
        f"{r['prior_mean_days']:.0f} days to pay on average."
    )


def score(f: pd.DataFrame, X: pd.DataFrame, as_of: pd.Timestamp, seed: int = 0) -> dict:
    """f, X: full feature frame and matrix. Uses only invoices paid before `as_of` to train."""
    tr = f.index[f["paid"] < as_of]
    open_ = f.index[(f["issued"] < as_of) & ~(f["paid"] < as_of)]
    if len(tr) < 20:
        raise ValueError("Need at least 20 paid invoices before the as-of date.")
    if len(open_) == 0:
        raise ValueError("No open invoices on that date.")
    Xtr, ytr = model.recent(X.loc[tr], f.loc[tr, "late"], f.loc[tr, "issued"])
    fc = model.Forecaster(seed).fit(Xtr, ytr.astype(int), f.loc[Xtr.index, "days_to_pay"])
    res = fc.predict(X.loc[open_])
    q = res["quantiles"]
    rng = np.random.default_rng(seed)
    week_edges = [as_of + pd.Timedelta(days=7 * w) for w in range(WEEKS + 1)]
    sims = np.zeros((DRAWS, WEEKS))
    rows = []
    for i, idx in enumerate(open_):
        r = f.loc[idx]
        age = (as_of - r["issued"]).days
        terms = (r["due"] - r["issued"]).days
        curve = q[i]
        s_age = 1 - np.interp(age, curve, model.LEVELS, left=0.0, right=1.0)
        if age > terms:
            status, p_late = "overdue", 1.0
        else:
            s_terms = 1 - np.interp(terms, curve, model.LEVELS, left=0.0, right=1.0)
            status = "open"
            p_late = float(np.clip(s_terms / s_age, 0, 1)) if s_age > 0.02 else 0.5
        lo, mid, hi = (model.conditional_quantile(curve, age, lv) for lv in (0.1, 0.5, 0.9))
        # Monte Carlo pay dates from the conditional distribution, for the cash band
        u = 1 - max(s_age, 0.02) * (1 - rng.uniform(size=DRAWS))
        draws = np.maximum(age, np.interp(u, model.LEVELS, curve, left=curve[0], right=curve[-1]))
        pay_dates = r["issued"] + pd.to_timedelta(np.round(draws), unit="D")
        wk = np.searchsorted(np.array(week_edges[1:], dtype="datetime64[ns]"), pay_dates.values, side="right")
        for w in range(WEEKS):
            sims[:, w] += r["amount"] * (wk == w)
        actual = r["paid"]
        rows.append(
            {
                "invoice_id": r["invoice_id"],
                "client": r["client"],
                "issued": str(r["issued"].date()),
                "due": str(r["due"].date()),
                "amount": round(float(r["amount"]), 2),
                "age_days": int(age),
                "status": status,
                "p_late": round(p_late, 3),
                "pay_lo": str((r["issued"] + pd.Timedelta(days=round(lo))).date()),
                "pay_mid": str((r["issued"] + pd.Timedelta(days=round(mid))).date()),
                "pay_hi": str((r["issued"] + pd.Timedelta(days=round(hi))).date()),
                "action": action(status, p_late),
                "history": history_note(r),
                "actual_paid": None if pd.isna(actual) else str(actual.date()),
            }
        )
    rows.sort(key=lambda x: (x["status"] != "overdue", -x["p_late"], -x["amount"]))
    weeks = []
    for w in range(WEEKS):
        a, b = week_edges[w], week_edges[w + 1]
        paid_in = f.loc[open_][(f.loc[open_, "paid"] >= a) & (f.loc[open_, "paid"] < b)]
        weeks.append(
            {
                "start": str(a.date()),
                "expected": round(float(sims[:, w].mean()), 2),
                "lo": round(float(np.percentile(sims[:, w], 10)), 2),
                "hi": round(float(np.percentile(sims[:, w], 90)), 2),
                "actual": round(float(paid_in["amount"].sum()), 2) if f.loc[open_, "paid"].notna().any() else None,
            }
        )
    return {
        "as_of": str(as_of.date()),
        "train_rows": int(len(Xtr)),
        "open_count": len(rows),
        "open_amount": round(float(f.loc[open_, "amount"].sum()), 2),
        "invoices": rows,
        "weeks": weeks,
    }
