#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Crown indices paired between acquisitions, and species separation by AUC.

Computation lives in analysis.crowns(). AUC is scale free, so indices with different
ranges compare directly; "band" is the middle two DBH quartiles, a size control.
"""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import numpy as np
import analysis as A
from scipy import stats
from scipy.optimize import linear_sum_assignment

CT = A.crowns()
print(f"{'cloud':<14}{'crowns':>7}{'median area':>13}{'median h95':>12}")
for n, T in CT.groupby("cloud", sort=False):
    print(f"{n:<14}{len(T):>7}{T.area.median():>11.1f} m2{T.h95.median():>10.2f} m")

def pair(a, b, tol=1.5):
    A_, B_ = CT[CT.cloud == a], CT[CT.cloud == b]
    x, y = A_[["x", "y"]].to_numpy(), B_[["x", "y"]].to_numpy()
    c = np.linalg.norm(x[:, None, :] - y[None, :, :], axis=2)
    i, j = linear_sum_assignment(c); k = c[i, j] <= tol
    return A_.iloc[i[k]].reset_index(drop=True), B_.iloc[j[k]].reset_index(drop=True)

print("\npaired crowns, nadir minus oblique (median [IQR])")
for a, b in (("Nadir_RGB", "Oblique_RGB"), ("Nadir_MS", "Oblique_MS")):
    x, y = pair(a, b)
    for col, unit in (("G", ""), ("h95", " m"), ("area", " m2")):
        d = x[col].to_numpy() - y[col].to_numpy()
        print(f"  {a:<12} {col:<5} {np.median(d):+8.4f}{unit}"
              f"  [{np.percentile(d,25):+.4f}, {np.percentile(d,75):+.4f}]  n={len(x)}")

print("\nspecies separation, AUC (spruce above pine)")
print(f"{'cloud':<14}{'index':<8}{'AUC':>8}{'n':>5}{'AUC band':>10}{'n':>5}")
for n, T in CT.groupby("cloud", sort=False):
    J = T[T.species > 0]
    lo, hi = J.dbh.quantile(.25), J.dbh.quantile(.75)
    bd = J[(J.dbh >= lo) & (J.dbh <= hi)]
    cols = ["NDVI", "NDRE", "GNDVI", "G"] if n.endswith("MS") else ["GCC", "RCC", "BCC"]
    for col in cols:
        p_, s_ = J[J.species == 1][col], J[J.species == 2][col]
        bp, bs = bd[bd.species == 1][col], bd[bd.species == 2][col]
        auc = stats.mannwhitneyu(s_, p_).statistic / (len(s_) * len(p_))
        aucb = stats.mannwhitneyu(bs, bp).statistic / (len(bs) * len(bp))
        print(f"{n:<14}{col:<8}{auc:>8.3f}{len(J):>5}{aucb:>10.3f}{len(bd):>5}")

J = CT[(CT.cloud == "Nadir_RGB") & (CT.species > 0)]
print(f"\ncrown area vs DBH r {J.area.corr(J.dbh):+.3f},  h95 vs DBH r {J.h95.corr(J.dbh):+.3f}")
print(f"GCC vs DBH r {J.GCC.corr(J.dbh):+.3f},  GCC vs h95 r {J.GCC.corr(J.h95):+.3f}")
