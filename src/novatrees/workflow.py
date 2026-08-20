# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""One call per sensor: load, preprocess, detect trees, measure them.

The Day 3 notebooks work one cloud interactively. Day 4 works three, twice each
(heuristic and learned), which is six runs of the same sequence. That sequence
belongs here so the notebook can stay orchestration and comparison.

The sequence is the demo's, with the noise filter added:

    read (decimated) -> denoise -> CSF ground -> normalise height
      -> either cross-section seeds (TLS, MLS) or CHM watershed (ALS)
      -> 3D Dijkstra region growing -> per-tree metrics

**Height normalisation is not optional in Day 4.** The TLS is not georeferenced in
Z and sits about 138 m below the other two, so normalised height is the only datum
the three clouds share. Anything comparing them before that step is comparing
nothing.

`detector="learned"` swaps the seeding for TreeAIBox. On TLS and MLS that means the
boreal stem classifier and tree locator, which are the right models for this forest.
On ALS it means the reclamation-site models, which are **not**: they were trained on
a different structure entirely, and their output here should be read as a domain
transfer test rather than as a fair heuristic-versus-learned comparison.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .chm_watershed import chm_segment
from .csf import csf_ground, normalize_heights
from .dataset import read_cloud
from .dataset import xyz as _xyz
from .denoise import denoise
from .features import radiometric_field, stem_prescreen
from .inventory import PlotGeometry, als_metrics, flag_edge_trees, infer_plot_geometry, tree_metrics
from .pipeline import detect_seeds, grow_instances
from .presets import SensorPreset, preset_for

__all__ = ["SensorRun", "run_sensor"]


@dataclass
class SensorRun:
    name: str
    detector: str
    cloud: object  # xarray Dataset, height-normalised
    labels: np.ndarray  # instance id per point, -1 unassigned
    seeds: np.ndarray  # (n, 3) x, y, dbh
    trees: object  # DataFrame of per-tree metrics
    plot: PlotGeometry
    timings: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)


def run_sensor(
    path,
    preset: SensorPreset | None = None,
    detector: str = "heuristic",
    max_points: int | None = None,
    already_normalised: bool = False,
    verbose: bool = True,
) -> SensorRun:
    """Run the whole sequence for one cloud. See the module docstring for the order.

    `already_normalised` skips CSF and normalisation for a cloud whose Z is already
    height above ground. Use it deliberately: a cloud merely *zeroed* at the ground,
    like the Day 4 TLS, is not normalised. Its Z is shifted to a common datum, but
    the terrain is still in it, so every height still carries the slope of the plot.
    """
    p = preset or preset_for(path)
    t: dict[str, float] = {}
    log = print if verbose else (lambda *a, **k: None)

    t0 = time.time()
    ds = read_cloud(path, max_points=max_points or p.max_points)
    xyz = _xyz(ds)
    t["read"] = time.time() - t0
    log(f"[{p.name}] read {len(xyz):,} points in {t['read']:.1f}s "
        f"(stride {ds.attrs.get('decimation', 1)})")

    t0 = time.time()
    keep = denoise(xyz, p.denoise)
    t["denoise"] = time.time() - t0
    log(f"[{p.name}] denoise removed {int((~keep).sum()):,} "
        f"({100 * (~keep).mean():.2f}%) in {t['denoise']:.1f}s")

    if already_normalised:
        ground = xyz[:, 2] <= p.grow.ground_z
        norm_xyz = xyz
        t["ground"] = t["normalise"] = 0.0
    else:
        t0 = time.time()
        ground = csf_ground(xyz, p.csf)
        t["ground"] = time.time() - t0
        log(f"[{p.name}] CSF ground {int(ground.sum()):,} "
            f"({100 * ground.mean():.1f}%) in {t['ground']:.1f}s")

        t0 = time.time()
        # Noise excluded from the ground set: one return below the true surface
        # drags the DTM cell down and biases every height above it.
        norm = normalize_heights(ds, ground & keep)
        norm_xyz = _xyz(norm)
        ds = norm
        t["normalise"] = time.time() - t0
        log(f"[{p.name}] normalised, z {norm_xyz[:, 2].min():.2f} to "
            f"{norm_xyz[:, 2].max():.2f} m in {t['normalise']:.1f}s")

    plot = infer_plot_geometry(norm_xyz)
    log(f"[{p.name}] plot centre ({plot.x:.1f}, {plot.y:.1f}) radius {plot.radius:.1f} m")

    t0 = time.time()
    if detector == "learned":
        from .treeaibox import TreeAIBoxConfig, treeaibox_seeds
        import pathlib

        seeds, _stem, _tim = treeaibox_seeds(
            norm_xyz,
            TreeAIBoxConfig(models_dir=pathlib.Path("models"), stemcls=p.dl_stemcls,
                            treeloc=p.dl_treeloc, stem_stage=p.dl_stem_stage),
            verbose=verbose,
        )
    elif p.seed_method == "chm":
        res = chm_segment(norm_xyz, p.chm)
        tops = res["tops"]
        seeds = (np.c_[tops[:, 0], tops[:, 1], np.full(len(tops), 0.25)]
                 if len(tops) else np.empty((0, 3)))
    else:
        # Reflectance where the sensor records it, intensity otherwise: both carry
        # return strength, and the Day 4 clouds have only intensity.
        _field, _values = radiometric_field(ds)
        band = (norm_xyz[:, 2] >= 0.7) & (norm_xyz[:, 2] < 2.0)
        mask = np.zeros(len(norm_xyz), bool)
        if band.sum() > p.score.k:
            sub = ds.isel(point=np.flatnonzero(band)) if _values is not None else norm_xyz[band]
            sub_keep = stem_prescreen(sub if _values is not None else norm_xyz[band], p=p.score)
            mask[np.flatnonzero(band)[sub_keep]] = True
        if _values is None:
            log(f"[{p.name}] no usable reflectance or intensity: "
                "the pre-screen is running on verticality alone")
        mask &= keep  # noise never becomes a seed
        seeds = detect_seeds(norm_xyz, p.seeds, mask=mask if mask.any() else None)
    t["detect"] = time.time() - t0
    log(f"[{p.name}/{detector}] {len(seeds)} seeds in {t['detect']:.1f}s")

    t0 = time.time()
    if len(seeds):
        result = grow_instances(norm_xyz, seeds, p.grow)
        labels = result.labels
    else:
        labels = np.full(len(norm_xyz), -1, np.int32)
    t["grow"] = time.time() - t0
    log(f"[{p.name}/{detector}] grew {int((labels >= 0).sum()):,} points "
        f"in {t['grow']:.1f}s")

    t0 = time.time()
    metric_fn = als_metrics if p.name == "ALS" else tree_metrics
    trees = metric_fn(norm_xyz, labels, ground_z=p.grow.ground_z)
    if len(trees):
        trees = flag_edge_trees(trees, plot)
    t["metrics"] = time.time() - t0

    stats = {
        "n_points": int(len(norm_xyz)),
        "n_noise": int((~keep).sum()),
        "n_ground": int(ground.sum()),
        "n_seeds": int(len(seeds)),
        "n_trees": int(len(trees)),
        "n_edge_trees": int(trees.edge_tree.sum()) if len(trees) else 0,
        "total_s": float(sum(t.values())),
    }
    log(f"[{p.name}/{detector}] {stats['n_trees']} trees "
        f"({stats['n_edge_trees']} on the plot edge) in {stats['total_s']:.1f}s total")

    return SensorRun(p.name, detector, ds, labels, seeds, trees, plot, t, stats)
