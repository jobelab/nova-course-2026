# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Per-tree extraction: semantic class + instance id, and one file per tree.

Instance labels alone answer *which tree*. To pull a single tree out of a mixed
stand you also need *which part* - the ground beneath it is not part of it, and
stem and foliage are usually wanted apart. Together those two labellings are a
panoptic result:

    semantic  0 ground   1 stem   2 foliage      (a fixed vocabulary)
    instance  1 .. K, 0 = unassigned             (discovered, one per tree)

Ground is deliberately *not* assigned to a tree. It carries no instance id, which
is the honest answer - a patch of forest floor does not belong to the tree above
it in any measurable sense, and pretending otherwise inflates every per-tree
statistic computed downstream.

Two ways to split stem from foliage:

**`method="tracked"` (default)** follows the stem upward and downward from the
seed, band by band, re-fitting the centre and radius as it goes. It handles lean
and mild sweep because it never assumes where the axis is - it measures it - and
it stops where the stem stops, which is what defines the crown base.

**`method="radial"`** is the older rule: a vertical cylinder of the seed's DBH
through the seed. Simple and fast, and wrong in two ways that mattered here. A
leaning stem leaves the cylinder as it rises, so the mask keeps whatever else is
near the axis instead - which is how instances came to report principal-axis
"tilts" of 60–80°, angles no standing tree has. And when a seed's circle fit is
bad (a merged instance, say) the radius is wrong for the whole height.

For a learned alternative see `novatrees.treeaibox.stem_classification`, which uses
TreeAIBox's trained stem classifier - better on forked stems, at the cost of a
model download and about a minute of CPU per million points.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xarray as xr

from .dataset import as_dataset
from .dataset import xyz as _xyz

__all__ = [
    "GROUND",
    "STEM",
    "FOLIAGE",
    "StemTrackParams",
    "semantic_labels",
    "track_stem_axis",
    "tree_table",
    "extract_trees",
]

GROUND, STEM, FOLIAGE = 0, 1, 2
_CLASS_NAMES = {GROUND: "ground", STEM: "stem", FOLIAGE: "foliage"}


@dataclass
class StemTrackParams:
    """Following a stem rather than assuming a vertical cylinder.

    Defaults were swept against the number of trees whose taper reconstructs. The
    tight ones matter: `slack = 0` and `max_growth = 1.0` together are what stop the
    track walking out along a branch. Loosening either costs reconstructed tapers
    (23 falls to 18) while the mask grows by nearly half, which is the signature of
    swallowing crown rather than following stem.
    """

    band: float = 0.30  # slab thickness used for each centre estimate (m)
    step: float = 0.25  # how far to advance between bands (m)
    search_expand: float = 1.3  # look this many radii out from the last centre
    search_min: float = 0.15  # ...but never a window tighter than this (m)
    min_points: int = 30  # below this the band is unusable
    max_shift: float = 0.15  # a centre may not jump further than this per step (m)
    radius_smooth: float = 0.7  # blend new radius with the previous one, 0..1
    min_radius: float = 0.015
    max_radius: float = 0.60
    slack: float = 0.0  # accept points this far outside the fitted radius (m)
    max_growth: float = 1.0  # a stem never widens upward by more than this ratio
    start_z: float = 1.30  # breast height: where the seed is trusted

    # Occlusion handling. A stem does not end because 40 cm of it was hidden behind
    # a neighbour, so a starved band is a gap to step over, not a stop signal. Only
    # `max_gap_bands` in a row ends the track.
    max_gap_bands: int = 2
    # A circle fitted to a narrow arc is a guess. Below this fraction of the
    # circumference the centre is still used but the radius is carried forward,
    # because the radius is what a partial arc gets wrong.
    min_occupancy: float = 0.45


