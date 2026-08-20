# NOVA course 2026 — point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Per-tree extraction: semantic class + instance id, and one file per tree.

Instance labels alone answer *which tree*. To pull a single tree out of a mixed
stand you also need *which part* — the ground beneath it is not part of it, and
stem and foliage are usually wanted apart. Together those two labellings are a
panoptic result:

    semantic  0 ground   1 stem   2 foliage      (a fixed vocabulary)
    instance  1 .. K, 0 = unassigned             (discovered, one per tree)

Ground is deliberately *not* assigned to a tree. It carries no instance id, which
is the honest answer — a patch of forest floor does not belong to the tree above
it in any measurable sense, and pretending otherwise inflates every per-tree
statistic computed downstream.

The stem/foliage split here is geometric: a point is stem if it sits within the
fitted stem radius (plus slack) of its own tree's vertical axis, below the crown
base. That works for straight boreal stems and is trivially explainable. For a
learned alternative see `novatrees.treeaibox.stem_classification`, which uses
TreeAIBox's trained stem classifier — better on leaning or forked stems, at the
cost of a model download and about a minute of CPU per million points.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from .dataset import as_dataset
from .dataset import xyz as _xyz

__all__ = ["GROUND", "STEM", "FOLIAGE", "semantic_labels", "tree_table", "extract_trees"]

GROUND, STEM, FOLIAGE = 0, 1, 2
_CLASS_NAMES = {GROUND: "ground", STEM: "stem", FOLIAGE: "foliage"}


def semantic_labels(
    cloud,
    tree_labels: np.ndarray,
    seeds: np.ndarray,
    ground_mask: np.ndarray | None = None,
    ground_z: float = 0.30,
    radius_slack: float = 0.10,
    crown_base: float | None = None,
) -> np.ndarray:
    """Classify every point as ground, stem or foliage.

    `seeds` is the (n_trees, 3) x/y/dbh array from `detect_seeds`; each tree's
    stem is modelled as a vertical cylinder of that diameter through its seed.
    `crown_base` caps the stem in height; None means no cap.
    """
    xyz = _xyz(cloud)
    out = np.full(len(xyz), FOLIAGE, np.int8)

    ground = ground_mask if ground_mask is not None else (xyz[:, 2] <= ground_z)
    out[ground] = GROUND

    labelled = (tree_labels >= 0) & ~ground
    idx = np.flatnonzero(labelled)
    if len(idx) == 0 or len(seeds) == 0:
        return out

    t = tree_labels[idx]
    valid = t < len(seeds)
    idx, t = idx[valid], t[valid]

    centre = seeds[t, :2]
    radius = seeds[t, 2] / 2.0 + radius_slack
    d = np.linalg.norm(xyz[idx, :2] - centre, axis=1)
    is_stem = d <= radius
    if crown_base is not None:
        is_stem &= xyz[idx, 2] <= crown_base

    out[idx[is_stem]] = STEM
    return out


def tree_table(cloud, tree_labels: np.ndarray, seeds: np.ndarray, semantic: np.ndarray | None = None):
    """One row per tree: point counts, height, DBH, position."""
    import pandas as pd

    xyz = _xyz(cloud)
    rows = []
    for k in range(len(seeds)):
        m = tree_labels == k
        n = int(m.sum())
        if n == 0:
            continue
        z = xyz[m, 2]
        row = {
            "treeID": k + 1,
            "x": float(seeds[k, 0]),
            "y": float(seeds[k, 1]),
            "dbh_m": float(seeds[k, 2]),
            "height_m": float(z.max()),
            "points": n,
        }
        if semantic is not None:
            row["stem_points"] = int((semantic[m] == STEM).sum())
            row["foliage_points"] = int((semantic[m] == FOLIAGE).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def extract_trees(
    cloud,
    tree_labels: np.ndarray,
    outdir: str | Path,
    source: str | Path | None = None,
    semantic: np.ndarray | None = None,
    min_points: int = 1000,
    include_ground: bool = False,
    prefix: str = "tree",
) -> list[Path]:
    """Write one LAZ per tree. Returns the paths written.

    Ground is excluded unless `include_ground`, in which case the ground points
    lying within the tree's XY footprint are appended and keep semantic class 0 —
    useful for per-tree DTM checks, misleading for per-tree volume.
    """
    import laspy

    ds = as_dataset(cloud)
    src = source or ds.attrs.get("source")
    if src is None:
        raise ValueError("no source header available; pass source=")

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    full = laspy.read(str(src))
    if len(full.points) != len(tree_labels):
        raise ValueError(f"labels ({len(tree_labels)}) do not match points ({len(full.points)})")

    xyz = _xyz(ds)
    written = []
    for k in range(int(tree_labels.max()) + 1):
        m = tree_labels == k
        if m.sum() < min_points:
            continue

        if include_ground and semantic is not None:
            g = semantic == GROUND
            if g.any():
                p = xyz[m]
                lo, hi = p[:, :2].min(0), p[:, :2].max(0)
                inside = (
                    g
                    & (xyz[:, 0] >= lo[0]) & (xyz[:, 0] <= hi[0])
                    & (xyz[:, 1] >= lo[1]) & (xyz[:, 1] <= hi[1])
                )
                m = m | inside

        sub = laspy.LasData(full.header)
        sub.points = full.points[m].copy()
        if semantic is not None and "classification" in sub.point_format.dimension_names:
            # LAS reserves 2 for ground; 4/5 are medium/high vegetation.
            las_class = np.where(
                semantic[m] == GROUND, 2, np.where(semantic[m] == STEM, 5, 4)
            ).astype(np.uint8)
            sub.classification = las_class

        path = outdir / f"{prefix}_{k + 1:03d}.laz"
        sub.write(str(path))
        written.append(path)

    return written


def attach_labels(cloud, tree_labels: np.ndarray, semantic: np.ndarray | None = None) -> xr.Dataset:
    """Return the Dataset with `treeID` (1-based, 0 = unassigned) and `semantic` attached."""
    ds = as_dataset(cloud).copy()
    ds["treeID"] = ("point", (tree_labels + 1).astype(np.int32))
    ds["treeID"].attrs.update(description="instance id, 0 = unassigned")
    if semantic is not None:
        ds["semantic"] = ("point", semantic.astype(np.int8))
        ds["semantic"].attrs.update(
            description="0 ground, 1 stem, 2 foliage",
            classes=", ".join(f"{k}={v}" for k, v in _CLASS_NAMES.items()),
        )
    return ds
