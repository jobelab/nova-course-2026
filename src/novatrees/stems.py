# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Stem detection and DBH from a breast-height cross-section, fitted robustly.

`pipeline.detect_seeds` clusters the slice and fits each cluster with a Taubin
circle over every point in it. That is fine on a clean plot and poor on this one:
the fit has no defence against a cluster that also contains a low branch, a
neighbouring stem or understorey, and it returned diameters biased +7.3 cm with
essentially no correlation to the field measurement (r = +0.12 on 35 stems).

The difference here is what happens after the clustering. A RANSAC circle ignores
the points that do not belong to it, and three gates then decide whether the fit
describes a stem at all: how round it is, how much of the circumference the points
actually cover, and whether the cluster continues above and below breast height.
Arc coverage is the one that matters most, because a scanner sees one side of a
stem and a circle through a short arc is nearly unconstrained.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["StemParams", "detect_stems"]


@dataclass
class StemParams:
    slice_lo: float = 1.15          # breast-height slab, m above ground
    slice_hi: float = 1.45
    eps: float = 0.05               # DBSCAN neighbourhood in the 2D slice (m)
    min_samples: int = 10
    min_cluster_pts: int = 40
    min_radius: float = 0.03        # 6 cm DBH and up
    max_radius: float = 0.35        # 70 cm DBH
    max_extent: float = 0.90        # a cluster wider than this is not one stem
    max_sigma: float = 0.02         # residual of the fit (m); a stem is round
    min_inlier_frac: float = 0.60
    min_arc: float = 0.25           # fraction of the circumference with points
    ransac_iterations: int = 400
    ransac_threshold: float = 0.02
    support_band: float = 0.30      # thickness of the check slabs above and below
    support_gap: float = 0.15
    min_support: int = 10


def detect_stems(xyz: np.ndarray, p: StemParams = StemParams(), seed: int = 0):
    """Find stems in a height-normalised cloud. Returns a structured array.

    Fields: `x`, `y`, `dbh` (m), `sigma` (fit residual, m), `arc` (0 to 1),
    `n` (points in the cluster), `inlier_frac`. Keeping the quality fields rather
    than discarding them is deliberate: they are what make a diameter defensible,
    and they let a later stage tighten the gates without re-running the clustering.
    """
    from scipy.spatial import cKDTree
    from sklearn.cluster import DBSCAN

    from .stemgeom import sector_occupancy
    from .taper import TaperParams, ransac_circle

    xyz = np.asarray(xyz, dtype=np.float64)
    sl = xyz[(xyz[:, 2] >= p.slice_lo) & (xyz[:, 2] < p.slice_hi)]
    if len(sl) == 0:
        return np.empty(0, dtype=_DTYPE)

    labels = DBSCAN(eps=p.eps, min_samples=p.min_samples, n_jobs=-1).fit_predict(sl[:, :2])

    lo0 = p.slice_lo - p.support_gap - p.support_band
    hi0 = p.slice_hi + p.support_gap
    below = cKDTree(xyz[(xyz[:, 2] >= lo0) & (xyz[:, 2] < lo0 + p.support_band)][:, :2])
    above = cKDTree(xyz[(xyz[:, 2] >= hi0) & (xyz[:, 2] < hi0 + p.support_band)][:, :2])

    rng = np.random.default_rng(seed)
    tp = TaperParams()
    tp.min_radius, tp.max_radius = p.min_radius, p.max_radius
    out = []
    for c in range(labels.max() + 1):
        pts = sl[labels == c][:, :2]
        if len(pts) < p.min_cluster_pts:
            continue
        if float((pts.max(0) - pts.min(0)).max()) > p.max_extent:
            continue
        fit = ransac_circle(pts, p.ransac_iterations, p.ransac_threshold, rng, tp)
        if fit is None:
            continue
        xc, yc, r, sigma, n_in = fit
        if not (p.min_radius <= r <= p.max_radius) or sigma > p.max_sigma:
            continue
        if n_in / len(pts) < p.min_inlier_frac:
            continue
        arc = sector_occupancy(pts, xc, yc)
        if arc < p.min_arc:
            continue
        probe = r + 0.10
        if len(below.query_ball_point([xc, yc], probe)) < p.min_support:
            continue
        if len(above.query_ball_point([xc, yc], probe)) < p.min_support:
            continue
        out.append((xc, yc, 2 * r, sigma, arc, len(pts), n_in / len(pts)))
    return np.array(out, dtype=_DTYPE) if out else np.empty(0, dtype=_DTYPE)


_DTYPE = np.dtype([
    ("x", "f8"), ("y", "f8"), ("dbh", "f8"), ("sigma", "f8"),
    ("arc", "f8"), ("n", "i8"), ("inlier_frac", "f8"),
])
