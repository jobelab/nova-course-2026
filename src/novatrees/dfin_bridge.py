# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Bridge to 3DFin and dendromatics, run as a third detection method.

[3DFin](https://github.com/3DFin/3DFin) is third-party forest inventory software and
[dendromatics](https://github.com/3DFin/dendromatics) is its algorithmic core. This
module drives dendromatics directly, in the same order 3DFin's own
`abstract_processing.py` does, so the comparison is against the shipped pipeline
rather than against a reinterpretation of it.

It answers a question `pcf_bridge` cannot. `pcf` is airborne and top-down; this is
terrestrial and bottom-up, so it is the closest independent implementation of what
`novatrees` does, and where they disagree the disagreement is informative.

**The idea already borrowed from it.** dendromatics tracks the stem axis section by
section rather than assuming one direction, and it checks sector occupancy before
trusting a circle. Both were reimplemented here before this bridge existed, in
`extract.track_stem_axis` and `stemgeom`. Running the original is how that
reimplementation gets checked.

The five steps, from 3DFin's processing module:

1. cut a stripe at breast height and cluster it by verticality, keeping stems
2. `individualize_trees`: PCA axis per cluster, then assign every point to an axis
3. re-cluster the assigned points near each axis into curated stems
4. `compute_sections`: fit a circle every `section_len` up each stem
5. `tilt_detection` to flag bad circles, then `tree_locator` for DBH and position

**It needs raw elevation in Z and normalised height in Z0, in the same array.**
Passing the normalised height as both makes `compute_axes_approximate` fail with
`need at least one array to concatenate`, because no cluster produces a valid axis.
`prepare` builds the four-column input correctly.

dendromatics is an **optional** dependency and is deliberately not in
`pyproject.toml`: it pulls in its own CSF build and a compiled core. Everything here
degrades to `available() -> False` when it is absent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .dataset import xyz as _xyz

__all__ = [
    "DfinParams",
    "DfinResult",
    "available",
    "prepare",
    "run_dendromatics",
    "section_volumes",
]


@dataclass
class DfinParams:
    """3DFin's shipped defaults, with the deviations marked.

    Everything here is `3DFinconfig.ini` unless the comment says otherwise. Keeping
    them at 3DFin's values is the point: a comparison against a heavily retuned
    version of someone else's software says nothing about either.
    """

    # basic
    lower_limit: float = 0.7  # stripe bottom, m above ground
    upper_limit: float = 3.5  # stripe top
    n_iterations: int = 2

    # verticality clustering
    vert_scale: float = 0.1
    vert_threshold: float = 0.7
    # 3DFin ships 1000. That is a hard floor on cluster size and it starves on a plot
    # this size: 22 clusters against 41 reference trees. 200 gives 45, which is the
    # closest of everything tried. Raise it back to 1000 for a plot-scale multi-scan
    # survey, which is what 3DFin was built for.
    n_points: int = 200
    res_xy_stripe: float = 0.02
    res_z_stripe: float = 0.02

    # individualisation
    res_xy: float = 0.035
    res_z: float = 0.035
    height_range: float = 0.7
    maximum_d: float = 15.0  # -> d_max, see the note in run_dendromatics
    minimum_points: int = 20
    distance_to_axis: float = 1.5  # -> d
    maximum_dev: float = 25.0
    res_heights: float = 0.3
    n_digits: int = 5

    # sections
    stem_search_diameter: float = 2.0
    minimum_height: float = 0.3
    maximum_height: float = 25.0
    section_len: float = 0.2
    section_wid: float = 0.05
    diameter_proportion: float = 0.5
    point_threshold: int = 5
    minimum_diameter: float = 0.06
    maximum_diameter: float = 1.0
    point_distance: float = 0.02
    number_points_section: int = 80
    number_sectors: int = 16
    m_number_sectors: int = 9
    circle_width: float = 0.02


@dataclass
class DfinResult:
    trees: object  # DataFrame: treeID, x, y, dbh_m, height_m, tilt_deg, sections_ok
    labels: np.ndarray  # instance id per input point, -1 unassigned
    sections: object  # DataFrame: one fitted circle per tree per height
    stats: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)


def available() -> bool:
    """True when dendromatics can be imported."""
    try:
        import dendromatics  # noqa: F401

        return True
    except Exception:
        return False


def prepare(cloud, ground: np.ndarray | None = None, cell: float = 0.5,
            quantile: float = 0.25) -> np.ndarray:
    """Build the `[x, y, raw z, normalised z]` array dendromatics expects.

    `cloud` carries raw elevations. With `ground` given, that mask is used; otherwise
    CSF classifies the ground here. Normalisation is ours rather than dendromatics'
    own, deliberately: holding the height model fixed means a difference in the result
    is a difference in stem detection, not in how the terrain was removed.
    """
    from .csf import csf_ground, normalize_heights

    P = _xyz(cloud)
    g = csf_ground(P) if ground is None else np.asarray(ground, bool)
    z0 = _xyz(normalize_heights(cloud, g, cell=cell, quantile=quantile))[:, 2]
    return np.column_stack([P[:, 0], P[:, 1], P[:, 2], z0])


def run_dendromatics(coords: np.ndarray, p: DfinParams | None = None,
                     verbose: bool = True) -> DfinResult:
    """Run the dendromatics stem pipeline. `coords` is `prepare()`'s output.

    Returns per-tree measurements, per-point instance labels aligned to `coords`, and
    every fitted section, so the result drops straight into `novatrees.evaluate` and
    `novatrees.inventory` beside our own.
    """
    import dendromatics as dm
    import pandas as pd

    p = p or DfinParams()
    log = print if verbose else (lambda *a, **k: None)
    t: dict[str, float] = {}

    # 1. Stripe at breast height, clustered by verticality. What survives is stems.
    t0 = time.time()
    stripe = coords[(coords[:, 3] > p.lower_limit) & (coords[:, 3] < p.upper_limit), 0:4]
    clust_stripe = dm.verticality_clustering(
        stripe, p.vert_scale, p.vert_threshold, p.n_points, p.n_iterations,
        p.res_xy_stripe, p.res_z_stripe, p.n_digits,
    )
    t["stripe"] = time.time() - t0
    n_clusters = int(len(np.unique(clust_stripe[:, -1]))) if len(clust_stripe) else 0
    log(f"[3DFin] stripe {len(stripe):,} pts -> {n_clusters} stem clusters "
        f"in {t['stripe']:.1f}s")
    if not len(clust_stripe):
        raise RuntimeError("verticality clustering found no stems; lower n_points")

    # 2. An axis per cluster, then every point in the cloud assigned to its nearest.
    #    Argument order follows 3DFin's own call: its `maximum_d` (15) lands in
    #    `d_max` and its `distance_to_axis` (1.5) in `d`, which is the reverse of what
    #    the dendromatics docstring describes for those two names. The shipped
    #    pipeline is the authority here, since matching it is the entire point.
    t0 = time.time()
    assigned, tree_vector, tree_heights = dm.individualize_trees(
        coords, clust_stripe, p.res_z, p.res_xy, p.lower_limit, p.upper_limit,
        p.height_range, p.maximum_d, p.minimum_points, p.distance_to_axis,
        p.maximum_dev, p.res_heights, p.n_digits,
    )
    t["individualize"] = time.time() - t0
    log(f"[3DFin] {len(tree_vector)} trees individualized in {t['individualize']:.1f}s")

    # 3. Curate the stems: points close to an axis, inside the section height band.
    t0 = time.time()
    near = assigned[
        (assigned[:, 5] < p.stem_search_diameter / 2.0)
        & (assigned[:, 3] > p.minimum_height)
        & (assigned[:, 3] < p.maximum_height + p.section_wid), :
    ]
    stems = dm.verticality_clustering(
        near, p.vert_scale, p.vert_threshold, p.n_points, p.n_iterations,
        p.res_xy_stripe, p.res_z_stripe, p.n_digits,
    )[:, 0:6]
    t["curate"] = time.time() - t0

    # 4. A circle every section_len up each stem, and 5. outliers, DBH, position.
    t0 = time.time()
    heights = np.arange(p.minimum_height, p.maximum_height, p.section_len)
    X_c, Y_c, R, check_circle, _, sector_perct, n_points_in = dm.compute_sections(
        stems, heights, p.section_wid, p.diameter_proportion, p.point_threshold,
        p.minimum_diameter / 2.0, p.maximum_diameter / 2.0, p.point_distance,
        p.number_points_section, p.number_sectors, p.m_number_sectors, p.circle_width,
    )
    old = np.seterr(divide="ignore", invalid="ignore")
    outliers = dm.tilt_detection(X_c, Y_c, R, heights, w_1=3, w_2=1)
    np.seterr(**old)
    dbh_values, tree_locations = dm.tree_locator(
        heights, X_c, Y_c, tree_vector, sector_perct, R, outliers,
    )
    t["sections"] = time.time() - t0
    log(f"[3DFin] {len(heights)} sections per stem fitted in {t['sections']:.1f}s")

    # Per-point labels, aligned back to the input order. `individualize_trees` may
    # reorder or drop points, so map by coordinate rather than assuming row order.
    labels = np.full(len(coords), -1, np.int32)
    if len(assigned):
        from scipy.spatial import cKDTree

        _, idx = cKDTree(assigned[:, :3]).query(coords[:, :3], k=1,
                                                distance_upper_bound=1e-6)
        hit = idx < len(assigned)
        labels[hit] = assigned[idx[hit], 4].astype(np.int32) - 1  # 1-based -> 0-based

    dbh = np.asarray(dbh_values, float).ravel()
    dbh[dbh <= 0] = np.nan  # tree_locator returns 0 when no section was usable
    loc = np.asarray(tree_locations, float).reshape(len(dbh), -1)
    hts = np.asarray(tree_heights, float)

    # A usable circle, taken from the condition inside `fit_circle_check` itself
    # rather than from the returned flag. `check_circle` is a review counter, not a
    # quality score: 0 means it passed first time, 1 that it was refitted, 2 that the
    # section held too few points to try. Treating >0 as good accepts every empty
    # section and fills the taper with zero radii.
    #
    # Note `n_points_in` is an upper bound, not a minimum. It counts points inside the
    # inner circle, and a stem cross-section should be nearly hollow, so a full one is
    # a fit that has wrapped around foliage rather than bark.
    R_arr = np.asarray(R, float)
    occupancy_ok = np.asarray(sector_perct, float) >= 100.0 * p.m_number_sectors / p.number_sectors
    ok = (
        (R_arr >= p.minimum_diameter / 2.0)
        & (R_arr <= p.maximum_diameter / 2.0)
        & (np.asarray(n_points_in, float) <= p.point_threshold)
        & occupancy_ok
        & (~np.asarray(outliers, bool))
    )
    trees = pd.DataFrame({
        "treeID": np.arange(1, len(dbh) + 1),
        "x": loc[:, 0], "y": loc[:, 1],
        "dbh_m": dbh,
        "height_m": hts[:len(dbh), 3] if hts.ndim == 2 and hts.shape[1] > 3 else np.nan,
        "tilt_deg": (np.asarray(tree_vector, float)[:len(dbh), 8]
                     if np.asarray(tree_vector).shape[1] > 8 else np.nan),
        "sections_ok": ok[:len(dbh)].sum(axis=1) if ok.ndim == 2 else np.nan,
        "review": np.asarray(check_circle, float)[:len(dbh)].mean(axis=1),
        "height_valid": (hts[:len(dbh), 4] > 0) if hts.ndim == 2 and hts.shape[1] > 4 else True,
    })

    n_tree, n_sec = np.asarray(R).shape
    sections = pd.DataFrame({
        "treeID": np.repeat(np.arange(1, n_tree + 1), n_sec),
        "z": np.tile(heights[:n_sec], n_tree),
        "x_c": np.asarray(X_c).ravel(), "y_c": np.asarray(Y_c).ravel(),
        "radius_m": np.asarray(R).ravel(),
        "occupancy": np.asarray(sector_perct).ravel() / 100.0,
        "n_points": np.asarray(n_points_in).ravel(),
        "ok": np.asarray(ok).ravel() if ok.ndim == 2 else False,
        "review": np.asarray(check_circle, float).ravel(),
    })

    stats = {
        "n_points": int(len(coords)),
        "n_clusters": n_clusters,
        "n_trees": int(len(trees)),
        "n_assigned": int((labels >= 0).sum()),
        "n_sections_ok": int(sections.ok.sum()),
        "total_s": float(sum(t.values())),
    }
    log(f"[3DFin] {stats['n_trees']} trees, "
        f"median DBH {np.nanmedian(dbh):.3f} m, in {stats['total_s']:.1f}s")
    return DfinResult(trees, labels, sections, stats, t)


def section_volumes(sections, trees, min_sections: int = 4):
    """Stem volume from the dendromatics sections, with the cover it spans.

    Deliberately the same shape as `taper.volume_variants`' measured columns:
    integrate pi r^2 over the accepted sections only, and report how much of the tree
    that covers, so the two reconstructions are compared on the same terms rather than
    one being quietly credited with a stem it never measured.
    """
    import pandas as pd

    rows = []
    heights = dict(zip(trees.treeID, trees.height_m))
    for tid, g in sections[sections.ok].groupby("treeID"):
        g = g.sort_values("z")
        if len(g) < min_sections:
            continue
        z, r = g.z.to_numpy(), g.radius_m.to_numpy()
        h = float(heights.get(tid, np.nan))
        v = float(np.trapezoid(np.pi * r**2, z))
        d13 = float(np.interp(1.3, z, 2 * r)) if z.min() <= 1.3 <= z.max() else float("nan")
        cyl = np.pi * (d13 / 2) ** 2 * h if np.isfinite(d13) and h > 0 else float("nan")
        rows.append({
            "treeID": tid, "height_m": h, "dbh_m": d13,
            "vol_measured_m3": v, "n_sections": int(len(g)),
            "cover": (z.max() - z.min()) / h if h > 0 else float("nan"),
            "ff_measured": v / cyl if cyl and np.isfinite(cyl) else float("nan"),
        })
    return pd.DataFrame(rows)
