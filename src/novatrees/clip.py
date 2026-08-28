# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Clip a point cloud to a plot polygon, streaming.

The drone acquisitions do not cover the same ground: the nadir footprint is 26.2 ha
and the oblique 93.3 ha, so any difference between them mixes view angle with land
cover. Clipping both to the field plot removes the second and leaves the first.

The polygon is read from GeoJSON rather than a shapefile so that the plot boundary
can live in the repository as one small text file with no GDAL dependency at read
time - the conversion happens once, with `ogr2ogr`, and the result is versioned.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

__all__ = ["clip_cloud", "point_in_rings", "read_geojson_rings"]


def read_geojson_rings(path: str | Path) -> list[np.ndarray]:
    """Read every exterior ring of every (Multi)Polygon feature as an (n, 2) array.

    Interior rings - holes - are ignored. The plot polygons here have none, and
    silently treating a hole as solid is a smaller error than pretending to support
    something untested.
    """
    doc = json.loads(Path(path).read_text())
    feats = doc["features"] if doc.get("type") == "FeatureCollection" else [doc]
    rings: list[np.ndarray] = []
    for feat in feats:
        geom = feat["geometry"] if "geometry" in feat else feat
        polys = (
            [geom["coordinates"]]
            if geom["type"] == "Polygon"
            else geom["coordinates"]
            if geom["type"] == "MultiPolygon"
            else []
        )
        for poly in polys:
            rings.append(np.asarray(poly[0], dtype=np.float64)[:, :2])
    if not rings:
        raise ValueError(f"no polygon geometry in {path}")
    return rings


def point_in_rings(xy: np.ndarray, rings: list[np.ndarray]) -> np.ndarray:
    """Boolean mask of points falling inside any ring.

    A bounding-box test runs first and decides the great majority of points: over the
    oblique cloud the 20 m plot is a thousandth of the footprint, so the exact
    winding test only ever sees the handful that could possibly qualify.
    """
    from matplotlib.path import Path as MplPath

    xy = np.asarray(xy, dtype=np.float64)
    inside = np.zeros(len(xy), dtype=bool)
    for ring in rings:
        lo, hi = ring.min(axis=0), ring.max(axis=0)
        near = (
            (xy[:, 0] >= lo[0]) & (xy[:, 0] <= hi[0])
            & (xy[:, 1] >= lo[1]) & (xy[:, 1] <= hi[1])
            & ~inside
        )
        if near.any():
            inside[near] = MplPath(ring).contains_points(xy[near])
    return inside


def clip_cloud(src: str | Path, dst: str | Path, rings, chunk: int = 4_000_000) -> int:
    """Copy points of `src` that fall inside `rings` to `dst`. Returns the count.

    Streams both ends: the oblique RGB cloud is 170 M points and 4.9 GB, and the
    result is a few hundred thousand points. Header, scale, offset, CRS and any extra
    dimensions carry over unchanged, so the clipped file stays comparable with the
    parent and still opens in CloudCompare with its colour and normals intact.
    """
    import laspy

    src, dst = str(src), str(dst)
    kept = 0
    with laspy.open(src) as fin:
        with laspy.open(dst, mode="w", header=fin.header) as fout:
            for pts in fin.chunk_iterator(chunk):
                mask = point_in_rings(np.c_[pts.x, pts.y], rings)
                if mask.any():
                    fout.write_points(pts[mask])
                    kept += int(mask.sum())
    return kept
