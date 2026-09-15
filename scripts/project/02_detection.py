#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Treetop detection scored against the field stems.

Computation lives in analysis.detections(); this prints it. Matching is one-to-one at
2.0 m, under half the 4.12 m mean stem spacing.
"""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import numpy as np
import _common as C, analysis as A
from novatrees.evaluate import match_positions
from scipy.optimize import linear_sum_assignment

TOPS = A.detections()
field = C.field_stems()
REF = field[["XCENT", "YCENT"]].to_numpy(float)
dbh, spec = field.dbh.to_numpy(), field.SPECIES.to_numpy(int)
SEPS = sorted(TOPS.sep.unique())
ORDER = ["Nadir_RGB", "Oblique_RGB", "Nadir_MS", "Oblique_MS", "ALS", "MLS", "TLS"]
print(f"reference: {len(REF)} stems, mean spacing {np.sqrt(np.pi*C.PLOT_R**2/len(REF)):.2f} m\n")

def tops(c, s):
    return TOPS[(TOPS.cloud == c) & (np.isclose(TOPS.sep, s))][["x", "y"]].to_numpy()

print("F1 against minimum treetop separation")
print(f"{'cloud':<13}" + "".join(f"{s:>9.1f}" for s in SEPS))
best = {}
for c in ORDER:
    row = []
    for s in SEPS:
        m = match_positions(tops(c, s), REF, tol=2.0)
        row.append(m["f1"])
        if c not in best or m["f1"] > best[c][0]:
            best[c] = (m["f1"], s, m, len(tops(c, s)))
    print(f"{c:<13}" + "".join(f"{v:>9.3f}" for v in row))

print(f"\n{'cloud':<13}{'sep':>5}{'tops':>6}{'matched':>9}{'recall':>8}{'prec':>7}{'F1':>7}")
for c in ORDER:
    f1, s, m, n = best[c]
    print(f"{c:<13}{s:>5.1f}{n:>6}{m['matched']:>9}{m['recall']:>8.3f}{m['precision']:>7.3f}{f1:>7.3f}")

qs = np.quantile(dbh, [0, .25, .5, .75, 1.0])
print(f"\ndetection rate by DBH quartile (cm), 1.5 m separation")
print(f"{'cloud':<13}" + "".join(f"{f'{qs[i]:.0f}-{qs[i+1]:.0f}':>10}" for i in range(4))
      + f"{'pine':>8}{'spruce':>8}")
for c in ORDER:
    q = tops(c, 1.5)
    cost = np.linalg.norm(q[:, None, :] - REF[None, :, :], axis=2)
    i, j = linear_sum_assignment(cost)
    ok = cost[i, j] <= 2.0
    hit = np.zeros(len(REF), bool); hit[j[ok]] = True
    cls = np.clip(np.searchsorted(qs[1:-1], dbh, side="right"), 0, 3)
    print(f"{c:<13}" + "".join(f"{100*hit[cls==k].mean():>9.0f}%" for k in range(4))
          + f"{100*hit[spec==1].mean():>7.0f}%{100*hit[spec==2].mean():>7.0f}%")
