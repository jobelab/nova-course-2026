# NOVA course 2026 — point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""CHM watershed tree segmentation — a Python port of the PCT crown detection.

This is the reference method to compare against: Tuomas Yrttimaa's *Point-Cloud-Tools*
(PCT), `pc_detect_tree_crowns_v2.m`. It is **top-down** — find the tree tops in a
canopy height model and let watershed basins fall out from them — where
`novatrees.pipeline` is **bottom-up**, growing outward from stem cross-sections.

Comparing the two is the interesting part. They disagree in characteristic ways:
CHM watershed finds a tree wherever there is a distinct canopy bump, so it sees
suppressed trees only if their crown reaches daylight, and it splits one broad
crown into two whenever the top is forked. Cross-section seeding finds a tree
wherever there is a stem at breast height, so it sees suppressed stems fine but
misses anything whose stem is occluded.

Ported from the MATLAB steps:

    pc2dem(..., CornerFillMethod="max")   -> _rasterize_max
    fspecial("gaussian",[3 3],1)          -> gaussian(sigma=1)
    helperDetectTreeTops                  -> peak_local_max
    helperSegmentTrees                    -> marker-controlled watershed
    convhull per label, area >= minCrownArea

Original tools by Dr. Tuomas Yrttimaa, University of Eastern Finland, released
CC BY 4.0. This file is a derivative work, distributed under GPL-3.0-or-later as
CC BY 4.0 section 3(a) permits, with the upstream attribution preserved. The
original remains CC BY 4.0 at source. See NOTICE at the repository root. Cite Yrttimaa (2021), https://doi.org/10.5281/zenodo.5779288, and the
methods papers https://doi.org/10.3390/rs11121423 and
https://doi.org/10.1016/j.isprsjprs.2020.08.017.

MATLAB's `helperDetectTreeTops` uses a height-varying window; `peak_local_max`
with a single `min_distance` is the closest scikit-image equivalent, so tree-top
counts will not match the MATLAB tool exactly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from skimage.feature import peak_local_max
from skimage.filters import gaussian
from skimage.segmentation import watershed

from .dataset import chm_dataarray
from .dataset import xyz as _xyz

__all__ = ["ChmParams", "chm_segment", "rasterize_chm"]


@dataclass
class ChmParams:
    """Defaults follow PCT `mainscript.m`."""

    pixel_size: float = 0.20  # chmPixelSize
    min_crown_area: float = 2.0  # minCrownArea, m^2
    min_tree_height: float = 2.0  # minTreeHeight, m
    smooth_sigma: float = 1.0  # fspecial("gaussian",[3 3],1)
    min_distance: float = 1.0  # tree-top separation, m (stands in for the
    # height-varying window in helperDetectTreeTops)
    ground_z: float = 0.30


def rasterize_chm(xyz: np.ndarray, pixel_size: float) -> tuple[np.ndarray, tuple[float, float]]:
    """Max-height raster, the pc2dem(CornerFillMethod="max") step."""
    x0, y0 = xyz[:, 0].min(), xyz[:, 1].min()
    cols = np.floor((xyz[:, 0] - x0) / pixel_size).astype(np.int64)
    rows = np.floor((xyz[:, 1] - y0) / pixel_size).astype(np.int64)
    nr, nc = rows.max() + 1, cols.max() + 1

    chm = np.zeros((nr, nc), np.float32)
    flat = rows * nc + cols
    np.maximum.at(chm.reshape(-1), flat, xyz[:, 2].astype(np.float32))
    chm[~np.isfinite(chm) | (chm < 0)] = 0.0  # MATLAB: canopyModel(isnan|<0) = 0
    return chm, (x0, y0)


def chm_segment(cloud, p: ChmParams = ChmParams()) -> dict:
    """Segment trees by marker-controlled watershed on the CHM.

    `cloud` may be an xarray Dataset or an (n, 3) array. Returns a dict whose
    "chm" is a labelled DataArray carrying real x/y coordinates.
    """
    xyz = _xyz(cloud)
    above = xyz[:, 2] > p.ground_z
    P = xyz[above]

    chm, (x0, y0) = rasterize_chm(P, p.pixel_size)
    chm_s = gaussian(chm, sigma=p.smooth_sigma, preserve_range=True)

    min_dist_px = max(1, int(round(p.min_distance / p.pixel_size)))
    tops = peak_local_max(
        chm_s,
        min_distance=min_dist_px,
        threshold_abs=p.min_tree_height,
        exclude_border=False,
    )

    markers = np.zeros(chm_s.shape, np.int32)
    for i, (r, c) in enumerate(tops, start=1):
        markers[r, c] = i

    mask = chm_s >= p.min_tree_height
    labels2d = watershed(-chm_s, markers, mask=mask)

    # Drop crowns smaller than minCrownArea (PCT rejects these before writing a
    # polygon), then renumber so labels stay contiguous.
    px_area = p.pixel_size**2
    counts = np.bincount(labels2d.ravel())
    too_small = np.where(counts * px_area < p.min_crown_area)[0]
    too_small = too_small[too_small > 0]
    if len(too_small):
        labels2d[np.isin(labels2d, too_small)] = 0
    keep = np.unique(labels2d)
    keep = keep[keep > 0]
    remap = np.zeros(labels2d.max() + 1, np.int32)
    remap[keep] = np.arange(1, len(keep) + 1)
    labels2d = remap[labels2d]

    cols = np.clip(np.floor((P[:, 0] - x0) / p.pixel_size).astype(np.int64), 0, chm.shape[1] - 1)
    rows = np.clip(np.floor((P[:, 1] - y0) / p.pixel_size).astype(np.int64), 0, chm.shape[0] - 1)
    lab_pts = labels2d[rows, cols] - 1  # 0-based, -1 = unassigned

    labels = np.full(len(xyz), -1, np.int32)
    labels[above] = lab_pts

    top_xy = np.c_[
        x0 + (tops[:, 1] + 0.5) * p.pixel_size,
        y0 + (tops[:, 0] + 0.5) * p.pixel_size,
        chm_s[tops[:, 0], tops[:, 1]],
    ]
    # Keep only tops whose basin survived the area filter.
    surviving = labels2d[tops[:, 0], tops[:, 1]] > 0
    top_xy = top_xy[surviving]

    sizes = np.bincount(labels[labels >= 0], minlength=max(len(keep), 1))
    return {
        "chm": chm_dataarray(chm_s, (x0, y0), p.pixel_size),
        "origin": (x0, y0),
        "pixel_size": p.pixel_size,
        "tops": top_xy,
        "labels2d": labels2d,
        "labels": labels,
        "stats": {
            "n_trees": int(len(keep)),
            "n_tops_detected": int(len(tops)),
            "n_tops_kept": int(surviving.sum()),
            "chm_shape": tuple(int(v) for v in chm.shape),
            "points_labelled": int((labels >= 0).sum()),
            "points_per_tree_median": int(np.median(sizes)) if len(sizes) else 0,
            "points_per_tree_max": int(sizes.max()) if len(sizes) else 0,
        },
    }
