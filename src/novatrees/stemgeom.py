# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Cross-section geometry: how much of a stem is visible, how round it is, and
whether it is still one stem.

Three measurements that a horizontal slice through a stem can give you, and what
each is actually good for.

**Sector occupancy** is the fraction of the circumference that has points behind
it. A circle fitted to a 30% arc is a guess; the same fit on a 90% arc is a
measurement. This is the single most useful quality flag, and it is cheap.

**Axis ratio** from an ellipse fit is a quality flag, not a lean measurement. The
geometry says a cylinder leaning by theta cuts a horizontal plane in an ellipse of
axis ratio cos(theta), so lean should be recoverable. Measured on this plot it is
not: median lean is 4.4 degrees, which predicts an axis ratio of 0.997, while the
observed median is about 0.84. Real stems are that far from circular anyway, from
ovality and bark ridges, so the lean signal sits roughly 50x below the noise floor.
Correlation between ellipse-derived and PCA-derived lean came out at 0.25 even with
a properly constrained fit. Use the axis ratio to spot slices where something
non-stem entered the fit, and take lean from the tracked centreline instead.

**Component count** per band detects structure, but only with a persistence test.
Counting clusters naively flags every tree as forked: on this plot all 32 trees
split below 14 m, some at 1.0 m, with 10 or more components by 8 m. Those are
branches and intruding neighbours. A real fork is two components that *both* behave
like stems over a run of consecutive bands.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "ForkParams",
    "sector_occupancy",
    "fit_ellipse",
    "axis_ratio",
    "band_components",
    "find_forks",
]


def sector_occupancy(points_2d: np.ndarray, cx: float, cy: float, n_sectors: int = 16) -> float:
    """Fraction of the circumference around (cx, cy) that has points in it.

    dendromatics uses the same idea to reject circles fitted from one visible arc.
    Returns 0..1.
    """
    if len(points_2d) == 0:
        return 0.0
    ang = np.arctan2(points_2d[:, 1] - cy, points_2d[:, 0] - cx)
    idx = ((ang + np.pi) / (2 * np.pi) * n_sectors).astype(int) % n_sectors
    return float(np.unique(idx).size / n_sectors)


def fit_ellipse(points_2d: np.ndarray):
    """Fitzgibbon direct least-squares ellipse fit. Returns (a, b) or None.

    The ellipse-specific constraint (4ac - b^2 = 1) matters: an unconstrained conic
    fit drifts to absurdly eccentric solutions on noisy arcs, which is what made a
    first attempt at this report 67 degrees of lean for a stem tilted 5.
    """
    from scipy.linalg import eig

    P = np.asarray(points_2d, float)
    if len(P) < 6:
        return None
    x = P[:, 0] - P[:, 0].mean()
    y = P[:, 1] - P[:, 1].mean()
    s = max(float(np.abs(np.r_[x, y]).max()), 1e-9)
    x, y = x / s, y / s

    D1 = np.c_[x * x, x * y, y * y]
    D2 = np.c_[x, y, np.ones_like(x)]
    S1, S2, S3 = D1.T @ D1, D1.T @ D2, D2.T @ D2
    try:
        T = -np.linalg.solve(S3, S2.T)
        M = np.linalg.solve(np.array([[0, 0, 2.0], [0, -1.0, 0], [2.0, 0, 0]]), S1 + S2 @ T)
    except np.linalg.LinAlgError:
        return None

    w, v = eig(M)
    cond = 4 * v[0].real * v[2].real - v[1].real ** 2
    if not np.any(cond > 0):
        return None
    a1 = v[:, int(np.argmax(np.where(cond > 0, cond, -np.inf)))].real
    A, B, C, D, E, F = *a1, *(T @ a1)

    M0 = np.array([[A, B / 2], [B / 2, C]])
    try:
        cx, cy = np.linalg.solve(2 * M0, [-D, -E])
    except np.linalg.LinAlgError:
        return None
    Fc = A * cx * cx + B * cx * cy + C * cy * cy + D * cx + E * cy + F
    ev = np.linalg.eigvalsh(M0)
    if np.any(ev == 0):
        return None
    ax2 = -Fc / ev
    if np.any(ax2 <= 0):
        return None
    ax = np.sqrt(ax2) * s
    return float(max(ax)), float(min(ax))


def axis_ratio(points_2d: np.ndarray) -> float:
    """Minor over major axis, 1.0 for a circle. NaN if no ellipse could be fitted.

    A **quality flag**, not a lean estimate: see the module docstring.
    """
    e = fit_ellipse(points_2d)
    if e is None or e[0] <= 0:
        return float("nan")
    return float(e[1] / e[0])


@dataclass
class ForkParams:
    """Deciding whether a tree has more than one stem."""

    band: float = 0.20  # slab thickness per band (m)
    step: float = 0.25  # advance between bands (m)
    z_start: float = 1.30
    z_stop: float = 14.0
    eps: float = 0.10  # clustering neighbourhood inside a band (m)
    min_samples: int = 15
    min_points: int = 40  # a component below this is ignored
    min_radius: float = 0.02
    max_radius: float = 0.60
    min_occupancy: float = 0.35  # a component seen from too few angles is not trusted
    max_drift: float = 0.20  # a stem centre moves less than this per step (m)
    persist_bands: int = 4  # a chain must survive this many bands to be considered
    match_radius: float = 0.30  # link components between bands within this distance (m)

    # Persistence alone is not enough. A branch also survives a metre, so without
    # these three every tree reads as forked: on this plot the persistence test
    # alone flagged 12 of 12 large trees, one with five "stems".
    min_extent: float = 2.0  # a stem runs at least this far vertically (m)
    max_lean: float = 25.0  # ...and stays within this of vertical (degrees)
    min_radius_frac: float = 0.35  # ...and is at least this fraction of the main stem


