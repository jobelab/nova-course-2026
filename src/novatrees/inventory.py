# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
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
    "drop_fragments",
    "match_by_crown",
    "crown_occupancy",
    "average_occupancy",
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


def drop_fragments(df, min_points: int = 5000, min_height: float = 5.0,
                   min_crown_area: float = 5.0, drop_edge: bool = True):
    """Remove the region-growing debris from an ALS tree table.

    Watershed seeding on a CHM produces more objects than there are trees. Some are
    real suppressed trees, but many are slivers: a handful of returns caught between
    two crowns, or the rim of a crown cut off by its neighbour's basin. On the Day 4
    ALS, 92 objects came out of 5.6 million points, and 26 of them held fewer points
    than a single real crown's outer branch.

    They matter because they are *positions*, and position is what the ALS-to-ground
    matching uses. A sliver sitting near a real stem wins the nearest-neighbour
    match and brings a nonsense height with it. Removing them took the matched
    height RMSE from 10.88 m to 2.09 m, which is the difference between a table that
    means something and one that does not.

    The three thresholds are deliberately loose, and the result is not sensitive to
    them: every combination from 5,000 to 30,000 points, 5 to 15 m and 5 to 20 m2
    returns the same twelve matched trees on this plot. They are there to cut debris,
    not to select trees.
    """
    out = df
    if drop_edge and "edge_tree" in out:
        out = out[~out.edge_tree]
    for col, lo in (("n_points", min_points), ("h_max", min_height),
                    ("crown_area_m2", min_crown_area)):
        if col in out:
            out = out[out[col] >= lo]
    return out.copy()


