# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Fitting a volume model on matched trees, and applying it to the ALS coverage.

The Day 4 objective stopped at a table: stem volume from the ground beside metrics
from the air. This is the step after it. Fit `V = f(ALS metrics)` on the trees where
both exist, then apply it to every ALS tree, including the ones no ground sensor ever
reached. That is the whole point of the airborne data.

**Twelve trees.** That is the entire training set on this plot, and it is small enough
that the honest reporting matters more than the fit. Everything here is arranged
around that:

- **Leave-one-out cross-validation, always.** With n = 12 an in-sample R^2 is
  meaningless: a four-parameter model will fit twelve points well no matter what.
  `loocv` refits the model n times, each without one tree, and scores the prediction
  for the tree left out.
- **Scored against the null model.** A model that cannot beat "predict the mean for
  every tree" has learned nothing, and with n = 12 that happens easily. `compare` puts
  the null in the table beside everything else.
- **Bias correction on the back-transform.** Fitting in log space and exponentiating
  the prediction returns the *median*, not the mean, and so underestimates every total
  it is summed into. The Baskerville correction factor is applied and reported, never
  applied silently.

**The allometric form is the reason for log space.** Stem volume against tree size is
a power law, not a line: V = a H^b A^c. Taking logs makes it linear and, more
usefully, makes the error multiplicative, which is what tree measurements actually
have. A big tree is wrong by a percentage, not by a fixed number of cubic metres.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "ModelSpec",
    "FitResult",
    "DEFAULT_SPECS",
    "fit_model",
    "loocv",
    "compare",
    "predict",
    "plot_total",
]


@dataclass(frozen=True)
class ModelSpec:
    """One candidate model: a name, its predictors, and whether it is fitted in logs."""

    name: str
    predictors: tuple[str, ...]
    log: bool = True

    @property
    def n_params(self) -> int:
        return len(self.predictors) + 1  # plus the intercept


# The candidates worth trying on airborne metrics, smallest first. Order matters:
# with twelve trees, every parameter has to earn its place, so read the table from
# the top and stop as soon as the cross-validated error stops improving.
DEFAULT_SPECS = (
    ModelSpec("null (mean volume)", (), log=False),
    ModelSpec("height only", ("h_max_air",)),
    ModelSpec("crown area only", ("crown_area_m2_air",)),
    ModelSpec("crown volume only", ("crown_volume_m3_air",)),
    ModelSpec("height + crown area", ("h_max_air", "crown_area_m2_air")),
    ModelSpec("height + crown volume", ("h_max_air", "crown_volume_m3_air")),
    ModelSpec("height + crown area + p50",
              ("h_max_air", "crown_area_m2_air", "h_p50_air")),
)


@dataclass
class FitResult:
    spec: ModelSpec
    coef: np.ndarray  # intercept first
    n: int
    r2: float  # in-sample, and not to be trusted at this n
    rmse: float  # in-sample, back-transformed to m3
    bias: float
    correction: float  # Baskerville factor, 1.0 when not fitted in logs
    sigma_log: float
    residuals: np.ndarray
    fitted: np.ndarray
    stats: dict = field(default_factory=dict)

    def equation(self, digits: int = 3) -> str:
        """The fitted model as it would be written in a paper."""
        if not self.spec.predictors:
            return f"V = {np.exp(self.coef[0]) if self.spec.log else self.coef[0]:.{digits}f}"
        if self.spec.log:
            # The scale coefficient is tiny whenever an exponent is large, because
            # h^4 is a big number, so a fixed number of decimals prints it as zero.
            a = float(np.exp(self.coef[0])) * self.correction
            terms = " ".join(
                f"{p.replace('_air', '')}^{b:.{digits}f}"
                for p, b in zip(self.spec.predictors, self.coef[1:])
            )
            return f"V = {a:.{digits}g} {terms}"
        terms = " ".join(
            f"{b:+.{digits}f}*{p.replace('_air', '')}"
            for p, b in zip(self.spec.predictors, self.coef[1:])
        )
        return f"V = {self.coef[0]:.{digits}f} {terms}"


