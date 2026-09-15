# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""A terrain model built from one cloud and applied to another.

`csf.normalize_heights` normalises a cloud against its own ground returns, which is
the right thing for laser scanning and impossible for photogrammetry. A
photogrammetric cloud only contains surfaces the cameras could see, and under a
closed canopy the ground is not one of them: on plot 167 the drone clouds hold
nothing at all below roughly 15 m. Normalising such a cloud against its own lowest
points would subtract canopy, not terrain, and every height would come out too short
by however much canopy was mistaken for ground.

So the terrain comes from the lidar and is applied to everything else. That makes the
DTM a shared object rather than a step inside one cloud's pipeline, which is what this
module adds.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["Dtm", "dtm_from_ground", "normalize_against"]


@dataclass
class Dtm:
    """A regular grid of ground elevations, with the origin of its lower-left cell."""

    grid: np.ndarray  # (rows, cols), elevation in the cloud's vertical datum
    x0: float
    y0: float
    cell: float

    @property
    def extent(self) -> tuple[float, float, float, float]:
        r, c = self.grid.shape
        return (self.x0, self.x0 + c * self.cell, self.y0, self.y0 + r * self.cell)

    def sample(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Bilinear elevation at each (x, y). Positions outside the grid clamp to the edge.

        Bilinear rather than nearest: a 0.5 m grid sampled nearest gives every point in
        a cell the same ground, which puts visible 0.5 m steps into a normalised cloud
        and into anything derived from it.
        """
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        r, c = self.grid.shape
        fx = np.clip((x - self.x0) / self.cell - 0.5, 0, c - 1)
        fy = np.clip((y - self.y0) / self.cell - 0.5, 0, r - 1)
        x0 = np.floor(fx).astype(np.int64)
        y0 = np.floor(fy).astype(np.int64)
        x1 = np.minimum(x0 + 1, c - 1)
        y1 = np.minimum(y0 + 1, r - 1)
        tx, ty = fx - x0, fy - y0
        g = self.grid
        return (
            g[y0, x0] * (1 - tx) * (1 - ty)
            + g[y0, x1] * tx * (1 - ty)
            + g[y1, x0] * (1 - tx) * ty
            + g[y1, x1] * tx * ty
        )


def dtm_from_ground(
    ground_xyz: np.ndarray, cell: float = 0.5, quantile: float | None = 0.25
) -> Dtm:
    """Rasterise classified ground points into a `Dtm`.

    `quantile` picks the elevation within each cell, defaulting to the 0.25 quantile
    for the reason given in `csf.normalize_heights`: the strict minimum follows the
    noise floor downward and biases every height above it upward. Empty cells are
    filled from the nearest filled cell, which is adequate where ground returns are
    dense and is reported by `holes_filled` so it can be judged rather than assumed.
    """
    from scipy.spatial import cKDTree

    g = np.asarray(ground_xyz, dtype=np.float64)
    if len(g) == 0:
        raise ValueError("no ground points to build a DTM from")

    x0 = np.floor(g[:, 0].min() / cell) * cell
    y0 = np.floor(g[:, 1].min() / cell) * cell
    cols = ((g[:, 0] - x0) / cell).astype(np.int64)
    rows = ((g[:, 1] - y0) / cell).astype(np.int64)
    nr, nc = int(rows.max()) + 1, int(cols.max()) + 1

    grid = np.full((nr, nc), np.nan)
    flat = rows * nc + cols
    order = np.argsort(flat, kind="stable")
    flat_s, z_s = flat[order], g[order, 2]
    edges = np.flatnonzero(np.r_[True, flat_s[1:] != flat_s[:-1], True])
    for a, b in zip(edges[:-1], edges[1:]):
        cellz = z_s[a:b]
        grid.flat[flat_s[a]] = cellz.min() if quantile is None else np.quantile(cellz, quantile)

    empty = np.isnan(grid)
    if empty.any():
        yy, xx = np.nonzero(~empty)
        tree = cKDTree(np.column_stack([xx, yy]))
        ey, ex = np.nonzero(empty)
        _, idx = tree.query(np.column_stack([ex, ey]))
        grid[ey, ex] = grid[yy[idx], xx[idx]]

    dtm = Dtm(grid=grid, x0=float(x0), y0=float(y0), cell=float(cell))
    dtm.holes_filled = int(empty.sum())          # noqa: attribute set for reporting
    dtm.cells = int(grid.size)
    return dtm


def normalize_against(xyz: np.ndarray, dtm: Dtm) -> np.ndarray:
    """Height above the terrain model for each point of an (n, 3) array."""
    xyz = np.asarray(xyz, dtype=np.float64)
    return xyz[:, 2] - dtm.sample(xyz[:, 0], xyz[:, 1])
