#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stem detection and diameter from a breast-height cross-section.

Reproduces notebooks/project/05_stems_from_below.py. Scored over the 30 by 30 m box
the TLS and MLS actually cover, because 28 per cent of the plot has no ground-based
data and scoring over the circle counts undelivered data as failure.
"""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import numpy as np
import _common as C
from novatrees.evaluate import match_positions
from novatrees.pipeline import SeedParams, detect_seeds
from novatrees.stems import StemParams, detect_stems
from scipy.optimize import linear_sum_assignment

dtm, _ = C.terrain()
td, cur = C.field_stems(), C.current_dbh()

for name, path, zoff in (("TLS", C.TLS, C.TLS_CONST), ("MLS", C.MLS, 0.0)):
    B = C.height_band(path, dtm, zoff=zoff)
    print(f"\n{name}: {len(B):,} points in the band after a 1 cm voxel")
    st = detect_stems(B, StemParams())
    S = np.column_stack([st["x"], st["y"], st["dbh"]])
    old = detect_seeds(B, SeedParams())
    for lab, Sx in (("Taubin, loose gates", old), ("RANSAC + gates", S)):
        for reflab, RX, RY, RD in (("2011 survey", td.XCENT.to_numpy(), td.YCENT.to_numpy(), td.dbh.to_numpy()),
                                   ("current list", cur.X.to_numpy(), cur.Y.to_numpy(), cur.DBH.to_numpy())):
            keep = C.in_box(RX, RY)
            R = np.column_stack([RX[keep], RY[keep]]); Dref = RD[keep]
            m = match_positions(Sx, R, tol=2.0)
            cost = np.linalg.norm(Sx[:, None, :2] - R[None, :, :], axis=2)
            i, j = linear_sum_assignment(cost); ok = cost[i, j] <= 2.0
            est, ref = Sx[i[ok], 2] * 100, Dref[j[ok]]
            err = est - ref
            print(f"  {lab:<22} vs {reflab:<13} F1 {m['f1']:.3f} "
                  f"(recall {m['recall']:.3f}, precision {m['precision']:.3f})  "
                  f"DBH n={ok.sum():>3} bias {err.mean():+6.2f} cm RMSE {np.sqrt((err**2).mean()):5.2f} cm "
                  f"r {np.corrcoef(est, ref)[0,1]:+.3f}")
print(f"\nmedian DBH: 2011 survey {td.dbh.median():.1f} cm, current list {cur.DBH.median():.1f} cm, "
      f"growth {cur.DBH.median()-td.dbh.median():+.1f} cm in fifteen years")
