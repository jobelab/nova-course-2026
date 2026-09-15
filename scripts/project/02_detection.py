#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Treetop detection on a canopy height model, scored against the field stems.

Reproduces notebooks/project/03_detection.py. Matching is one-to-one at 2.0 m,
under half the 4.12 m mean stem spacing: independent nearest-neighbour matching at
a 3 m tolerance let 49 detections claim a recall of 0.865 against 74 stems.
"""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import numpy as np
import _common as C
from novatrees.chm_watershed import ChmParams, chm_segment
from novatrees.evaluate import match_positions
from scipy.optimize import linear_sum_assignment

dtm, _ = C.terrain()
td = C.field_stems()
R = td[["XCENT", "YCENT"]].to_numpy(float)
dbh = td.dbh.to_numpy()
sp = td.SPECIES.to_numpy(int)
print(f"reference: {len(R)} stems, mean spacing {np.sqrt(np.pi*C.PLOT_R**2/len(R)):.2f} m\n")

H = {n: C.normalised(C.DRONE / f"{n}_plot167_20m.las", dtm, target=2_000_000)
     for n in C.DRONE_CLOUDS}
H["ALS"] = C.normalised(C.ALS, dtm, target=2_000_000)
H["MLS"] = C.normalised(C.MLS, dtm, target=2_000_000)
H["TLS"] = C.normalised(C.TLS, dtm, zoff=C.TLS_CONST, target=2_000_000)

SEPS = (1.5, 2.0, 2.5, 3.0, 3.5)
print("F1 against minimum treetop separation")
print(f"{'cloud':<13}" + "".join(f"{s:>9.1f}" for s in SEPS))
best = {}
for n, P in H.items():
    row = []
    for s in SEPS:
        r = chm_segment(P, ChmParams(pixel_size=0.20, min_distance=s,
                                     min_tree_height=5.0, min_crown_area=3.0))
        m = match_positions(r["tops"], R, tol=2.0)
        row.append(m["f1"])
        if n not in best or m["f1"] > best[n][0]:
            best[n] = (m["f1"], s, r["tops"], m)
    print(f"{n:<13}" + "".join(f"{v:>9.3f}" for v in row))

print(f"\n{'cloud':<13}{'sep':>5}{'tops':>6}{'recall':>8}{'prec':>7}{'F1':>7}")
for n, (f1, s, tops, m) in best.items():
    print(f"{n:<13}{s:>5.1f}{len(tops):>6}{m['recall']:>8.3f}{m['precision']:>7.3f}{f1:>7.3f}")

qs = np.quantile(dbh, [0, .25, .5, .75, 1.0])
print(f"\ndetection rate by DBH quartile (cm) at 1.5 m separation")
print(f"{'cloud':<13}" + "".join(f"{f'{qs[i]:.0f}-{qs[i+1]:.0f}':>10}" for i in range(4))
      + f"{'pine':>8}{'spruce':>8}")
for n, P in H.items():
    r = chm_segment(P, ChmParams(pixel_size=0.20, min_distance=1.5,
                                 min_tree_height=5.0, min_crown_area=3.0))
    cost = np.linalg.norm(r["tops"][:, None, :2] - R[None, :, :], axis=2)
    i, j = linear_sum_assignment(cost)
    ok = cost[i, j] <= 2.0
    hit = np.zeros(len(R), bool); hit[j[ok]] = True
    cls = np.clip(np.searchsorted(qs[1:-1], dbh, side="right"), 0, 3)
    print(f"{n:<13}" + "".join(f"{100*hit[cls==k].mean():>9.0f}%" for k in range(4))
          + f"{100*hit[sp==1].mean():>7.0f}%{100*hit[sp==2].mean():>7.0f}%")
