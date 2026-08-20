# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Bridge to `pcf`, the package from the earlier course sessions.

`pcf` is a Python reimplementation of the parts of lidR this course needed:
ground classification, TIN height normalisation, variable-window tree location, and
the Dalponte and Silva crown algorithms. It was written for airborne data and it is
better at some things than what is here, so the point of this module is to make both
runnable side by side rather than to pick a winner in advance.

**Both pipelines are kept deliberately.** Where they disagree, the disagreement is
the interesting part, and neither is trusted by default:

| step | `novatrees` | `pcf` |
| --- | --- | --- |
| ground | CSF, native Python bindings | CSF or progressive morphological |
| normalise | DTM per cell, q-quantile | TIN interpolation of ground returns |
| tree location | cross-section stems, or CHM local maxima | variable-window local maxima on the CHM |
| crowns | 3D Dijkstra region growing | Dalponte 2016, Silva 2016, or watershed |
| crown metrics | 3D point-based | 2D polygons from the segmented raster |

`pcf` is an **optional** dependency, deliberately. It pulls in geopandas, rasterio,
shapely and pyproj, which `novatrees` otherwise does without, and it lives in a
separate repository. Everything here degrades to `available() -> False` when it is
absent, so nothing else in the package depends on it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .dataset import xyz as _xyz

__all__ = [
    "PCF_CANDIDATES",
    "available",
    "add_to_path",
    "ground_and_normalise",
    "locate_and_segment",
    "compare_normalisation",
    "PcfParams",
    "als_segment",
]

# Where the sibling repository usually sits. Add your own path if it moves.
PCF_CANDIDATES = [
    Path.home() / "organizations/slu/courses/2026/point_cloud_forestry/src",
    Path("../point_cloud_forestry/src"),
    Path("../../point_cloud_forestry/src"),
]


def add_to_path(extra: Path | str | None = None) -> bool:
    """Put `pcf` on `sys.path` if it can be found. Returns whether it is importable."""
    candidates = ([Path(extra)] if extra else []) + PCF_CANDIDATES
    for c in candidates:
        c = Path(c).expanduser()
        if (c / "pcf" / "__init__.py").exists() and str(c) not in sys.path:
            sys.path.insert(0, str(c))
    try:
        import pcf  # noqa: F401

        return True
    except Exception:
        return False


def available(extra: Path | str | None = None) -> bool:
    """True when `pcf` and its geo stack can be imported."""
    return add_to_path(extra)


def _to_cloud(path):
    import laspy
    from pcf.cloud import Cloud

    f = laspy.read(str(path))
    return Cloud(
        x=np.asarray(f.x), y=np.asarray(f.y), z=np.asarray(f.z),
        classification=np.asarray(f.classification),
        intensity=np.asarray(f.intensity) if hasattr(f, "intensity") else None,
    )


def ground_and_normalise(path, ground: str = "csf", algorithm: str = "tin",
                         zmin: float = -0.5, zmax: float = 50.0, clean: bool = True):
    """Classify ground and normalise height the `pcf` way. Returns (xyz, ground mask).

    The difference from `novatrees.csf.normalize_heights` is the surface. This
    interpolates a **TIN** through the ground returns; ours takes a quantile per
    raster cell. TIN follows terrain between returns rather than stepping between
    cells, which should matter more the sparser the ground returns are, so airborne
    data is where to expect a difference.
    """
    if not available():
        raise ImportError("pcf is not importable; see PCF_CANDIDATES")
    from pcf import ground as pg
    from pcf import normalize as pn

    cl = _to_cloud(path)
    cg = pg.classify_ground(cl, algorithm=ground)
    cn = pn.normalize_height(cg, algorithm=algorithm)
    if clean:
        # Drops points outside [zmin, zmax], which changes the point count. Turn it
        # off to keep a point-for-point correspondence with the input, which any
        # comparison against an independently normalised copy needs.
        cn = pn.clean_normalized(cn, zmin=zmin, zmax=zmax)
    return np.column_stack([cn.x, cn.y, cn.z]), (np.asarray(cg.classification) == 2)