def _design(df, spec: ModelSpec) -> np.ndarray:
    n = len(df)
    if not spec.predictors:
        return np.ones((n, 1))
    X = np.column_stack([np.asarray(df[p], float) for p in spec.predictors])
    if spec.log:
        X = np.log(np.clip(X, 1e-9, None))
    return np.column_stack([np.ones(n), X])


def _clean(df, y: str, spec: ModelSpec):
    """Rows usable for this model: response and every predictor present and positive."""
    cols = [y, *spec.predictors]
    d = df[cols].replace([np.inf, -np.inf], np.nan).dropna()
    if spec.log:
        d = d[(d > 0).all(axis=1)]
    return df.loc[d.index]


def fit_model(df, y: str = "vol_model_relaxed_m3_ground",
              spec: ModelSpec = DEFAULT_SPECS[4]) -> FitResult:
    """Ordinary least squares, in log space when the spec says so.

    The Baskerville correction factor `exp(sigma^2 / 2)` is computed and stored, and
    `predict` applies it. Without it, a log-log model returns the conditional median
    and every plot total built from it is biased low, typically by a few per cent but
    by much more when the scatter is large.
    """
    d = _clean(df, y, spec)
    X = _design(d, spec)
    yv = np.asarray(d[y], float)
    target = np.log(yv) if spec.log else yv

    coef, *_ = np.linalg.lstsq(X, target, rcond=None)
    pred_t = X @ coef
    resid_t = target - pred_t
    dof = max(len(d) - X.shape[1], 1)
    sigma = float(np.sqrt(np.sum(resid_t**2) / dof))
    correction = float(np.exp(sigma**2 / 2)) if spec.log else 1.0

    fitted = np.exp(pred_t) * correction if spec.log else pred_t
    resid = yv - fitted
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((yv - yv.mean()) ** 2))
    return FitResult(
        spec=spec, coef=coef, n=int(len(d)),
        r2=1 - ss_res / ss_tot if ss_tot > 0 else float("nan"),
        rmse=float(np.sqrt(ss_res / len(d))),
        bias=float(resid.mean()),
        correction=correction, sigma_log=sigma,
        residuals=resid, fitted=fitted,
        stats={"y": y, "mean_observed": float(yv.mean())},
    )


def predict(fit: FitResult, df) -> np.ndarray:
    """Apply a fitted model to new trees. Returns NaN where a predictor is missing."""
    spec = fit.spec
    out = np.full(len(df), np.nan)
    if not spec.predictors:
        base = np.exp(fit.coef[0]) * fit.correction if spec.log else fit.coef[0]
        return np.full(len(df), float(base))
    cols = [df[p].to_numpy(dtype=float) for p in spec.predictors]
    ok = np.all([np.isfinite(c) & (c > 0 if spec.log else True) for c in cols], axis=0)
    if not ok.any():
        return out
    X = _design(df.loc[ok], spec)
    p = X @ fit.coef
    out[ok] = np.exp(p) * fit.correction if spec.log else p
    return out


def loocv(df, y: str = "vol_model_relaxed_m3_ground",
          spec: ModelSpec = DEFAULT_SPECS[4]) -> dict:
    """Leave-one-out cross-validation. The only error estimate worth quoting at n = 12.

    Refits the model n times, each time holding out one tree, and scores the held-out
    prediction. `r2` here is the cross-validated coefficient of determination, and
    **it can be negative**: that means the model predicts a held-out tree worse than
    the training mean would, which is a real and common outcome on twelve points.
    """
    d = _clean(df, y, spec)
    yv = np.asarray(d[y], float)
    n = len(d)
    if n < spec.n_params + 2:
        return {"n": n, "rmse": float("nan"), "bias": float("nan"),
                "r2": float("nan"), "predicted": np.full(n, np.nan),
                "why": f"needs at least {spec.n_params + 2} trees, has {n}"}

    pred = np.empty(n)
    for i in range(n):
        train = d.drop(d.index[i])
        f = fit_model(train, y, spec)
        pred[i] = predict(f, d.iloc[[i]])[0]

    err = yv - pred
    ss_tot = float(np.sum((yv - yv.mean()) ** 2))
    return {
        "n": n,
        "rmse": float(np.sqrt(np.mean(err**2))),
        "rmse_pct": float(100 * np.sqrt(np.mean(err**2)) / yv.mean()),
        "bias": float(err.mean()),
        "r2": float(1 - np.sum(err**2) / ss_tot) if ss_tot > 0 else float("nan"),
        "predicted": pred,
        "observed": yv,
        "why": "",
    }