def band_components(points: np.ndarray, zc: float, p: ForkParams = ForkParams()) -> list[dict]:
    """Cluster one horizontal band and describe each stem-like component."""
    import circle_fit
    from sklearn.cluster import DBSCAN

    sl = points[np.abs(points[:, 2] - zc) <= p.band / 2]
    if len(sl) < p.min_points:
        return []

    lab = DBSCAN(eps=p.eps, min_samples=p.min_samples, n_jobs=-1).fit_predict(sl[:, :2])
    out = []
    for c in range(lab.max() + 1):
        q = sl[lab == c][:, :2]
        if len(q) < p.min_points:
            continue
        try:
            cx, cy, r, _ = circle_fit.taubinSVD(q)
        except Exception:
            continue
        if not (p.min_radius <= r <= p.max_radius):
            continue
        occ = sector_occupancy(q, cx, cy)
        if occ < p.min_occupancy:
            continue
        out.append({"z": float(zc), "x": float(cx), "y": float(cy), "r": float(r),
                    "n": int(len(q)), "occupancy": occ, "axis_ratio": axis_ratio(q)})
    return out


def _chain_stats(chain: list[dict]) -> dict:
    """Vertical extent, lean and median radius of a tracked chain."""
    pts = [c for c in chain if c is not None]
    if len(pts) < 2:
        return {"extent": 0.0, "lean": 90.0, "r": 0.0, "n": len(pts)}
    z = np.array([c["z"] for c in pts])
    xy = np.array([[c["x"], c["y"]] for c in pts])
    extent = float(z.max() - z.min())
    drift = float(np.hypot(*(xy[-1] - xy[0])))
    lean = float(np.degrees(np.arctan2(drift, max(extent, 1e-6))))
    return {"extent": extent, "lean": lean,
            "r": float(np.median([c["r"] for c in pts])), "n": len(pts)}


def is_stem_like(chain: list[dict], main_r: float, p: ForkParams = ForkParams()) -> bool:
    """Does this chain behave like a stem rather than a branch?

    A branch departs and keeps going: it leans hard, thins, and does not run far
    vertically. A second stem stays near vertical, holds its radius, and runs for
    metres. All three tests are needed, and dropping any one of them lets branches
    back in.
    """
    s = _chain_stats(chain)
    return (
        s["n"] >= p.persist_bands
        and s["extent"] >= p.min_extent
        and s["lean"] <= p.max_lean
        and s["r"] >= p.min_radius_frac * max(main_r, 1e-6)
    )


def find_forks(points: np.ndarray, p: ForkParams = ForkParams()):
    """Track stem-like components upward and report where more than one is a stem.

    Returns (tracks, forks). `tracks` are the chains that passed `is_stem_like`;
    `forks` is a DataFrame of heights where two or more of them are alive at once.

    Counting clusters alone marks every tree as forked, and adding persistence
    alone is still not enough. What separates a fork from a branch is that a second
    stem runs vertically for metres while holding a radius comparable to the main
    one, which is what `is_stem_like` tests.
    """
    import pandas as pd

    z_top = min(float(points[:, 2].max()), p.z_stop)
    live: list[list[dict]] = []
    finished: list[list[dict]] = []
    rows: list[dict] = []
    band_now: list[tuple[float, list]] = []

    for zc in np.arange(p.z_start, z_top, p.step):
        comps = band_components(points, zc, p)

        used = set()
        for chain in live:
            last = next((c for c in reversed(chain) if c is not None), None)
            if last is None:  # chain is nothing but gaps
                chain.append(None)
                continue
            best, best_d = None, p.match_radius
            for i, c in enumerate(comps):
                if i in used:
                    continue
                d = float(np.hypot(c["x"] - last["x"], c["y"] - last["y"]))
                if d < best_d and d <= p.max_drift + last["r"]:
                    best, best_d = i, d
            if best is None:
                chain.append(None)  # a gap; tolerated briefly below
            else:
                used.add(best)
                chain.append(comps[best])

        for i, c in enumerate(comps):  # unmatched components start new chains
            if i not in used:
                live.append([c])

        still: list[list[dict]] = []
        for chain in live:
            tail = chain[-3:]
            if len(tail) == 3 and all(t is None for t in tail):
                finished.append([c for c in chain if c is not None])
            else:
                still.append(chain)
        live = still

        band_now.append((float(zc), [ch for ch in live]))

    finished.extend(live)
    all_chains = [[c for c in ch if c is not None] for ch in finished]
    all_chains = [ch for ch in all_chains if len(ch) >= 2]
    main_r = max((_chain_stats(ch)["r"] for ch in all_chains), default=0.0)
    tracks = [ch for ch in all_chains if is_stem_like(ch, main_r, p)]

    # A fork is a height at which two or more *stem-like* chains are both present.
    for zc, chains in band_now:
        alive = [ch for ch in chains
                 if is_stem_like([c for c in ch if c is not None], main_r, p)]
        if len(alive) >= 2:
            radii = sorted(
                (next((c["r"] for c in reversed(ch) if c is not None), 0.0) for ch in alive),
                reverse=True)
            rows.append({"z": float(zc), "n_stems": len(alive), "radii": radii,
                         "largest_r": radii[0] if radii else float("nan")})

    return tracks, pd.DataFrame(rows)