def match_by_crown(ground_df, air_df, rank: str = "height_m",
                   crown_area_col: str = "crown_area_m2", scale: float = 1.0,
                   max_height_diff: float | None = 4.0,
                   air_height_col: str = "h_max", suffixes=("_ground", "_air")):
    """Give each airborne crown to the dominant stem beneath it.

    Nearest-neighbour matching asks *which stem is closest to this apex*, which is the
    wrong question. An airborne crown is the top of **one** tree, the one that reached
    the light there, and every other stem under that crown is a tree the helicopter
    could not see. Those are not matching failures; they are omissions, and they are
    the physical reason an airborne inventory undercounts a layered stand.

    So: take each crown's footprint, collect every ground stem standing inside it, and
    give the crown to the dominant one, ranked by `rank` (tree height by default,
    which is the closest available stand-in for "the one that reached the light").
    The rest are recorded as **suppressed**, with the crown they sit under.

    The footprint is a circle of radius `sqrt(area / pi) * scale` about the apex,
    because the ALS table stores crown area and apex rather than a polygon. That is a
    real approximation: a crown is not round and its apex is not its centre, so
    `scale` is provided to widen or narrow it, and the counts below should be read as
    sensitive to it.

    `max_height_diff` guards the rule against its own failure mode. "Tallest stem
    inside the footprint" gives the crown to whatever is there, even when that is a
    6 m sapling standing under a 25 m canopy whose real owner was never detected from
    the ground. A crown and its stem should agree on height to within roughly the
    matched height RMSE, so a stem further than this from the crown's own `h_max` does
    not own it, and the crown is left empty instead.

    Returns the joined frame, with `.attrs` carrying:

    - `n_suppressed`: stems under a crown that lost to a taller neighbour
    - `n_ground_outside`: stems under no crown at all, which is a **detection** failure
      by the airborne method rather than an occlusion one
    - `n_air_empty`: crowns with no stem beneath them, either outside the ground
      coverage or a segmentation artefact
    - `suppressed`: the frame of losing stems, so omission can be studied rather than
      silently dropped
    """
    import numpy as np
    import pandas as pd

    g = ground_df.reset_index(drop=True)
    a = air_df.reset_index(drop=True)
    if not len(g) or not len(a):
        out = pd.DataFrame()
        out.attrs.update(n_ground=len(g), n_air=len(a), n_matched=0)
        return out

    radius = np.sqrt(np.asarray(a[crown_area_col], float) / np.pi) * scale
    gx, gy = g.x.to_numpy(float), g.y.to_numpy(float)
    ranker = (g[rank].to_numpy(float) if rank in g
              else np.zeros(len(g)))  # no ranking column: first stem wins

    owner = {}          # air index -> ground index
    under = {}          # air index -> [ground indices]
    for j in range(len(a)):
        d = np.hypot(gx - float(a.x[j]), gy - float(a.y[j]))
        inside = np.flatnonzero(d <= radius[j])
        if not len(inside):
            continue
        under[j] = inside.tolist()
        # Dominant stem: tallest inside the footprint. Ties go to the closer one.
        order = inside[np.lexsort((d[inside], -ranker[inside]))]
        if max_height_diff is not None and air_height_col in a and rank in g:
            # The owner has to be a plausible owner. Walk down from the tallest and
            # take the first stem whose height matches the crown's.
            h_air = float(a[air_height_col][j])
            order = [k for k in order
                     if abs(float(g[rank][k]) - h_air) <= max_height_diff]
        if not len(order):
            continue
        owner[j] = int(order[0])

    # One stem cannot own two crowns. Where it does, keep the crown whose apex is
    # nearer, and free the other to its next-tallest stem.
    taken: dict[int, int] = {}
    for j, gi in sorted(owner.items()):
        if gi not in taken:
            taken[gi] = j
            continue
        rival = taken[gi]
        d_new = np.hypot(gx[gi] - float(a.x[j]), gy[gi] - float(a.y[j]))
        d_old = np.hypot(gx[gi] - float(a.x[rival]), gy[gi] - float(a.y[rival]))
        loser = j if d_new >= d_old else rival
        if d_new < d_old:
            taken[gi] = j
        others = [k for k in under[loser] if k not in taken.values() and k != gi]
        owner[loser] = (others[np.argmax(ranker[others])] if others else -1)

    pairs = [(gi, j) for j, gi in owner.items() if gi >= 0]
    if not pairs:
        out = pd.DataFrame()
        out.attrs.update(n_ground=len(g), n_air=len(a), n_matched=0)
        return out

    gi = [p[0] for p in pairs]
    ai = [p[1] for p in pairs]
    dist = [float(np.hypot(gx[p[0]] - float(a.x[p[1]]), gy[p[0]] - float(a.y[p[1]])))
            for p in pairs]
    out = pd.concat(
        [g.iloc[gi].reset_index(drop=True).add_suffix(suffixes[0]),
         a.iloc[ai].reset_index(drop=True).add_suffix(suffixes[1]),
         pd.Series(dist, name="distance")], axis=1)

    matched_ground = set(gi)
    covered = {k for v in under.values() for k in v}
    suppressed_idx = sorted(covered - matched_ground)
    sup = g.iloc[suppressed_idx].copy()
    if len(sup):
        sup["under_air_tree"] = [
            int(a.treeID[j]) if "treeID" in a else j
            for k in suppressed_idx
            for j in [next(jj for jj, v in under.items() if k in v)]
        ]

    out.attrs.update(
        n_ground=len(g), n_air=len(a), n_matched=len(out),
        n_suppressed=len(suppressed_idx),
        n_ground_outside=int(len(g) - len(covered)),
        n_air_empty=int(len(a) - len(under)),
        median_offset=float(np.median(dist)),
        crown_scale=scale, rank=rank, max_height_diff=max_height_diff,
        suppressed=sup,
    )
    return out