def compare(df, y: str = "vol_model_relaxed_m3_ground", specs=DEFAULT_SPECS):
    """Every candidate model, scored in-sample and by leave-one-out, in one table.

    Read the cross-validated columns and ignore the in-sample ones except as a measure
    of how much optimism they carry. The gap between `R2` and `R2 cv` is that optimism
    made visible, and on twelve trees it is usually large.
    """
    import pandas as pd

    rows = []
    for spec in specs:
        try:
            f = fit_model(df, y, spec)
            cv = loocv(df, y, spec)
        except Exception as e:  # a degenerate predictor set should not stop the table
            rows.append({"model": spec.name, "note": f"failed: {type(e).__name__}"})
            continue
        rows.append({
            "model": spec.name,
            "params": spec.n_params,
            "n": f.n,
            "R2": round(f.r2, 3),
            "RMSE": round(f.rmse, 3),
            "R2 cv": round(cv["r2"], 3) if np.isfinite(cv["r2"]) else None,
            "RMSE cv": round(cv["rmse"], 3) if np.isfinite(cv["rmse"]) else None,
            "RMSE cv %": round(cv["rmse_pct"], 1) if np.isfinite(cv.get("rmse_pct", np.nan)) else None,
            "bias cv": round(cv["bias"], 4) if np.isfinite(cv["bias"]) else None,
            "correction": round(f.correction, 4),
            "equation": f.equation(),
            "note": cv["why"],
        })
    return pd.DataFrame(rows)


def plot_total(volumes: np.ndarray, area_ha: float, cv_rmse: float | None = None,
               n_boot: int = 2000, seed: int = 0) -> dict:
    """Sum predicted volumes to a plot total and a per-hectare figure.

    Two sources of uncertainty are reported separately, because they behave
    differently and quoting only one is how a confident wrong number gets published:

    - **sampling**, from bootstrapping the trees, which says how much the total moves
      if this plot had held a slightly different set of trees;
    - **model**, from the cross-validated error per tree. Summed over `n` trees it
      grows as `sqrt(n) * rmse` if the errors are independent, and as `n * rmse` if
      they are not. Both are given, and the truth is in between: a model fitted on
      twelve trees from one plot makes correlated errors.
    """
    v = np.asarray(volumes, float)
    v = v[np.isfinite(v)]
    n = len(v)
    total = float(v.sum())
    out = {
        "n_trees": n,
        "total_m3": total,
        "per_ha_m3": total / area_ha if area_ha > 0 else float("nan"),
        "stems_per_ha": n / area_ha if area_ha > 0 else float("nan"),
        "mean_tree_m3": float(v.mean()) if n else float("nan"),
    }
    if n > 2:
        rng = np.random.default_rng(seed)
        boots = np.array([rng.choice(v, n, replace=True).sum() for _ in range(n_boot)])
        lo, hi = np.percentile(boots, [2.5, 97.5])
        out["sampling_ci_m3"] = (float(lo), float(hi))
        out["sampling_ci_per_ha"] = (float(lo / area_ha), float(hi / area_ha))
    if cv_rmse is not None and np.isfinite(cv_rmse) and n:
        out["model_error_independent_m3"] = float(np.sqrt(n) * cv_rmse)
        out["model_error_correlated_m3"] = float(n * cv_rmse)
    return out
