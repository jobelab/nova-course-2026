# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""LAZ reading and writing, including the treeID field CloudCompare reads."""

from __future__ import annotations

from pathlib import Path

import laspy
import numpy as np

__all__ = ["read_sample", "read_xyz", "write_labelled", "write_seeds"]


def read_xyz(path: str | Path) -> np.ndarray:
    """Read a LAS/LAZ file as an (n, 3) float64 array of scaled coordinates."""
    f = laspy.read(str(path))
    return np.c_[f.x, f.y, f.z]


def read_sample(
    path: str | Path,
    target: int = 2_000_000,
    centre: tuple[float, float] | None = None,
    radius: float | None = None,
    fields: tuple[str, ...] = (),
    chunk: int = 2_000_000,
    seed: int = 0,
) -> dict[str, np.ndarray]:
    """Read an even random sample of a cloud without ever holding it whole.

    Returns `x`, `y`, `z` plus any extra `fields` (`intensity`, `red`, ...).

    The keep probability is worked out from the header before the loop and applied
    inside it, so peak memory is set by `target` rather than by the file. That
    distinction matters more than it looks: `Plot_167_TLS_GroundZero.laz` holds 290
    million points in a 30 by 30 m box, and the 20 m plot circle is larger than that
    box, so clipping to the plot discards almost nothing. Accumulating first and
    thinning afterwards exhausts memory on a 15 GB machine.

    When `centre` and `radius` are given, the in-circle fraction is estimated from the
    header bounding box so that roughly `target` points survive the filter rather than
    `target` times that fraction.
    """
    import laspy

    rng = np.random.default_rng(seed)
    out: dict[str, list[np.ndarray]] = {k: [] for k in ("x", "y", "z", *fields)}
    n_seen = 0
    with laspy.open(str(path)) as f:
        n_total = f.header.point_count
        frac = 1.0
        if radius is not None:
            mins, maxs = f.header.mins, f.header.maxs
            box = max((maxs[0] - mins[0]) * (maxs[1] - mins[1]), 1e-9)
            frac = min(1.0, (np.pi * radius * radius) / box)
        p = min(1.0, target / max(n_total * frac, 1.0))
        for pts in f.chunk_iterator(chunk):
            x, y = np.asarray(pts.x), np.asarray(pts.y)
            keep = rng.random(len(x)) < p
            if centre is not None and radius is not None:
                keep &= (x - centre[0]) ** 2 + (y - centre[1]) ** 2 <= radius * radius
            if not keep.any():
                continue
            n_seen += int(keep.sum())
            out["x"].append(x[keep])
            out["y"].append(y[keep])
            out["z"].append(np.asarray(pts.z)[keep])
            for k in fields:
                out[k].append(np.asarray(getattr(pts, k))[keep].astype(np.float64))
            del x, y, keep
    got = {k: (np.concatenate(v) if v else np.empty(0)) for k, v in out.items()}
    got["_kept"] = n_seen
    got["_total"] = n_total
    got["_p"] = p
    return got


def write_labelled(
    src: str | Path,
    dst: str | Path,
    labels: np.ndarray,
    geodesic: np.ndarray | None = None,
    drop_unlabelled: bool = False,
) -> int:
    """Copy `src` to `dst`, adding a `treeID_dj` extra dimension from `labels`.

    Labels are 1-based so that 0 reads as "unassigned" - CloudCompare renders a
    scalar field of 0..n with a colour ramp, and a 0-valued background separates
    cleanly from tree 1.

    The field is `treeID_dj`, not `treeID`: the course clouds already ship a
    reference `treeid`, and overwriting it would destroy the only ground truth
    available. Both load side by side in CloudCompare, which is the point.

    Returns the number of points written.
    """
    f = laspy.read(str(src))
    if len(labels) != len(f.points):
        raise ValueError(f"labels ({len(labels)}) do not match points ({len(f.points)})")

    tree_id = (labels + 1).astype(np.int32)

    if drop_unlabelled:
        keep = labels >= 0
        f.points = f.points[keep]
        tree_id = tree_id[keep]
        if geodesic is not None:
            geodesic = geodesic[keep]

    f.add_extra_dim(laspy.ExtraBytesParams(name="treeID_dj", type=np.int32))
    f.treeID_dj = tree_id

    if geodesic is not None:
        finite = np.where(np.isfinite(geodesic), geodesic, -1.0).astype(np.float32)
        f.add_extra_dim(laspy.ExtraBytesParams(name="geodesic", type=np.float32))
        f.geodesic = finite

    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    f.write(str(dst))
    return len(f.points)


def write_seeds(dst: str | Path, seeds: np.ndarray, z: float = 1.30, like: str | Path | None = None):
    """Write detected stem centres as a small LAZ, with DBH as an extra dimension.

    Opening this next to the full cloud in CloudCompare is the quickest visual
    check that the cross-section step found the right stems.
    """
    header = laspy.LasHeader(point_format=6, version="1.4")
    if like is not None:
        src = laspy.read(str(like))
        header.offsets, header.scales = src.header.offsets, src.header.scales
    header.add_extra_dim(laspy.ExtraBytesParams(name="dbh", type=np.float32))
    header.add_extra_dim(laspy.ExtraBytesParams(name="treeID_dj", type=np.int32))

    las = laspy.LasData(header)
    las.x = seeds[:, 0]
    las.y = seeds[:, 1]
    las.z = np.full(len(seeds), z)
    las.dbh = seeds[:, 2].astype(np.float32)
    las.treeID_dj = np.arange(1, len(seeds) + 1, dtype=np.int32)

    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    las.write(str(dst))
    return len(seeds)
