# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Noise filtering: removing points that no surface put there.

Three kinds of point get called noise, and they need different treatment.

**Isolated returns.** Birds, insects, rain, dust, and the stray return from a
scanner's own housing. These sit far from any surface and both filters below
remove them easily.

**Mixed pixels**, also called edge or ghost points. A beam straddling the edge of a
stem returns a distance averaged between the stem and whatever is behind it, so the
point lands in empty space along the line of sight. These are the ones that matter
here: they form a faint halo around every stem, and a circle fitted through that
halo comes out too large. They are harder to remove because they are not isolated,
they are thinly but consistently distributed.

**Registration ghosts** in multi-scan or mobile data, where the same surface appears
twice a few centimetres apart. Neither filter here removes those; they need better
registration, not outlier rejection.

Two methods, matching what CloudCompare offers:

* `statistical` compares each point's mean distance to its k nearest neighbours
  against the cloud-wide distribution, and rejects the tail. Good on isolated
  returns, adaptive to varying density, and the usual first choice.
* `radius` rejects points with too few neighbours inside a fixed radius. Blunter,
  and it needs a radius chosen for the local density, which makes it awkward on a
  cloud whose density falls off with range, as every terrestrial scan's does.

**Filter after normalising, before slicing.** Noise near the ground corrupts the
DTM if removed too late, and a halo around stems corrupts the circle fits if
removed too early relative to slicing.

Measured on the Day 4 plot 167, statistical filtering at the preset settings:

    MLS   2.9 M points   removed 4.81%   5.3 s
    ALS   2.8 M points   removed 1.78%   3.0 s

With two sensors over one plot the filter can be checked rather than trusted. ALS
sees the canopy top properly and puts it at 162.72 m over the MLS footprint, while
MLS carries 5,853 points (0.15%) above that. Nothing in the plot is that tall, so
those are unambiguously noise, and it is reassuring that the filter targets them.
It is also not aggressive enough: it kept MLS returns up to 164.5 m, which is still
1.8 m above anything real. Tighten `n_sigma` for MLS if the canopy-top metrics
matter.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from .dataset import xyz as _xyz

__all__ = ["DenoiseParams", "denoise", "denoise_statistical", "denoise_radius"]


@dataclass
class DenoiseParams:
    method: str = "statistical"  # "statistical" or "radius"
    k: int = 8  # neighbours for the statistical test
    n_sigma: float = 2.0  # reject beyond mean + n_sigma * std of mean distance
    radius: float = 0.10  # neighbourhood for the radius test (m)
    min_neighbours: int = 4  # fewer than this inside `radius` and the point goes
    chunk: int = 2_000_000  # query in chunks to bound memory


def denoise_statistical(cloud, k: int = 8, n_sigma: float = 2.0, chunk: int = 2_000_000):
    """Statistical outlier removal. Returns a boolean keep-mask.

    The threshold is global (mean plus `n_sigma` standard deviations of the mean
    neighbour distance), which is the standard formulation and its main weakness:
    in a cloud whose density varies by orders of magnitude with range, one global
    threshold is generous near the scanner and harsh far from it. On a plot-scale
    terrestrial cloud that is tolerable. On a full mobile transect it is not, and
    the filter should be applied per tile.
    """
    P = _xyz(cloud)
    n = len(P)
    if n <= k:
        return np.ones(n, bool)

    tree = cKDTree(P)
    mean_d = np.empty(n)
    for start in range(0, n, chunk):
        stop = min(start + chunk, n)
        d, _ = tree.query(P[start:stop], k=k + 1, workers=-1)
        mean_d[start:stop] = d[:, 1:].mean(axis=1)  # column 0 is the point itself

    thresh = mean_d.mean() + n_sigma * mean_d.std()
    return mean_d <= thresh


def denoise_radius(cloud, radius: float = 0.10, min_neighbours: int = 4,
                   chunk: int = 2_000_000):
    """Radius outlier removal. Returns a boolean keep-mask."""
    P = _xyz(cloud)
    n = len(P)
    tree = cKDTree(P)
    keep = np.ones(n, bool)
    for start in range(0, n, chunk):
        stop = min(start + chunk, n)
        counts = tree.query_ball_point(P[start:stop], r=radius, workers=-1,
                                       return_length=True)
        keep[start:stop] = counts > min_neighbours  # the point counts itself
    return keep


def denoise(cloud, p: DenoiseParams = DenoiseParams()):
    """Noise filter. Returns a boolean keep-mask over the input points."""
    if p.method == "statistical":
        return denoise_statistical(cloud, k=p.k, n_sigma=p.n_sigma, chunk=p.chunk)
    if p.method == "radius":
        return denoise_radius(cloud, radius=p.radius, min_neighbours=p.min_neighbours,
                              chunk=p.chunk)
    raise ValueError(f"unknown method {p.method!r}; use 'statistical' or 'radius'")
