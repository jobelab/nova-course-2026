#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Crown level indices, paired between acquisitions, and species separation.

Reproduces notebooks/project/04_crowns_and_species.py. AUC is used for the species
comparison because it is scale free, so indices with different ranges compare
directly. "Band" restricts to the middle two DBH quartiles as a size control.
"""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import numpy as np, pandas as pd, laspy
import _common as C
from novatrees import spectral as sp
from novatrees.chm_watershed import ChmParams, chm_segment
from novatrees.terrain import normalize_against
from scipy.optimize import linear_sum_assignment
from scipy import stats

dtm, _ = C.terrain()
td = C.field_stems()
R = td[["XCENT", "YCENT"]].to_numpy(float)


def crowns(name):
    f = laspy.read(str(C.DRONE / f"{name}_plot167_20m.las"))
    xyz = np.column_stack([f.x, f.y, f.z])
    H = np.column_stack([xyz[:, 0], xyz[:, 1], normalize_against(xyz, dtm)])
    raw = {k: np.asarray(getattr(f, k), float) for k in ("red", "green", "blue")}
    if name.endswith("MS"):
        c = sp.resolve_ms(raw); c["nir"] = np.asarray(f.nir, float)
        idx = {"NDVI": sp.normalised_difference(c["nir"], c["red"]),
               "NDRE": sp.normalised_difference(c["nir"], c["red_edge"]),
               "GNDVI": sp.normalised_difference(c["nir"], c["green"]),
               "G": sp.chromatic_coordinates(sp.colour_array(c, sp.MS_VISIBLE))[0][:, 0]}
    else:
        cc, _ = sp.chromatic_coordinates(sp.colour_array(raw, sp.RGB))
        idx = {"GCC": cc[:, 1], "RCC": cc[:, 0], "BCC": cc[:, 2], "G": cc[:, 1]}
    r = chm_segment(H, ChmParams(pixel_size=0.20, min_distance=1.5,
                                 min_tree_height=5.0, min_crown_area=3.0))
    lab, tops = r["labels"], r["tops"]
    area = np.bincount(r["labels2d"].ravel())[1:] * r["pixel_size"] ** 2
    rows = []
    for k in range(len(tops)):
        m = lab == k
        if m.sum() < 30:
            continue
        row = dict(cloud=name, x=tops[k, 0], y=tops[k, 1], n=int(m.sum()),
                   h95=float(np.percentile(H[m, 2], 95)),
                   area=float(area[k]) if k < len(area) else np.nan)
        for nm, v in idx.items():
            row[nm] = float(np.nanmedian(v[m]))
        rows.append(row)
    T = pd.DataFrame(rows)
    cost = np.linalg.norm(T[["x", "y"]].to_numpy()[:, None, :] - R[None, :, :], axis=2)
    i, j = linear_sum_assignment(cost); ok = cost[i, j] <= 2.0
    T["dbh"] = np.nan; T["species"] = 0
    T.loc[i[ok], "dbh"] = td.dbh.to_numpy()[j[ok]]
    T.loc[i[ok], "species"] = td.SPECIES.to_numpy()[j[ok]]
    return T


TB = {n: crowns(n) for n in C.DRONE_CLOUDS}
print(f"{'cloud':<14}{'crowns':>7}{'median area':>13}{'median h95':>12}")
for n, T in TB.items():
    print(f"{n:<14}{len(T):>7}{T.area.median():>11.1f} m2{T.h95.median():>10.2f} m")


def pair(a, b, tol=1.5):
    A, B = TB[a][["x", "y"]].to_numpy(), TB[b][["x", "y"]].to_numpy()
    c = np.linalg.norm(A[:, None, :] - B[None, :, :], axis=2)
    i, j = linear_sum_assignment(c); k = c[i, j] <= tol
    return TB[a].iloc[i[k]].reset_index(drop=True), TB[b].iloc[j[k]].reset_index(drop=True)


print("\npaired crowns, nadir minus oblique (median [IQR])")
for a, b in (("Nadir_RGB", "Oblique_RGB"), ("Nadir_MS", "Oblique_MS")):
    x, y = pair(a, b)
    for col, unit in (("G", ""), ("h95", " m"), ("area", " m2")):
        d = x[col].to_numpy() - y[col].to_numpy()
        print(f"  {a:<12} {col:<5} {np.median(d):+8.4f}{unit}  "
              f"[{np.percentile(d,25):+.4f}, {np.percentile(d,75):+.4f}]  n={len(x)}")

print("\nspecies separation, AUC (spruce above pine)")
print(f"{'cloud':<14}{'index':<8}{'AUC':>8}{'n':>5}{'AUC band':>10}{'n':>5}")
for n, T in TB.items():
    J = T[T.species > 0]
    lo, hi = J.dbh.quantile(.25), J.dbh.quantile(.75)
    bd = J[(J.dbh >= lo) & (J.dbh <= hi)]
    cols = ["GCC", "RCC", "BCC"] if not n.endswith("MS") else ["NDVI", "NDRE", "GNDVI", "G"]
    for col in cols:
        p_, s_ = J[J.species == 1][col], J[J.species == 2][col]
        bp, bs = bd[bd.species == 1][col], bd[bd.species == 2][col]
        auc = stats.mannwhitneyu(s_, p_).statistic / (len(s_) * len(p_))
        aucb = stats.mannwhitneyu(bs, bp).statistic / (len(bs) * len(bp))
        print(f"{n:<14}{col:<8}{auc:>8.3f}{len(J):>5}{aucb:>10.3f}{len(bd):>5}")

J = TB["Nadir_RGB"]
J = J[J.species > 0]
print(f"\ncrown area vs DBH r = {J.area.corr(J.dbh):+.3f}, h95 vs DBH r = {J.h95.corr(J.dbh):+.3f}")
print(f"GCC vs DBH r = {J.GCC.corr(J.dbh):+.3f}, GCC vs h95 r = {J.GCC.corr(J.h95):+.3f}")
