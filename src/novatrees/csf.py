# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Cloth Simulation Filter ground classification, and height normalisation.

CSF is available here two ways, and they are the *same* algorithm:

* **In Python** - the `cloth-simulation-filter` package, bindings published by
  the CSF authors. This is what the functions below use: no subprocess, no file
  round-trip, ~0.3 s on 15 M points.
* **In CloudCompare** - the `qCSF` plugin built for this machine
  (`~/.local/share/CCCorp/CloudCompare/plugins/libQCSF_PLUGIN.so`), reachable
  from the GUI or the `-CSF` command line. See `csf/run-csf.sh`.

They do not agree to the point. The plugin exposes scene presets (SLOPE / RELIEF
/ FLAT) that set rigidness plus some post-processing the raw library leaves off,
so expect a percent or two of difference in the ground count. Neither is "wrong";
`compare_with_cloudcompare` exists to quantify the gap rather than argue about it.

Reference: Zhang W. et al. (2016), *An Easy-to-Use Airborne LiDAR Data Filtering
Method Based on Cloth Simulation*, Remote Sensing 8(6):501.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xarray as xr

from .dataset import as_dataset
from .dataset import xyz as _xyz

__all__ = ["CsfParams", "csf_ground", "normalize_heights", "compare_with_cloudcompare"]

# CloudCompare's scene presets, in the rigidness the library actually takes.
SCENE_RIGIDNESS = {"SLOPE": 1, "RELIEF": 2, "FLAT": 3}


@dataclass
class CsfParams:
    cloth_resolution: float = 0.20  # grid spacing of the simulated cloth (m)
    class_threshold: float = 0.30  # ground if within this of the cloth (m)
    rigidness: int = 2  # 1 steep slope, 2 relief, 3 flat
    iterations: int = 500
    slope_smooth: bool = False  # post-process for disconnected terrain


def csf_ground(cloud, p: CsfParams = CsfParams()) -> np.ndarray:
    """Classify ground points. Returns a boolean mask, True = ground.

    `cloud` may be an xarray Dataset or an (n, 3) array.
    """
    import CSF

    xyz = _xyz(cloud)

    csf = CSF.CSF()
    csf.params.cloth_resolution = p.cloth_resolution
    csf.params.class_threshold = p.class_threshold
    csf.params.rigidness = p.rigidness
    csf.params.interations = p.iterations  # the library really does spell it this way
    csf.params.bSloopSmooth = p.slope_smooth
    csf.setPointCloud(xyz)

    ground_idx, _nonground_idx = CSF.VecInt(), CSF.VecInt()
    csf.do_filtering(ground_idx, _nonground_idx)

    mask = np.zeros(len(xyz), bool)
    mask[np.asarray(ground_idx, dtype=np.int64)] = True
    return mask


