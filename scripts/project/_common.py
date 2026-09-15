# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared setup for the individual-project analyses on plot 167.

Every script here needs the same three things: the plot geometry, the corrected
terrain, and a way to read a large cloud without exhausting memory. Building the
terrain takes about a minute, so it is cached to the output directory and rebuilt
only when that cache is missing.

Data lives outside the repository by design. `FIELD` points at the field survey and
laser scanning, `DRONE` at the clipped drone clouds. Both are documented in
`data/drone/README.md`; set NOVA_FIELD or NOVA_DRONE to override.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

CX, CY = 420407.631019, 6481815.135773      # plot 167 centre, SWEREF99 TM
PLOT_R = 20.0                                # plot radius, m
SURVEY_Z = 137.642                           # surveyed ground at the centre, RH2000
TLS_CONST = 138.124                          # recovered in 02_terrain.py
BOX_HALF = 15.0                              # TLS and MLS are delivered as a 30 m box

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "project"
FIELD = Path(os.environ.get(
    "NOVA_FIELD",
    "/mnt/c/Users/jose.beltran/Proton Drive/jobel/My files/SLU/data/field"))
DRONE = Path(os.environ.get("NOVA_DRONE", ROOT / "data" / "drone")) / "clip"

TLS = FIELD / "tls/plot167_matched/Plot_167_TLS_GroundZero.laz"
MLS = FIELD / "mls/plot167/Plot_167_MLS.laz"
ALS = FIELD / "als/helicopter_2021/ALS_helicopter.laz"
GIS = FIELD / "gis/phd_course_demo_aug26"
DRONE_CLOUDS = ("Nadir_RGB", "Oblique_RGB", "Nadir_MS", "Oblique_MS")


def csf_params():
    from novatrees.csf import CsfParams
    return CsfParams(cloth_resolution=0.5, class_threshold=0.30, rigidness=2)


def terrain(rebuild: bool = False):
    """The ALS terrain model, shifted onto MLS ground control. Returns (dtm, offset).

    The offset is not cosmetic. The ALS and MLS are not on the same vertical datum,
    and uncorrected the difference puts 2.089 m into every height derived from this
    terrain, with nothing in the drone clouds able to reveal it.
    """
    from novatrees.csf import csf_ground
    from novatrees.io import read_sample
    from novatrees.terrain import Dtm, dtm_from_ground

    cache = OUT / "dtm.npz"
    if cache.exists() and not rebuild:
        z = np.load(cache)
        return Dtm(grid=z["grid"], x0=float(z["x0"]), y0=float(z["y0"]),
                   cell=float(z["cell"])), float(z["offset"])

    p = csf_params()
    a = read_sample(ALS, target=2_000_000, centre=(CX, CY), radius=30.0)
    A = np.column_stack([a["x"], a["y"], a["z"]])
    raw = dtm_from_ground(A[csf_ground(A, p)], cell=0.5, quantile=0.25)

    m = read_sample(MLS, target=2_000_000, centre=(CX, CY), radius=PLOT_R)
    M = np.column_stack([m["x"], m["y"], m["z"]])
    Mg = M[csf_ground(M, p)]
    offset = float(np.median(Mg[:, 2] - raw.sample(Mg[:, 0], Mg[:, 1])))

    dtm = Dtm(grid=raw.grid + offset, x0=raw.x0, y0=raw.y0, cell=raw.cell)
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, grid=dtm.grid, x0=dtm.x0, y0=dtm.y0,
                        cell=dtm.cell, offset=offset)
    return dtm, offset


def field_stems(within: float = PLOT_R):
    """The 2011 field survey for plot 167: stem centres, DBH in cm, species."""
    import pandas as pd

    t = pd.read_csv(GIS / "treedataRemningstorp2011_final_only_within20m_trslg.txt", sep="\t")
    t = t[t.PLOT == 167]
    t = t[np.hypot(t.XCENT - CX, t.YCENT - CY) <= within].reset_index(drop=True)
    t["dbh"] = t.DIAM / 10.0
    return t