def crown_occupancy(ground, air, crown_area_col: str = "crown_area_m2",
                    scale: float = 1.0, volume_col: str = "vol_model_relaxed_m3",
                    height_col: str = "height_m", exclusive: bool = True):
    """How many stems stand under each airborne crown, and what they add up to.

    A refinement of `match_by_crown` that stops trying to name the tree. Assigning a
    crown to one stem throws away every other stem beneath it, and on this plot that
    is 22 of 38. **Counting them instead keeps them.**

    The unit of analysis becomes the crown, not the tree, and the quantity to model
    becomes the volume *under* a crown rather than the volume *of* the dominant stem.
    That is the better target for upscaling, because summing it over every airborne
    crown recovers the suppressed trees too, whereas summing a dominant-stem model
    reproduces the airborne undercount by construction.

    It also sidesteps the hardest part of the matching problem. Deciding *which* stem
    owns a crown needs the stem to be detected, correctly segmented and correctly
    ranked; deciding *how many* stems are under it needs only that they were detected.

    One row per crown, with:

    - `n_stems`, and `stem_volume_sum`, the quantity worth modelling
    - `stem_volume_dominant` and `dominant_height_m`, for comparison with the
      one-crown-one-tree view
    - `suppressed_volume_share`: how much of the volume under this crown belongs to
      trees the airborne sensor cannot see. Where that is large, a dominant-stem model
      is missing most of the wood.

    Crowns with no stem beneath them keep `n_stems = 0` and are returned, because they
    are the crowns standing outside the ground coverage and dropping them silently
    would bias any per-hectare figure upward.

    **`exclusive` matters more than it looks.** Crowns overlap, so a stem can fall
    inside several footprints, and counting it in each one inflates the total: on this
    plot the naive count reached 54 stems from a set of 38. With `exclusive`, every
    stem is given to the single crown whose apex is nearest, which makes the crowns a
    partition and the sums addable. Turn it off only to ask a per-crown question that
    does not get summed.
    """
    import numpy as np
    import pandas as pd

    g = ground.reset_index(drop=True)
    a = air.reset_index(drop=True)
    radius = np.sqrt(np.asarray(a[crown_area_col], float) / np.pi) * scale
    gx, gy = g.x.to_numpy(float), g.y.to_numpy(float)
    vol = (g[volume_col].to_numpy(float) if volume_col in g
           else np.full(len(g), np.nan))
    hgt = (g[height_col].to_numpy(float) if height_col in g
           else np.full(len(g), np.nan))

    # Which stems fall inside which crowns, before any tie is broken.
    contains = [
        np.flatnonzero(np.hypot(gx - float(a.x[j]), gy - float(a.y[j])) <= radius[j])
        for j in range(len(a))
    ]
    if exclusive:
        # One stem, one crown: the nearest apex among the crowns that contain it.
        owner = {}
        for j, inside in enumerate(contains):
            for k in inside:
                d = float(np.hypot(gx[k] - float(a.x[j]), gy[k] - float(a.y[j])))
                if k not in owner or d < owner[k][1]:
                    owner[k] = (j, d)
        contains = [
            np.array([k for k, (jj, _) in owner.items() if jj == j], dtype=int)
            for j in range(len(a))
        ]

    rows = []
    for j in range(len(a)):
        inside = contains[j]
        v = vol[inside]
        h = hgt[inside]
        finite = np.isfinite(v)
        dom = inside[np.argmax(np.where(np.isfinite(h), h, -np.inf))] if len(inside) else None
        v_sum = float(np.nansum(v)) if finite.any() else float("nan")
        v_dom = float(vol[dom]) if dom is not None and np.isfinite(vol[dom]) else float("nan")
        rows.append({
            "treeID_air": int(a.treeID[j]) if "treeID" in a else j,
            "n_stems": int(len(inside)),
            "n_stems_with_volume": int(finite.sum()),
            "stem_volume_sum": v_sum,
            "stem_volume_dominant": v_dom,
            "dominant_height_m": float(hgt[dom]) if dom is not None else float("nan"),
            "crown_radius_m": float(radius[j]),
            "suppressed_volume_share": (
                1 - v_dom / v_sum if np.isfinite(v_dom) and np.isfinite(v_sum) and v_sum > 0
                else float("nan")
            ),
        })
    out = pd.DataFrame(rows)
    air_cols = a.add_suffix("_air") if "treeID_air" not in a else a
    out = out.merge(air_cols, on="treeID_air", how="left")
    out.attrs.update(
        n_air=len(a), n_ground=len(g), scale=scale, exclusive=exclusive,
        n_crowns_occupied=int((out.n_stems > 0).sum()),
        n_stems_covered=int(out.n_stems.sum()),
        stems_per_occupied_crown=float(out.loc[out.n_stems > 0, "n_stems"].mean())
        if (out.n_stems > 0).any() else float("nan"),
    )
    return out


def average_occupancy(tables: dict, on: str = "treeID_air"):
    """Average two or more sensors' crown occupancy tables, crown by crown.

    TLS and MLS see the same stems and disagree about how many they resolved. Neither
    is truth, so the mean of their counts is a better estimate than either, and the
    spread between them is the honest uncertainty on it. Both are returned:
    `n_stems` is the mean, `n_stems_spread` the range.
    """
    keys = list(tables)
    merged = None
    for k in keys:
        t = tables[k][[on, "n_stems", "stem_volume_sum", "stem_volume_dominant"]]
        t = t.rename(columns={c: f"{c}_{k}" for c in t.columns if c != on})
        merged = t if merged is None else merged.merge(t, on=on, how="outer")

    for col in ("n_stems", "stem_volume_sum", "stem_volume_dominant"):
        cols = [f"{col}_{k}" for k in keys]
        merged[col] = merged[cols].mean(axis=1)
        merged[f"{col}_spread"] = merged[cols].max(axis=1) - merged[cols].min(axis=1)
    base = tables[keys[0]].drop(
        columns=["n_stems", "stem_volume_sum", "stem_volume_dominant"], errors="ignore")
    return merged.merge(base, on=on, how="left")