def locate_and_segment(path, res: float = 0.5, ws: float = 3.0, hmin: float = 3.0,
                       method: str = "dalponte2016", subcircle: float = 0.2,
                       th_seed: float = 0.45, th_cr: float = 0.55, max_cr: float = 10.0):
    """The `pcf` airborne chain: CHM, tree tops, crowns. Returns a dict.

    `ws` is the local-maximum window in metres, and it is the parameter that decides
    how many trees you get: on the Day 4 ALS at 0.5 m resolution it gave 150 tops at
    2 m, 118 at 3 m and 71 at 5 m. There is no default that is right for every stand.
    """
    if not available():
        raise ImportError("pcf is not importable; see PCF_CANDIDATES")
    from pcf import normalize as pn
    from pcf import ground as pg
    from pcf import raster as pr
    from pcf import segment as ps

    cl = _to_cloud(path)
    cn = pn.clean_normalized(
        pn.normalize_height(pg.classify_ground(cl, algorithm="csf"), algorithm="tin")
    )
    chm = pr.rasterize_canopy(cn, res=res, algorithm="p2r", subcircle=subcircle)
    ttops = ps.locate_trees(chm, ws=ws, hmin=hmin)
    seg = getattr(ps, method)(chm, ttops, th_tree=hmin, th_seed=th_seed,
                              th_cr=th_cr, max_cr=max_cr) if method != "watershed" \
        else ps.watershed(chm, ttops, th_tree=hmin)
    crowns = ps.polygonize(seg)
    return {"chm": chm, "ttops": ttops, "segmentation": seg, "crowns": crowns,
            "n_tops": len(ttops), "n_crowns": len(crowns)}


def compare_normalisation(path, reference_path=None, quantile: float = 0.25,
                          cell: float = 0.5, max_points: int | None = None):
    """Normalise a cloud both ways and report how far apart they land.

    With `reference_path` pointing at an independently normalised copy of the same
    cloud, in the same point order, both are also scored against it. That is the only
    way to say which is *right* rather than merely which is different, and the Day 3
    data is the one place here that offers it.
    """
    from .csf import csf_ground, normalize_heights
    from .dataset import read_cloud

    ds = read_cloud(path, max_points=max_points)
    ours_ground = csf_ground(ds)
    ours = _xyz(normalize_heights(ds, ours_ground, cell=cell, quantile=quantile))
    theirs, _ = ground_and_normalise(path, clean=False)

    out = {"n_ours": len(ours), "n_theirs": len(theirs)}
    if len(ours) == len(theirs):
        d = ours[:, 2] - theirs[:, 2]
        out.update(mean_difference=float(d.mean()), rmse_between=float(np.sqrt((d**2).mean())))

    if reference_path is not None:
        ref = _xyz(read_cloud(reference_path, max_points=max_points))
        for label, arr in (("ours", ours), ("pcf", theirs)):
            if len(arr) != len(ref):
                out[f"{label}_vs_reference"] = "point counts differ, not comparable"
                continue
            e = arr[:, 2] - ref[:, 2]
            out[f"{label}_bias"] = float(e.mean())
            out[f"{label}_rmse"] = float(np.sqrt((e**2).mean()))
    return out


@dataclass
class PcfParams:
    """Parameters for the `pcf` airborne chain, used as an ALS detector here.

    Defaults are the ones measured best on the Day 4 ALS: 0.5 m CHM cells and a 3 m
    local-maximum window. `ws` is the parameter that decides how many trees you get,
    and there is no value that is right for every stand.
    """

    res: float = 0.5  # CHM cell size
    ws: float = 3.0  # local-maximum window, metres
    hmin: float = 3.0  # ignore maxima below this height
    subcircle: float = 0.2  # spread each return over a small disc before rasterising
    method: str = "dalponte2016"  # or "silva2016", "watershed"
    th_seed: float = 0.45
    th_cr: float = 0.55
    max_cr: float = 10.0


