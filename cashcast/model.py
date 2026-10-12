"""TabPFN v2 wrappers: late-payment probability and a days-to-pay distribution."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)

MAX_TRAIN = 1000  # TabPFN's default CPU limit; the most recent paid invoices are kept
LEVELS = np.round(np.arange(0.02, 0.99, 0.02), 2)  # 49 quantiles describe the distribution


def _device() -> str:
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # pragma: no cover
        return "cpu"


def recent(train_X: pd.DataFrame, train_y: pd.Series, order: pd.Series):
    keep = order.sort_values().index[-MAX_TRAIN:]
    return train_X.loc[keep], train_y.loc[keep]


class Forecaster:
    """Fit on paid invoices, predict for any invoices."""

    def __init__(self, seed: int = 0):
        from tabpfn import TabPFNClassifier, TabPFNRegressor
        from tabpfn.constants import ModelVersion

        dev = _device()
        self.clf = TabPFNClassifier.create_default_for_version(
            ModelVersion.V2, device=dev, random_state=seed
        )
        self.reg = TabPFNRegressor.create_default_for_version(
            ModelVersion.V2, device=dev, random_state=seed
        )

    def fit(self, X: pd.DataFrame, late: pd.Series, days: pd.Series) -> "Forecaster":
        self.clf.fit(X.to_numpy(), late.astype(int).to_numpy())
        self.reg.fit(X.to_numpy(), days.to_numpy(dtype=float))
        return self

    def predict(self, X: pd.DataFrame) -> dict:
        p_late = self.clf.predict_proba(X.to_numpy())[:, 1]
        q = np.asarray(
            self.reg.predict(X.to_numpy(), output_type="quantiles", quantiles=list(LEVELS))
        ).T  # rows x levels
        q = np.maximum.accumulate(np.clip(q, 0, None), axis=1)
        return {"p_late": p_late, "quantiles": q}


def quantile(q: np.ndarray, level: float) -> np.ndarray:
    return np.array([np.interp(level, LEVELS, row) for row in q])


def survival(q: np.ndarray, t: float) -> np.ndarray:
    """P(days_to_pay > t) for each row, read off the quantile curve."""
    return np.array([1 - np.interp(t, row, LEVELS, left=0.0, right=1.0) for row in q])


def conditional_quantile(row: np.ndarray, age: float, level: float) -> float:
    """Quantile of days_to_pay given the invoice is still unpaid after `age` days."""
    s_age = 1 - np.interp(age, row, LEVELS, left=0.0, right=1.0)
    if s_age <= 0.02:
        return float(max(age + 1, row[-1]))
    target_cdf = 1 - s_age * (1 - level)
    return float(max(age, np.interp(target_cdf, LEVELS, row, left=row[0], right=row[-1])))