def track_stem_axis(points: np.ndarray, seed: np.ndarray, p: StemTrackParams = StemTrackParams()):
    """Follow one stem from breast height outward. Returns (axis, stem mask).

    `axis` is (n_bands, 5): z, x, y, radius, sector occupancy. The mask is over
    `points`.

    Tracking runs upward and downward separately from breast height, where the
    cross-section seed is most trustworthy. Each band searches near the *previous*
    centre, so the axis can lean; `max_shift` bounds how fast, which keeps a branch
    from stealing the track. Growing wider going up is rejected outright, since
    stems taper, and that single rule removes most of what a fixed-radius cylinder
    got wrong.

    Two concessions to real scans. A band with too few points is a **gap**, not the
    end of the stem: occlusion by a neighbour or dense understory routinely hides
    half a metre. The track steps over up to `max_gap_bands` of them. And a band
    whose visible arc is narrower than `min_occupancy` keeps its centre but carries
    the previous radius forward, because a partial arc biases the radius long before
    it biases the centre.
    """
    from .stemgeom import sector_occupancy

    import circle_fit

    mask = np.zeros(len(points), bool)
    if len(points) == 0:
        return np.empty((0, 5)), mask

    z = points[:, 2]
    axis_rows = []

    for direction in (+1, -1):
        cx, cy = float(seed[0]), float(seed[1])
        r = max(float(seed[2]) / 2.0, p.min_radius)
        zc = p.start_z + (p.step if direction > 0 else 0.0)
        gaps = 0

        while z.min() - p.band <= zc <= z.max() + p.band:
            in_band = np.abs(z - zc) <= p.band / 2
            fitted = False

            if in_band.sum() >= p.min_points:
                win = max(r * p.search_expand, p.search_min)
                near = in_band & (np.hypot(points[:, 0] - cx, points[:, 1] - cy) <= win)
                if near.sum() >= p.min_points:
                    q = points[near, :2]
                    try:
                        nx, ny, nr, _ = circle_fit.taubinSVD(q)
                    except Exception:
                        nx, ny, nr = q[:, 0].mean(), q[:, 1].mean(), r

                    shift = float(np.hypot(nx - cx, ny - cy))
                    if shift > p.max_shift:  # too fast to be a stem; rein it in
                        nx = cx + (nx - cx) * p.max_shift / shift
                        ny = cy + (ny - cy) * p.max_shift / shift

                    occ = sector_occupancy(q, nx, ny)
                    if occ >= p.min_occupancy:
                        if not (p.min_radius <= nr <= p.max_radius):
                            nr = r
                        if direction > 0:
                            nr = min(nr, r * p.max_growth)
                        r = p.radius_smooth * r + (1 - p.radius_smooth) * nr
                    # else: keep the previous radius, the arc is too narrow to trust

                    cx, cy = float(nx), float(ny)
                    keep = in_band & (np.hypot(points[:, 0] - cx, points[:, 1] - cy) <= r + p.slack)
                    mask |= keep
                    axis_rows.append((zc, cx, cy, r, occ))
                    fitted = True

            if not fitted:
                gaps += 1
                if gaps > p.max_gap_bands and direction > 0:
                    break  # genuinely out of stem: this is the crown base
            else:
                gaps = 0
            zc += direction * p.step

    axis = np.array(sorted(axis_rows)) if axis_rows else np.empty((0, 5))
    return axis, mask


def semantic_labels(
    cloud,
    tree_labels: np.ndarray,
    seeds: np.ndarray,
    ground_mask: np.ndarray | None = None,
    ground_z: float = 0.30,
    radius_slack: float = 0.10,
    crown_base: float | None = None,
    method: str = "tracked",
    track: StemTrackParams = StemTrackParams(),
    return_axes: bool = False,
):
    """Classify every point as ground, stem or foliage.

    `method="tracked"` (default) follows each stem from breast height, re-fitting
    its centre and radius band by band, so lean and sweep are handled and the
    stem ends where the measurements stop rather than at a fixed height.

    `method="radial"` is the older vertical-cylinder rule kept for comparison:
    a point is stem if within `seeds[k, 2] / 2 + radius_slack` of the seed's
    vertical axis, optionally capped at `crown_base`.

    With `return_axes`, returns `(labels, axes)` where axes maps tree index to an
    (n_bands, 4) array of z, x, y, radius - the reconstructed stem centreline.
    """
    xyz = _xyz(cloud)
    out = np.full(len(xyz), FOLIAGE, np.int8)

    ground = ground_mask if ground_mask is not None else (xyz[:, 2] <= ground_z)
    out[ground] = GROUND

    labelled = (tree_labels >= 0) & ~ground
    idx = np.flatnonzero(labelled)
    axes: dict[int, np.ndarray] = {}
    if len(idx) == 0 or len(seeds) == 0:
        return (out, axes) if return_axes else out

    if method == "radial":
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
        return (out, axes) if return_axes else out

    if method != "tracked":
        raise ValueError(f"unknown method {method!r}; use 'tracked' or 'radial'")

    for k in range(len(seeds)):
        sel = np.flatnonzero((tree_labels == k) & ~ground)
        if len(sel) < track.min_points:
            continue
        axis, mask = track_stem_axis(xyz[sel], seeds[k], track)
        if mask.any():
            out[sel[mask]] = STEM
        if len(axis):
            axes[k] = axis

    return (out, axes) if return_axes else out


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
    lying within the tree's XY footprint are appended and keep semantic class 0 -
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