def _cloud_from_xyz(xyz: np.ndarray):
    """A `pcf.Cloud` from an array we have already normalised ourselves.

    Deliberately not `pcf`'s own reader. Holding ground classification and height
    normalisation fixed is what makes the comparison a comparison of *segmentation*
    rather than of four differences at once.
    """
    from pcf.cloud import Cloud

    P = np.asarray(xyz, float)
    return Cloud(x=P[:, 0].copy(), y=P[:, 1].copy(), z=P[:, 2].copy(),
                 classification=np.full(len(P), 1, np.uint8), intensity=None)


def als_segment(xyz, p: PcfParams | None = None, verbose: bool = False):
    """Segment an ALS cloud the `pcf` way. Returns (labels, seeds, crowns, stats).

    The chain is CHM, variable-window tree tops, then Dalponte 2016 crowns, and the
    crowns come back as a raster of ids, so every point takes the id of the cell it
    falls in. That is the actual airborne result rather than our 3D region growing
    seeded from someone else's tops.

    `labels` is 0-based with -1 unassigned, matching everything else here, so it
    scores through `novatrees.evaluate` and `novatrees.inventory` unchanged.
    """
    if not available():
        raise ImportError("pcf is not importable; see PCF_CANDIDATES")
    from pcf import raster as pr
    from pcf import segment as ps

    p = p or PcfParams()
    P = np.asarray(_xyz(xyz), float)
    cloud = _cloud_from_xyz(P)

    chm = pr.rasterize_canopy(cloud, res=p.res, algorithm="p2r", subcircle=p.subcircle)
    ttops = ps.locate_trees(chm, ws=p.ws, hmin=p.hmin)
    if not len(ttops):
        return np.full(len(P), -1, np.int32), np.empty((0, 3)), None, {"n_tops": 0}

    if p.method == "watershed":
        seg = ps.watershed(chm, ttops, th_tree=p.hmin)
    else:
        seg = getattr(ps, p.method)(chm, ttops, th_tree=p.hmin, th_seed=p.th_seed,
                                    th_cr=p.th_cr, max_cr=p.max_cr)

    # Raster ids to per-point labels. Row 0 is the northernmost row, so the row index
    # counts down from ymax; getting that backwards mirrors the plot silently.
    xmin, _, _, ymax = seg.extent
    col = np.floor((P[:, 0] - xmin) / seg.res).astype(int)
    row = np.floor((ymax - P[:, 1]) / seg.res).astype(int)
    nrow, ncol = seg.array.shape
    inside = (col >= 0) & (col < ncol) & (row >= 0) & (row < nrow)

    labels = np.full(len(P), -1, np.int32)
    ids = np.full(len(P), np.nan)
    ids[inside] = seg.array[row[inside], col[inside]]
    valid = np.isfinite(ids) & (ids > 0)
    # Crown ids are 1-based and not necessarily contiguous; compact them to 0-based.
    uniq, compact = np.unique(ids[valid], return_inverse=True)
    labels[valid] = compact.astype(np.int32)

    tx = ttops.geometry.x.to_numpy()
    ty = ttops.geometry.y.to_numpy()
    seeds = np.c_[tx, ty, np.full(len(tx), 0.25)]  # placeholder diameter, as for CHM
    if verbose:
        print(f"[pcf] {len(ttops)} tops -> {len(uniq)} crowns, "
              f"{int(valid.sum()):,} points assigned")
    return labels, seeds, ps.polygonize(seg), {
        "n_tops": int(len(ttops)), "n_crowns": int(len(uniq)),
        "n_assigned": int(valid.sum()), "method": p.method,
    }
