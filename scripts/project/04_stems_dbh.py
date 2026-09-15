#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stem detection and diameter, scored over the area the scanners actually cover.

Computation lives in analysis.stems(). The 30 by 30 m box is 900 m2 against a 1256 m2
plot, so 28 per cent of the plot has no ground-based data and scoring over the circle
counts undelivered data as failure.
"""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import numpy as np
import _common as C, analysis as A
from novatrees.evaluate import match_positions
from scipy.optimize import linear_sum_assignment

S = A.stems()
td, cur = C.field_stems(), C.current_dbh()
REFS = (("2011 survey", td.XCENT.to_numpy(), td.YCENT.to_numpy(), td.dbh.to_numpy()),
        ("current list", cur.X.to_numpy(), cur.Y.to_numpy(), cur.DBH.to_numpy()))
FITS = {"taubin": "Taubin, loose gates", "ransac": "RANSAC + gates"}

for cloud in ("TLS", "MLS"):
    print(f"\n{cloud}")
    for fit, label in FITS.items():
        q = S[(S.cloud == cloud) & (S.fit == fit)]
        P = q[["x", "y", "dbh"]].to_numpy()
        for reflab, RX, RY, RD in REFS:
            keep = C.in_box(RX, RY)
            R = np.column_stack([RX[keep], RY[keep]]); Dref = RD[keep]
            m = match_positions(P[:, :2], R, tol=2.0)
            cost = np.linalg.norm(P[:, None, :2] - R[None, :, :], axis=2)
            i, j = linear_sum_assignment(cost); ok = cost[i, j] <= 2.0
            est, ref = P[i[ok], 2], Dref[j[ok]]
            err = est - ref
            print(f"  {label:<22} vs {reflab:<13} F1 {m['f1']:.3f} "
                  f"(recall {m['recall']:.3f}, precision {m['precision']:.3f})  "
                  f"DBH n={int(ok.sum()):>3} bias {err.mean():+6.2f} cm "
                  f"RMSE {np.sqrt((err**2).mean()):5.2f} cm r {np.corrcoef(est, ref)[0,1]:+.3f}")
    r = S[(S.cloud == cloud) & (S.fit == "ransac")]
    print(f"  fit quality: median sigma {r.sigma.median()*1000:.1f} mm, median arc {r.arc.median():.2f}")

print(f"\nmedian DBH: 2011 {td.dbh.median():.1f} cm, current {cur.DBH.median():.1f} cm, "
      f"growth {cur.DBH.median()-td.dbh.median():+.1f} cm in fifteen years")
