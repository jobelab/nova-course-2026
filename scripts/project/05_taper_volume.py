#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stem taper, volume, and the fusion argument tested rather than assumed.

Reproduces notebooks/project/06_taper_and_volume.py. The last block reconstructs the
same stems with and without a drone-supplied total height, which is the test the
usual multi-sensor argument for volume did not survive.
"""
import sys, warnings; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, laspy
import _common as C
from novatrees.chm_watershed import ChmParams, chm_segment
from novatrees.extract import StemTrackParams, track_stem_axis
from novatrees.stems import StemParams, detect_stems
from novatrees.taper import TaperParams, taper_curve
from novatrees.terrain import normalize_against
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

dtm, _ = C.terrain()
B = C.height_band(C.TLS, dtm, zoff=C.TLS_CONST)
st = detect_stems(B, StemParams())
centres = np.column_stack([st["x"], st["y"]])
print(f"{len(st)} stems detected in the TLS")

# total height comes from the drone, the only thing that sees the top
f = laspy.read(str(C.DRONE / "Nadir_RGB_plot167_20m.las"))
xyz = np.column_stack([f.x, f.y, f.z])
H = np.column_stack([xyz[:, 0], xyz[:, 1], normalize_against(xyz, dtm)])
seg = chm_segment(H, ChmParams(pixel_size=0.20, min_distance=1.5,
                               min_tree_height=5.0, min_crown_area=3.0))
lab, tops = seg["labels"], seg["tops"]
crown_h = np.array([np.percentile(H[lab == k, 2], 95) if (lab == k).sum() > 30 else np.nan
                    for k in range(len(tops))])
cost = np.linalg.norm(centres[:, None, :] - tops[None, :, :2], axis=2)
i, j = linear_sum_assignment(cost); ok = cost[i, j] <= 3.0
h_of = np.full(len(st), np.nan); h_of[i[ok]] = crown_h[j[ok]]
print(f"{ok.sum()} stems paired with a drone crown for total height")


def neighbourhoods(path, zoff, rad=0.8, chunk=2_000_000):
    """Full-detail points around each stem. A KD-tree, not an n-by-k distance matrix:
    a 2 M by 35 array per chunk is half a gigabyte."""
    tree = cKDTree(centres)
    out = [[] for _ in centres]
    with laspy.open(str(path)) as fh:
        for pts in fh.chunk_iterator(chunk):
            x, y = np.asarray(pts.x), np.asarray(pts.y)
            z = np.asarray(pts.z) + zoff
            dm, k = tree.query(np.column_stack([x, y]), distance_upper_bound=rad)
            m = np.isfinite(dm)
            if not m.any():
                continue
            h = z[m] - dtm.sample(x[m], y[m])
            good = (h >= 0.2) & (h <= 35)
            P = np.column_stack([x[m][good], y[m][good], h[good]]); kk = k[m][good]
            for t in np.unique(kk):
                out[t].append(P[kk == t])
            del x, y, z, dm, k, m, h, P, kk
    return [C.voxel(np.vstack(v), 0.01) if v else np.empty((0, 3)) for v in out]


NB = neighbourhoods(C.TLS, C.TLS_CONST)
tp = TaperParams(); tp.ransac_iterations = 600; tp.min_occupancy = 0.5; tp.align_axis = True

rows, paired = [], []
for n, (P, h) in enumerate(zip(NB, h_of)):
    if len(P) < 2000:
        continue
    try:
        _, mask = track_stem_axis(P, np.array([st["x"][n], st["y"][n], 1.30]), StemTrackParams())
        S = P[mask]
        if len(S) < 500:
            continue
        r = taper_curve(S, tp, total_height=(None if np.isnan(h) else float(h)))
        rows.append(dict(volume=r.volume_measured, covered=r.covered_fraction,
                         form=r.form_factor_measured, dbh_taper=r.dbh * 100,
                         dbh_slice=st["dbh"][n] * 100))
        if not np.isnan(h):
            b = taper_curve(S, tp, total_height=None)
            paired.append(dict(v_with=r.volume_measured, v_without=b.volume_measured,
                               f_with=r.form_factor_measured, f_without=b.form_factor_measured,
                               c_with=r.covered_fraction, c_without=b.covered_fraction))
    except Exception:
        continue

T = pd.DataFrame(rows).dropna(subset=["volume"])
print(f"\ntaper reconstructed for {len(T)} stems")
print(f"  DBH taper vs cross-section fit   r {T.dbh_taper.corr(T.dbh_slice):+.3f}")
print(f"  covered fraction  median {T.covered.median():.2f}  [{T.covered.quantile(.25):.2f}, {T.covered.quantile(.75):.2f}]")
print(f"  form factor       median {T.form.median():.3f}  [{T.form.quantile(.25):.3f}, {T.form.quantile(.75):.3f}]")
print(f"  form factor vs covered fraction  r {T.form.corr(T.covered):+.3f}")
print(f"  stem volume       median {T.volume.median():.3f} m3   total {T.volume.sum():.2f} m3")

U = pd.DataFrame(paired)
print(f"\nsame {len(U)} stems, with and without the drone height")
print(f"  measured volume  {U.v_with.median():.3f} m3  against  {U.v_without.median():.3f} m3")
print(f"  form factor      {U.f_with.median():.3f}     against  {U.f_without.median():.3f}")
print(f"  covered fraction {U.c_with.median():.3f}     against  {U.c_without.median():.3f}")
