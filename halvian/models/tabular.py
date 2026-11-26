"""A small wrapper around scikit-learn models with built-in explanations.

Two algorithms, same interface:

* ``logistic``: logistic regression on standardized numbers and one-hot categories.
  Its reasons are exact: each feature's contribution to the log-odds relative to a
  typical training patient, and the contributions add up to the prediction.
* ``boosting``: HistGradientBoosting. Its reasons come from occlusion (set one feature to
  its typical value and see how much the estimate moves).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


@dataclass
class TabularModel:
    kind: str
    numeric: list[str]
    categorical: list[str]
    pipeline: Pipeline | None = None
    reference: dict = field(default_factory=dict)  # typical value per feature
    ref_vector: np.ndarray | None = None  # mean transformed row (logistic)
    feature_map: list[str] = field(default_factory=list)  # transformed column -> feature

    @property
    def features(self) -> list[str]:
        return self.numeric + self.categorical

    def _frame(self, df: pd.DataFrame) -> pd.DataFrame:
        X = df[self.features].copy()
        for c in self.categorical:
            X[c] = X[c].astype(str)
        for c in self.numeric:
            X[c] = X[c].astype(float)
        return X

    def fit(self, df: pd.DataFrame, y: np.ndarray, seed: int = 0) -> TabularModel:
        X = self._frame(df)
        if self.kind == "logistic":
            prep = ColumnTransformer([
                ("num", StandardScaler(), self.numeric),
                ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), self.categorical),
            ])
            clf = LogisticRegression(C=1.0, max_iter=3000)
        else:
            prep = ColumnTransformer([
                ("num", "passthrough", self.numeric),
                ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), self.categorical),
            ])
            n_num = len(self.numeric)
            cat_mask = [False] * n_num + [True] * len(self.categorical)
            clf = HistGradientBoostingClassifier(
                max_iter=300, learning_rate=0.06, max_leaf_nodes=31, l2_regularization=1.0,
                categorical_features=cat_mask, early_stopping=True, validation_fraction=0.1,
                random_state=seed,
            )
        self.pipeline = Pipeline([("prep", prep), ("clf", clf)])
        self.pipeline.fit(X, np.asarray(y, dtype=int))
        self.reference = {c: float(X[c].median()) for c in self.numeric}
        self.reference.update({c: X[c].mode().iloc[0] for c in self.categorical})
        if self.kind == "logistic":
            Z = self.pipeline.named_steps["prep"].transform(X)
            self.ref_vector = Z.mean(axis=0)
            names = self.pipeline.named_steps["prep"].get_feature_names_out()
            self.feature_map = [self._owner(n) for n in names]
        return self

    def _owner(self, transformed_name: str) -> str:
        part, rest = transformed_name.split("__", 1)
        if part == "num":
            return rest
        for c in sorted(self.categorical, key=len, reverse=True):
            if rest.startswith(c + "_"):
                return c
        return rest

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        return self.pipeline.predict_proba(self._frame(df))[:, 1]

    def contributions(self, df: pd.DataFrame) -> pd.DataFrame:
        """Log-odds contribution of each feature for each row, relative to typical."""
        X = self._frame(df)
        if self.kind == "logistic":
            Z = self.pipeline.named_steps["prep"].transform(X)
            coef = self.pipeline.named_steps["clf"].coef_[0]
            contrib = (Z - self.ref_vector) * coef
            out = pd.DataFrame(contrib, columns=self.feature_map, index=df.index)
            return out.T.groupby(level=0).sum().T[self.features]
        base = _logit(self.predict_proba(df))
        out = {}
        for c in self.features:
            Xr = X.copy()
            Xr[c] = self.reference[c]
            out[c] = base - _logit(self.pipeline.predict_proba(Xr)[:, 1])
        return pd.DataFrame(out, index=df.index)

    def global_importance(self, df: pd.DataFrame, y: np.ndarray, seed: int = 0,
                          max_rows: int = 6000) -> pd.DataFrame:
        """Mean absolute contribution and permutation importance (AUC drop) per feature."""
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(df), size=min(max_rows, len(df)), replace=False)
        sub, ysub = df.iloc[idx], np.asarray(y)[idx]
        mean_abs = self.contributions(sub).abs().mean()
        perm = permutation_importance(self.pipeline, self._frame(sub), ysub, scoring="roc_auc",
                                      n_repeats=3, random_state=seed)
        imp = pd.DataFrame({"feature": self.features,
                            "mean_abs_contribution": mean_abs.reindex(self.features).to_numpy(),
                            "permutation_auc_drop": perm.importances_mean})
        return imp.sort_values("permutation_auc_drop", ascending=False).reset_index(drop=True)
