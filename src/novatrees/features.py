# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Point features for separating stem from foliage, and a weighted screen.

Three signals say "this point is on a stem", and they fail in different places,
which is why the course demo combines them rather than picking one:

* **verticality** - a stem surface is a patch of a vertical cylinder, so its
  normal points sideways. High for stems, high for tree-sized noise, low for
  ground and for flat foliage clumps.
* **reflectance** - bark returns far more strongly than needles. On the course
  plot the two sit about 9 dB apart, which makes this the single strongest
  feature, and it is one that geometry cannot supply.
* **radial distance** - stem points hug the tree's vertical axis; branches reach
  away from it. Only meaningful once seeds exist, so it refines rather than
  bootstraps.

Each is scaled to 0–1 on its 1st–99th percentiles (not min–max, so one outlier
cannot squash the range), weighted, and summed. `prescreen_pct` then keeps that
percentage of the highest-scoring points - lower is tighter.

The reflectance transform is the demo's own arithmetic: add 26, divide by 31,
invert, log10. Those constants are calibrated to *this* scanner - they map its
raw range (−25.0 … 5.0 dB) onto almost exactly 0–1 - so re-derive them from
`reflectance_bounds()` before using this on another instrument.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from .dataset import xyz as _xyz

__all__ = [
    "StemScoreParams",
    "eigen_features",
    "reflectance_index",
    "reflectance_bounds",
    "stem_score",
    "stem_prescreen",
]


@dataclass
class StemScoreParams:
    """Weights are relative - they are normalised to sum to 1."""

    k: int = 20  # neighbours for the local PCA
    w_vertical: float = 0.4
    w_reflectance: float = 0.4
    w_radial: float = 0.2
    prescreen_pct: float = 40.0  # keep this % of highest-scoring points
    refl_offset: float = 26.0  # the demo's "+26"
    refl_scale: float = 31.0  # the demo's "/31"


def eigen_features(points, k: int = 20) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Local PCA per point. Returns (verticality, planarity, linearity).

    Verticality is ``1 - |n_z|`` for ``n`` the smallest eigenvector, i.e. the
    surface normal. This is the same quantity CloudCompare produces via
    *Edit > Normals > Compute* followed by *Export normals to SF(s)*; the demo
    asks for a 0.015 m neighbourhood, and k=20 gives a median radius of about
    0.012 m on TLS data of this density.
    """
    P = _xyz(points)
    if len(P) < k:
        k = max(3, len(P))
    _, nn = cKDTree(P).query(P, k=k, workers=-1)
    Q = P[nn]
    Q = Q - Q.mean(axis=1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", Q, Q) / k
    w, v = np.linalg.eigh(cov)  # ascending
    l3, l2, l1 = w[:, 0], w[:, 1], w[:, 2]
    normal = v[:, :, 0]
    verticality = 1.0 - np.abs(normal[:, 2])
    with np.errstate(divide="ignore", invalid="ignore"):
        planarity = np.where(l1 > 0, (l2 - l3) / l1, 0.0)
        linearity = np.where(l1 > 0, (l1 - l2) / l1, 0.0)
    return verticality, planarity, linearity


def reflectance_bounds(reflectance: np.ndarray) -> tuple[float, float]:
    """Offset and scale that would put this sensor's reflectance on 0–1.

    Returns ``(offset, scale)`` for use as `refl_offset` / `refl_scale`. The demo's
    26 and 31 fall straight out of this for the course scanner.
    """
    lo, hi = float(np.min(reflectance)), float(np.max(reflectance))
    offset = -lo + 1.0
    return offset, float(np.ceil(hi + offset))


def reflectance_index(
    reflectance: np.ndarray, offset: float = 26.0, scale: float = 31.0
) -> np.ndarray:
    """The demo's reflectance arithmetic: +offset, /scale, invert, log10.

    **Low values mean a strong return**, i.e. bark. Stems land near 0.09 on the
    course plot and foliage near 0.23.
    """
    x = (np.asarray(reflectance, float) + offset) / scale
    return np.log10(1.0 / np.clip(x, 1e-9, None))


def _unit(v: np.ndarray, lo: float = 1.0, hi: float = 99.0, invert: bool = False) -> np.ndarray:
    a, b = np.percentile(v, lo), np.percentile(v, hi)
    s = np.clip((v - a) / max(b - a, 1e-9), 0.0, 1.0)
    return 1.0 - s if invert else s


def stem_score(
    points,
    reflectance: np.ndarray | None = None,
    seeds: np.ndarray | None = None,
    p: StemScoreParams = StemScoreParams(),
) -> np.ndarray:
    """Weighted 0–1 stem likeness per point.

    Missing inputs drop out cleanly: without `reflectance` the reflectance term is
    skipped, without `seeds` the radial term is. Weights are renormalised over
    whatever remains, so a geometry-only score is just `w_vertical` alone.
    """
    P = _xyz(points)
    vert, _, _ = eigen_features(P, k=p.k)

    terms, weights = [_unit(vert)], [p.w_vertical]

    if reflectance is not None and p.w_reflectance > 0:
        idx = reflectance_index(reflectance, p.refl_offset, p.refl_scale)
        terms.append(_unit(idx, invert=True))  # low index = bark
        weights.append(p.w_reflectance)

    if seeds is not None and len(seeds) and p.w_radial > 0:
        d, _ = cKDTree(np.asarray(seeds)[:, :2]).query(P[:, :2], workers=-1)
        terms.append(_unit(d, invert=True))  # close to an axis = stem-like
        weights.append(p.w_radial)

    total = sum(weights)
    if total <= 0:
        return np.zeros(len(P))
    return sum(w * t for w, t in zip(weights, terms)) / total


def stem_prescreen(
    points,
    reflectance: np.ndarray | None = None,
    seeds: np.ndarray | None = None,
    p: StemScoreParams = StemScoreParams(),
) -> np.ndarray:
    """Boolean mask keeping the top `prescreen_pct` percent by `stem_score`."""
    score = stem_score(points, reflectance, seeds, p)
    if p.prescreen_pct >= 100:
        return np.ones(len(score), bool)
    cut = np.percentile(score, 100.0 - p.prescreen_pct)
    return score >= cut
