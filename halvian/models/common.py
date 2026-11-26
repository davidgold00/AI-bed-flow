"""Shared model utilities: leakage-safe temporal splits, metrics and calibration bins.

Temporal design (REVIEW finding 2):

* **Selection**: fit on rows scored Jan to Aug whose outcome was known before Sep 1,
  score September rows whose outcome was known before Oct 1, pick the algorithm.
* **Final model**: refit on rows scored Jan to Sep whose outcome was known before Oct 1.
* **Test**: rows scored Oct to Dec. These labels are never used for fitting or choice.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from halvian import config as C
from halvian.data.cohort import minutes_from_start

MIN_SUPPORT = 30  # fewer positives or negatives than this reads "insufficient data"


def month_start(month: int, year: int = 2025) -> float:
    if month == 13:
        return minutes_from_start(date(year + 1, 1, 1))
    return minutes_from_start(date(year, month, 1))


def split_labels(score_min: pd.Series, outcome_min: pd.Series) -> pd.Series:
    """'fit', 'valid', 'test', or '' (unused) for each row.

    score_min: when the prediction is made. outcome_min: when the label became known.
    'fit' rows feed selection; 'fit' + 'valid' rows (outcome known before Oct 1) feed the
    final refit; 'test' rows are evaluation only.
    """
    sep1, oct1, end = month_start(C.VALID_MONTH), month_start(C.TEST_MONTHS[0]), month_start(13)
    jan1 = month_start(1)
    out = pd.Series("", index=score_min.index, dtype=object)
    out[(score_min >= jan1) & (score_min < sep1) & (outcome_min < sep1)] = "fit"
    out[(score_min >= sep1) & (score_min < oct1) & (outcome_min < oct1)] = "valid"
    out[(score_min >= oct1) & (score_min < end)] = "test"
    return out


def binary_metrics(y: np.ndarray, p: np.ndarray, flag: np.ndarray | None = None) -> dict:
    """AUC, average precision, Brier and confusion counts with explicit denominators."""
    y = np.asarray(y, dtype=bool)
    p = np.asarray(p, dtype=float)
    pos, neg = int(y.sum()), int((~y).sum())
    out: dict = {"n": int(len(y)), "positives": pos, "negatives": neg,
                 "prevalence": float(y.mean()) if len(y) else np.nan}
    enough = pos >= MIN_SUPPORT and neg >= MIN_SUPPORT
    out["auc"] = float(roc_auc_score(y, p)) if enough else None
    out["average_precision"] = float(average_precision_score(y, p)) if enough else None
    out["brier"] = float(brier_score_loss(y, p)) if len(y) else None
    out["mean_predicted"] = float(p.mean()) if len(y) else None
    out["calibration_gap_pts"] = float(100 * (p.mean() - y.mean())) if len(y) else None
    if flag is not None:
        f = np.asarray(flag, dtype=bool)
        tp, fp = int((f & y).sum()), int((f & ~y).sum())
        fn, tn = int((~f & y).sum()), int((~f & ~y).sum())
        out.update({
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "flags": int(f.sum()),
            "flag_rate": float(f.mean()) if len(f) else None,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / pos if pos else None,
            "fnr": fn / pos if pos >= MIN_SUPPORT else None,
            "fpr": fp / neg if neg else None,
        })
    return out


def calibration_bins(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> list[dict]:
    """Reliability bins (equal width) with counts, for the calibration curve."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    edges = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        m = idx == b
        if m.sum():
            rows.append({"bin_low": float(edges[b]), "bin_high": float(edges[b + 1]),
                         "mean_predicted": float(p[m].mean()), "observed": float(y[m].mean()),
                         "count": int(m.sum())})
    return rows


def curve_points(y: np.ndarray, p: np.ndarray, kind: str, n: int = 60) -> list[dict]:
    """Downsampled ROC or precision-recall curve for plotting."""
    from sklearn.metrics import precision_recall_curve, roc_curve

    if kind == "roc":
        a, b, _ = roc_curve(y, p)
        pts = list(zip(a, b, strict=True))
        keys = ("fpr", "tpr")
    else:
        prec, rec, _ = precision_recall_curve(y, p)
        pts = list(zip(rec, prec, strict=True))
        keys = ("recall", "precision")
    step = max(1, len(pts) // n)
    sel = pts[::step] + [pts[-1]]
    return [{keys[0]: float(u), keys[1]: float(v)} for u, v in sel]
