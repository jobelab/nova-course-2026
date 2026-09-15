#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Terrain from the ALS, tied to MLS ground control, and height distributions.

Reproduces the numbers in notebooks/project/02_terrain_and_heights.py.
"""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import numpy as np
import _common as C
from novatrees.csf import csf_ground

dtm, offset = C.terrain(rebuild=True)
p = C.csf_params()
M = C.normalised(C.MLS, dtm, target=2_000_000)          # for the control residual
Mabs = np.column_stack([M[:, 0], M[:, 1], M[:, 2] + dtm.sample(M[:, 0], M[:, 1])])
Mg = Mabs[csf_ground(Mabs, p)]
res = Mg[:, 2] - dtm.sample(Mg[:, 0], Mg[:, 1])

print("ALS terrain against MLS ground control")
print(f"  offset applied {offset:+.3f} m over {len(Mg):,} control points")
print(f"  after correction: median {np.median(res):+.3f} m  RMSE {np.sqrt((res**2).mean()):.3f} m"
      f"  p05 {np.percentile(res,5):+.3f}  p95 {np.percentile(res,95):+.3f}")
zc = float(dtm.sample(np.r_[C.CX], np.r_[C.CY])[0])
print(f"  DTM at plot centre {zc:.3f} m, surveyed {C.SURVEY_Z:.3f} m, difference {zc-C.SURVEY_Z:+.3f} m")

T = C.normalised(C.TLS, dtm, zoff=0.0, target=1_500_000)
Tabs = np.column_stack([T[:, 0], T[:, 1], T[:, 2] + dtm.sample(T[:, 0], T[:, 1])])
Tg = Tabs[csf_ground(Tabs, p)]
const = float(np.median(dtm.sample(Tg[:, 0], Tg[:, 1]) - Tg[:, 2]))
print(f"\nTLS normalisation constant recovered: {const:.3f} m "
      f"(the surveyed value would be wrong by {const-C.SURVEY_Z:+.3f} m)")

print(f"\n{'cloud':<14}{'points':>10}{'p50':>8}{'p95':>8}{'p99':>8}{'max':>8}{'<0.5 m':>9}")
rows = {n: C.normalised(C.DRONE / f"{n}_plot167_20m.las", dtm, target=800_000)[:, 2]
        for n in C.DRONE_CLOUDS}
rows["TLS"] = C.normalised(C.TLS, dtm, zoff=const, target=800_000)[:, 2]
rows["MLS"] = C.normalised(C.MLS, dtm, target=800_000)[:, 2]
rows["ALS"] = C.normalised(C.ALS, dtm, target=800_000)[:, 2]
for n, h in rows.items():
    print(f"{n:<14}{len(h):>10,}{np.percentile(h,50):>8.2f}{np.percentile(h,95):>8.2f}"
          f"{np.percentile(h,99):>8.2f}{h.max():>8.2f}{100*(h<0.5).mean():>8.1f}%")
