# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Per-tree metrics, and matching the same tree across two sensors.

The Day 4 objective is a table with **stem volume measured from the ground** beside
**metrics measured from the air**, one row per tree. That requires three things:
metrics that ALS can actually produce, metrics that TLS or MLS can produce, and an
honest way to decide that an airborne crown and a terrestrial stem are the same
tree.

On the matching, two points worth stating before the numbers are used.

**Position means different things to each sensor.** A terrestrial scan locates a
tree by its stem base. An airborne scan locates it by its canopy maximum, which sits
wherever the crown is tallest, not above the stem. Leaning trees and asymmetric
crowns separate the two by metres, and that offset is a real property of the
measurement, not noise to be tuned away. `match_positions` reports the offsets so
they can be looked at rather than assumed small.

**A greedy one-to-one match is a choice.** Where crowns are dense, several
terrestrial stems compete for one airborne crown, and any assignment is partly
arbitrary. Unmatched trees on both sides are returned, because how many failed to
match is usually more informative than the mean error of those that did.
"""

from __future__ import annotations

import numpy as np

from dataclasses import dataclass

from .dataset import xyz as _xyz

__all__ = [
    "PlotGeometry",
    "infer_plot_geometry",
    "flag_edge_trees",
    "tree_metrics",
    "als_metrics",
    "match_positions",
    "join_sensors",
]


def _hull_area(points_2d: np.ndarray) -> float:
    if len(points_2d) < 3:
        return float("nan")
    try:
        from scipy.spatial import ConvexHull

        return float(ConvexHull(points_2d).volume)  # 2D hull "volume" is the area
    except Exception:
        return float("nan")


def _hull_volume(points_3d: np.ndarray) -> float:
    if len(points_3d) < 4:
        return float("nan")
    try:
        from scipy.spatial import ConvexHull

        return float(ConvexHull(points_3d).volume)
    except Exception:
        return float("nan")


def tree_metrics(cloud, labels: np.ndarray, ground_z: float = 0.30, crown_frac: float = 0.5):
    """Per-tree structural metrics from any sensor. Returns a DataFrame.

    Heights use the 99th percentile as well as the maximum: a single high return,
    from a bird or a noise point, moves the maximum and not the percentile, and the
    gap between them is a useful outlier flag in itself.

    Crown metrics are taken above `crown_frac` of the tree's height, which is a
    convention rather than a measurement of where the crown starts. `crown_base` in
    `novatrees.extract` measures that properly when stem points exist.
    """
    import pandas as pd

    P = _xyz(cloud)
    rows = []
    for k in range(int(labels.max()) + 1):
        m = labels == k
        n = int(m.sum())
        if n < 10:
            continue
        p = P[m]
        z = p[:, 2]
        h = float(np.percentile(z, 99))
        crown = p[z >= crown_frac * h]
        rows.append(
            {
                "treeID": k + 1,
                "x": float(np.median(p[:, 0])),
                "y": float(np.median(p[:, 1])),
                "n_points": n,
                "h_max": float(z.max()),
                "h_p99": h,
                "h_mean": float(z.mean()),
                "h_std": float(z.std()),
                "h_p25": float(np.percentile(z, 25)),
                "h_p50": float(np.percentile(z, 50)),
                "h_p75": float(np.percentile(z, 75)),
                "h_p95": float(np.percentile(z, 95)),
                "crown_area_m2": _hull_area(crown[:, :2]) if len(crown) >= 3 else float("nan"),
                "crown_volume_m3": _hull_volume(crown) if len(crown) >= 4 else float("nan"),
                "crown_base_m": float(z.min()) if n else float("nan"),
                "frac_above_mean": float((z > z.mean()).sum() / n),
            }
        )
    return pd.DataFrame(rows)


def als_metrics(cloud, labels: np.ndarray, ground_z: float = 0.50, crown_frac: float = 0.5):
    """Airborne metrics per tree, with the position taken at the canopy maximum.

    The position difference from `tree_metrics` is deliberate. An airborne crown is
    located where it is tallest, which is what an ALS-based inventory actually
    measures and what a terrestrial stem base has to be matched against.
    """
    import pandas as pd

    df = tree_metrics(cloud, labels, ground_z=ground_z, crown_frac=crown_frac)
    if df.empty:
        return df

    P = _xyz(cloud)
    apex = []
    for k in df.treeID.to_numpy() - 1:
        p = P[labels == k]
        top = p[np.argmax(p[:, 2])]
        apex.append((float(top[0]), float(top[1])))
    df = df.copy()
    df["apex_x"] = [a[0] for a in apex]
    df["apex_y"] = [a[1] for a in apex]
    # match on the apex: it is where an airborne detector says the tree is
    df["x"], df["y"] = df.apex_x, df.apex_y
    return df


def match_positions(a_xy: np.ndarray, b_xy: np.ndarray, max_distance: float = 3.0):
    """Greedy one-to-one nearest matching between two sets of tree positions.

    Returns (pairs, unmatched_a, unmatched_b) where pairs is a DataFrame with the
    two indices and their separation. Closest pairs are taken first, so a confident
    match is never displaced by a marginal one competing for the same tree.

    `max_distance` is the judgement call. Too tight and leaning trees are lost; too
    loose and neighbours get swapped in dense stands. Report the distance
    distribution before settling on a value.
    """
    import pandas as pd
    from scipy.spatial import cKDTree

    a_xy = np.asarray(a_xy, float)[:, :2]
    b_xy = np.asarray(b_xy, float)[:, :2]
    if len(a_xy) == 0 or len(b_xy) == 0:
        return pd.DataFrame(columns=["a", "b", "distance"]), list(range(len(a_xy))), list(range(len(b_xy)))

    tree = cKDTree(b_xy)
    cand = []
    for i, pt in enumerate(a_xy):
        for d, j in zip(*tree.query(pt, k=min(5, len(b_xy)))) if len(b_xy) > 1 else [
            (float(tree.query(pt)[0]), int(tree.query(pt)[1]))
        ]:
            if np.isfinite(d) and d <= max_distance:
                cand.append((float(d), i, int(j)))

    cand.sort()
    used_a, used_b, pairs = set(), set(), []
    for d, i, j in cand:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        pairs.append({"a": i, "b": j, "distance": d})

    return (
        pd.DataFrame(pairs),
        [i for i in range(len(a_xy)) if i not in used_a],
        [j for j in range(len(b_xy)) if j not in used_b],
    )


def join_sensors(ground_df, air_df, max_distance: float = 3.0, suffixes=("_ground", "_air")):
    """Join terrestrial and airborne tables into one row per matched tree.

    `ground_df` should carry stem volume and DBH; `air_df` the airborne metrics.
    Both need `x` and `y`. Unmatched trees from either side are dropped from the
    join and counted in `.attrs`, which is where to look before trusting any
    regression fitted on the result.
    """
    import pandas as pd

    pairs, un_g, un_a = match_positions(
        ground_df[["x", "y"]].to_numpy(), air_df[["x", "y"]].to_numpy(), max_distance
    )
    if pairs.empty:
        out = pd.DataFrame()
        out.attrs.update(n_ground=len(ground_df), n_air=len(air_df), n_matched=0,
                         unmatched_ground=len(un_g), unmatched_air=len(un_a))
        return out

    g = ground_df.iloc[pairs.a.to_numpy()].reset_index(drop=True).add_suffix(suffixes[0])
    a = air_df.iloc[pairs.b.to_numpy()].reset_index(drop=True).add_suffix(suffixes[1])
    out = pd.concat([g, a, pairs.distance.reset_index(drop=True)], axis=1)
    out.attrs.update(
        n_ground=len(ground_df), n_air=len(air_df), n_matched=len(out),
        unmatched_ground=len(un_g), unmatched_air=len(un_a),
        match_rate_ground=len(out) / max(len(ground_df), 1),
        match_rate_air=len(out) / max(len(air_df), 1),
        median_offset=float(pairs.distance.median()),
    )
    return out


# --------------------------------------------------------------------------- #
# Circular plots
# --------------------------------------------------------------------------- #


@dataclass
class PlotGeometry:
    """A circular sample plot: where it is and how far it reaches."""

    x: float
    y: float
    radius: float

    def distance_to_edge(self, px, py):
        return self.radius - np.hypot(np.asarray(px) - self.x, np.asarray(py) - self.y)


def infer_plot_geometry(cloud) -> PlotGeometry:
    """Recover the centre and radius of a cookie-cut circular plot from the points."""
    P = _xyz(cloud)
    cx = float((P[:, 0].min() + P[:, 0].max()) / 2)
    cy = float((P[:, 1].min() + P[:, 1].max()) / 2)
    r = float(np.hypot(P[:, 0] - cx, P[:, 1] - cy).max())
    return PlotGeometry(cx, cy, r)


def flag_edge_trees(df, plot: PlotGeometry, buffer: float = 2.0):
    """Add `dist_to_edge` and `edge_tree` to a per-tree table.

    A circular cookie cutter slices through whatever crowns and stems happen to
    straddle the boundary, so a tree near the edge is measured from a fraction of
    itself. Its stem volume and crown area are biased low by an amount nobody can
    recover, because the missing part was never scanned.

    This does not correct anything, which would require assuming a shape. It marks
    the affected trees so they can be excluded from a fit, or kept deliberately.
    `buffer` should be roughly a crown radius: 2 m is conservative for a boreal
    plot, and too small for anything with a broad crown.
    """
    out = df.copy()
    out["dist_to_edge"] = plot.distance_to_edge(out.x.to_numpy(), out.y.to_numpy())
    out["edge_tree"] = out.dist_to_edge < buffer
    return out
