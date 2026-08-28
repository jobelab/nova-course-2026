# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""xarray containers for point clouds and rasters.

A LAS file is a table of points with a pile of named per-point attributes -
`reflectance`, `treeid`, whatever the previous tool wrote. Carrying that around
as a bare `(n, 3)` array plus a handful of loose variables loses the names and
invites mismatched-length bugs. An `xarray.Dataset` over a single `point`
dimension keeps every attribute aligned and self-describing, and a labelled
`DataArray` is a far better home for the CHM than an ndarray with the geotransform
remembered separately.

The maths underneath is still numpy: scipy, scikit-learn and CSF all want raw
arrays, so the compute functions unwrap at entry and rewrap on the way out.
xarray is the container and the interface, not the kernel.

    ds = read_cloud("plot.laz")
    ds                      # <xarray.Dataset> dims(point: 15595864)
    ds.z.mean()             # labelled, aligned
    xyz(ds)                 # (n, 3) ndarray when a kernel needs one
"""

from __future__ import annotations

from pathlib import Path

import laspy
import numpy as np
import xarray as xr

__all__ = ["read_cloud", "xyz", "as_dataset", "chm_dataarray", "attach", "write_cloud"]

# LAS attributes that are noise for our purposes; skip them on load.
_SKIP = {
    "X", "Y", "Z", "return_number", "number_of_returns", "scan_direction_flag",
    "edge_of_flight_line", "synthetic", "key_point", "withheld", "overlap",
    "scanner_channel", "scan_angle", "scan_angle_rank", "user_data",
    "point_source_id", "gps_time", "classification_flags", "raw_classification",
}


def read_cloud(
    path: str | Path,
    extras: bool = True,
    every: int = 1,
    max_points: int | None = None,
) -> xr.Dataset:
    """Read a LAS/LAZ file into a Dataset over a `point` dimension.

    Coordinates x, y, z become data variables (not xarray coords: they are not
    an index, and making them one would invite a sort that reorders the cloud).

    `every` keeps one point in N, `max_points` picks that stride for you. Both read
    in chunks, so the whole file never lands in memory at once. This matters more
    than it sounds: the Day 4 TLS plot is 290 M points, which is 6.5 GB of float64
    coordinates before any working copy, on a machine with about 9 GB free.

    Decimation here is a **stride**, not a random sample. Reproducible between runs,
    and it does not disturb the spatial distribution the way taking the first N
    points would.
    """
    if max_points is not None and every == 1:
        with laspy.open(str(path)) as fh:
            total = fh.header.point_count
        every = max(1, int(np.ceil(total / max_points)))

    if every > 1:
        chunks: dict[str, list[np.ndarray]] = {}
        names: list[str] | None = None
        offset = 0
        with laspy.open(str(path)) as fh:
            header = fh.header
            for chunk in fh.chunk_iterator(5_000_000):
                sel = np.arange((-offset) % every, len(chunk.array), every)
                offset = (offset + len(chunk.array)) % every
                if len(sel) == 0:
                    continue
                sub = chunk[sel]
                if names is None:
                    names = ["x", "y", "z"] + (
                        [n for n in sub.point_format.dimension_names if n not in _SKIP
                         and n not in ("x", "y", "z")] if extras else []
                    )
                for n in names:
                    try:
                        arr = np.asarray(sub[n])
                    except Exception:
                        continue
                    chunks.setdefault(n, []).append(arr)
        data = {n: ("point", np.concatenate(v)) for n, v in chunks.items() if len(v)}
        n_points = len(data["x"][1]) if "x" in data else 0
    else:
        f = laspy.read(str(path))
        header = f.header
        n = len(f.points)
        data = {
            "x": ("point", np.asarray(f.x)),
            "y": ("point", np.asarray(f.y)),
            "z": ("point", np.asarray(f.z)),
        }
        if extras:
            for name in f.point_format.dimension_names:
                if name in _SKIP or name in data:
                    continue
                try:
                    arr = np.asarray(f[name])
                except Exception:
                    continue
                if arr.shape == (n,):
                    data[name] = ("point", arr)
        n_points = n

    ds = xr.Dataset(data)
    ds.attrs.update(
        source=str(path),
        n_points=n_points,
        decimation=every,
        crs_offsets=tuple(float(v) for v in header.offsets),
        crs_scales=tuple(float(v) for v in header.scales),
    )
    for var, unit in (("x", "m"), ("y", "m"), ("z", "m")):
        if var in ds:
            ds[var].attrs["units"] = unit
    if "z" in ds:
        ds["z"].attrs["description"] = "height above ground if the cloud is normalised"
    return ds


def xyz(ds: xr.Dataset | np.ndarray) -> np.ndarray:
    """Unwrap to a contiguous (n, 3) float array for the numeric kernels."""
    if isinstance(ds, np.ndarray):
        return ds
    return np.ascontiguousarray(
        np.column_stack([ds["x"].values, ds["y"].values, ds["z"].values])
    )


def as_dataset(obj: xr.Dataset | np.ndarray) -> xr.Dataset:
    """Accept either container; return a Dataset."""
    if isinstance(obj, xr.Dataset):
        return obj
    arr = np.asarray(obj)
    return xr.Dataset(
        {"x": ("point", arr[:, 0]), "y": ("point", arr[:, 1]), "z": ("point", arr[:, 2])}
    )


def attach(ds: xr.Dataset, name: str, values: np.ndarray, **attrs) -> xr.Dataset:
    """Return a copy of `ds` with a new per-point variable attached."""
    out = ds.copy()
    out[name] = ("point", np.asarray(values))
    out[name].attrs.update(attrs)
    return out


def chm_dataarray(chm: np.ndarray, origin: tuple[float, float], pixel_size: float) -> xr.DataArray:
    """Wrap a CHM raster with real-world x/y coordinates at cell centres."""
    x0, y0 = origin
    nr, nc = chm.shape
    return xr.DataArray(
        chm,
        dims=("y", "x"),
        coords={
            "y": y0 + (np.arange(nr) + 0.5) * pixel_size,
            "x": x0 + (np.arange(nc) + 0.5) * pixel_size,
        },
        name="chm",
        attrs={"units": "m", "pixel_size": pixel_size, "long_name": "canopy height"},
    )


def write_cloud(ds: xr.Dataset, dst: str | Path, source: str | Path | None = None) -> int:
    """Write a Dataset back to LAZ, carrying its extra per-point variables.

    `source` supplies the header (scales, offsets, CRS); it defaults to the file
    the Dataset was read from.
    """
    src = source or ds.attrs.get("source")
    if src is None:
        raise ValueError("no source header available; pass source=")

    f = laspy.read(str(src))
    if len(f.points) != ds.sizes["point"]:
        raise ValueError(f"point count mismatch: {len(f.points)} vs {ds.sizes['point']}")

    existing = set(f.point_format.dimension_names)
    for name, var in ds.data_vars.items():
        if name in ("x", "y", "z") or name in existing:
            continue
        arr = var.values
        dtype = arr.dtype
        if dtype.kind == "b":
            arr, dtype = arr.astype(np.uint8), np.dtype(np.uint8)
        f.add_extra_dim(laspy.ExtraBytesParams(name=name, type=dtype))
        f[name] = arr

    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    f.write(str(dst))
    return len(f.points)