def current_dbh(within: float = PLOT_R):
    """A contemporaneous diameter list. Almost certainly derived from this same laser
    scanning rather than measured in the field, so it checks the implementation and
    does not validate the measurement."""
    import pandas as pd

    c = pd.read_csv(GIS / "Plot167_dbh.txt", sep="\t")
    return c[np.hypot(c.X - CX, c.Y - CY) <= within].reset_index(drop=True)


def in_box(x, y, half: float = BOX_HALF):
    """Inside the 30 by 30 m box the TLS and MLS actually cover.

    That box is 900 m2 and the plot is 1256 m2, so 28 per cent of the plot has no
    ground-based data. Scoring those instruments over the whole plot counts
    undelivered data as failure.
    """
    return (np.abs(np.asarray(x) - CX) <= half) & (np.abs(np.asarray(y) - CY) <= half)


def voxel(P: np.ndarray, size: float) -> np.ndarray:
    """One point per cubic voxel, to cap density before anything neighbour-based.

    TLS records about 323,000 points per m2. An 8 cm DBSCAN neighbourhood at that
    density holds thousands of points and the neighbour lists exhaust memory before
    clustering starts.
    """
    k = np.floor(np.asarray(P) / size).astype(np.int64)
    _, idx = np.unique(k, axis=0, return_index=True)
    return P[np.sort(idx)]


def height_band(path, dtm, zoff=0.0, lo=0.5, hi=2.3, target=6_000_000,
                voxel_size=0.01, chunk=2_000_000):
    """Points in a height band above the terrain, thinned inside the chunk loop."""
    import laspy

    rng = np.random.default_rng(0)
    out = []
    with laspy.open(str(path)) as f:
        p = min(1.0, target / max(f.header.point_count * 0.03, 1))
        for pts in f.chunk_iterator(chunk):
            x, y = np.asarray(pts.x), np.asarray(pts.y)
            z = np.asarray(pts.z) + zoff
            m = (x - CX) ** 2 + (y - CY) ** 2 <= PLOT_R ** 2
            if not m.any():
                continue
            h = z[m] - dtm.sample(x[m], y[m])
            k = (h >= lo) & (h <= hi) & (rng.random(int(m.sum())) < p)
            if k.any():
                out.append(np.column_stack([x[m][k], y[m][k], h[k]]))
            del x, y, z, m, h, k
    B = np.vstack(out)
    return voxel(B, voxel_size) if voxel_size else B


def normalised(path, dtm, zoff=0.0, target=2_000_000, radius=PLOT_R):
    """A height-normalised sample of a cloud: (n, 3) of x, y, height above terrain."""
    from novatrees.io import read_sample
    from novatrees.terrain import normalize_against

    d = read_sample(path, target=target, centre=(CX, CY), radius=radius)
    Q = np.column_stack([d["x"], d["y"], d["z"] + zoff])
    return np.column_stack([Q[:, 0], Q[:, 1], normalize_against(Q, dtm)])


def cache(name: str, build, fmt: str = "csv", rebuild: bool = False):
    """Return a cached result, computing it with `build()` only when missing.

    The analyses behind the later chapters take one to four minutes each, mostly in
    chunked reads over multi-gigabyte clouds. Caching is what lets a notebook open in
    a second on the second run, which is the difference between a notebook that gets
    reopened and one that does not.

    `fmt` is "csv" for a DataFrame or "npz" for a dict of arrays.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.{fmt}"
    if path.exists() and not rebuild:
        if fmt == "csv":
            import pandas as pd
            return pd.read_csv(path)
        z = np.load(path, allow_pickle=False)
        return {k: z[k] for k in z.files}
    obj = build()
    if fmt == "csv":
        obj.to_csv(path, index=False)
    else:
        np.savez_compressed(path, **obj)
    return obj


def notebook_setup():
    """Put `scripts/project` on the path so a notebook can import this module.

    Notebooks live in notebooks/project and the shared setup lives in scripts/project.
    Rather than duplicate it, each notebook calls this first. One source of truth for
    the plot geometry, the terrain and the memory-safe readers.
    """
    import sys
    p = str(ROOT / "scripts" / "project")
    if p not in sys.path:
        sys.path.insert(0, p)