def normalize_heights(
    cloud, ground_mask: np.ndarray, cell: float = 0.5, quantile: float | None = 0.25
) -> xr.Dataset:
    """Subtract a ground surface from Z, returning a Dataset with `z` normalised.

    The DTM is one height per `cell`-sized cell, taken from the ground points
    falling in it. `quantile=None` uses the strict minimum, which is the textbook
    choice and is biased *low*: TLS noise puts a few returns below the true
    surface, so every height above it comes out too tall.

    Measured against the course's own `_hnorm` file (identical point order, so
    the comparison is point-to-point):

        quantile=None   bias +0.264 m   RMSE 0.275   28% of points within 0.25 m
        quantile=0.25   bias -0.002 m   RMSE 0.068   99% of points within 0.25 m

    Hence the default. The minimum is available if you want the textbook version,
    but it is measurably worse here.

    Cells with no ground point are filled from the nearest filled neighbour,
    adequate where ground returns are dense. The original elevation is kept as
    `z_orig`.
    """
    from scipy.spatial import cKDTree

    ds = as_dataset(cloud)
    xyz = _xyz(ds)
    g = xyz[ground_mask]
    if len(g) == 0:
        raise ValueError("no ground points; loosen the CSF parameters")

    x0, y0 = g[:, 0].min(), g[:, 1].min()
    cols = np.floor((g[:, 0] - x0) / cell).astype(np.int64)
    rows = np.floor((g[:, 1] - y0) / cell).astype(np.int64)
    nr, nc = rows.max() + 1, cols.max() + 1

    flat = rows * nc + cols
    if quantile is None:
        dtm = np.full((nr, nc), np.inf, np.float64)
        np.minimum.at(dtm.reshape(-1), flat, g[:, 2])
    else:
        import pandas as pd

        q = pd.Series(g[:, 2]).groupby(flat).quantile(quantile)
        dtm = np.full(nr * nc, np.nan)
        dtm[q.index.to_numpy()] = q.to_numpy()
        dtm = dtm.reshape(nr, nc)

    # Fill empty cells from the nearest filled one.
    filled = np.isfinite(dtm)
    if not filled.all():
        fr, fc = np.where(filled)
        er, ec = np.where(~filled)
        if len(fr):
            _, nn = cKDTree(np.c_[fr, fc]).query(np.c_[er, ec])
            dtm[er, ec] = dtm[fr[nn], fc[nn]]

    pcols = np.clip(np.floor((xyz[:, 0] - x0) / cell).astype(np.int64), 0, nc - 1)
    prows = np.clip(np.floor((xyz[:, 1] - y0) / cell).astype(np.int64), 0, nr - 1)
    ground_z = dtm[prows, pcols]

    out = ds.copy()
    out["z_orig"] = ("point", xyz[:, 2])
    out["z"] = ("point", xyz[:, 2] - ground_z)
    out["ground"] = ("point", ground_mask)
    out["z"].attrs.update(units="m", description="height above CSF ground surface")
    out.attrs["dtm_cell"] = cell
    out.attrs["dtm_quantile"] = "min" if quantile is None else quantile
    return out


def compare_with_cloudcompare(
    src: str | Path,
    outdir: str | Path,
    scene: str = "RELIEF",
    cloth_resolution: float = 0.2,
    class_threshold: float = 0.3,
    binary: str = "/opt/cloudcompare-qt6-qpcl/bin/CloudCompare",
) -> dict:
    """Run the CloudCompare qCSF plugin on the same file, for cross-checking.

    Returns the ground/off-ground counts the plugin produced. Requires the
    plugin build; see `setup/cloudcompare-linux.md`.
    """
    import laspy

    src, outdir = Path(src).resolve(), Path(outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    link = outdir / src.name
    if not link.exists():
        link.symlink_to(src)

    env = {
        "LD_LIBRARY_PATH": "/opt/pcl-qt6/lib",
        "QT_QPA_PLATFORM": "offscreen",
        "HOME": str(Path.home()),
        "PATH": "/usr/bin:/bin",
    }
    cmd = [
        binary, "-SILENT", "-C_EXPORT_FMT", "LAS", "-EXT", "laz",
        "-O", src.name,
        "-CSF", "-SCENES", scene,
        "-CLOTH_RESOLUTION", str(cloth_resolution),
        "-CLASS_THRESHOLD", str(class_threshold),
        "-MAX_ITERATION", "500",
        "-EXPORT_GROUND", "-EXPORT_OFFGROUND",
    ]
    proc = subprocess.run(cmd, cwd=outdir, env=env, capture_output=True, text=True, timeout=1800)
    link.unlink(missing_ok=True)

    stem = src.stem
    g = outdir / f"{stem}_ground_points.laz"
    o = outdir / f"{stem}_offground_points.laz"
    if not g.exists():
        raise RuntimeError(f"CloudCompare CSF produced no output:\n{proc.stdout[-2000:]}")

    return {
        "ground": len(laspy.read(str(g)).points),
        "offground": len(laspy.read(str(o)).points),
        "ground_file": g,
        "offground_file": o,
    }
