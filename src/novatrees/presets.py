# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Sensor presets: the same pipeline, retuned per platform.

The Day 3 defaults are tuned for a dense terrestrial scan. Point them at airborne
data unchanged and they fail, not because the parameters are slightly off but
because **the method itself has to change**.

That is the whole point of comparing platforms:

| | TLS | MLS | ALS |
| --- | --- | --- | --- |
| viewpoint | from below, static | from below, moving | from above |
| density | ~300,000 pts/m2 | ~70,000 pts/m2 | ~3,000 pts/m2 |
| stems visible | yes, richly | yes, partially | **no** |
| seeds from | cross-section | cross-section | **canopy maxima** |
| dominant error | occlusion behind stems | trajectory drift, thinner returns | no stem information at all |

A helicopter cannot see a stem under a closed canopy, so cross-section seeding has
nothing to cluster and CHM watershed becomes the only option. On the Day 3 TLS plot
the ranking was the reverse: watershed reached recall 0.15 where cross-section
seeding reached 0.68, because half the stand never reaches the canopy. Neither
method is better in general. They answer to different data.

Densities above are computed from the Day 4 clouds. Numbers in the presets are
starting points, not settled values, and each carries a note on what drove it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .chm_watershed import ChmParams
from .csf import CsfParams
from .denoise import DenoiseParams
from .features import StemScoreParams
from .pipeline import GrowParams, SeedParams
from .taper import TaperParams

__all__ = ["SensorPreset", "TLS", "MLS", "ALS", "PRESETS", "preset_for"]


@dataclass
class SensorPreset:
    name: str
    seed_method: str  # "cross-section" or "chm"
    csf: CsfParams
    seeds: SeedParams
    grow: GrowParams
    score: StemScoreParams
    chm: ChmParams
    taper: TaperParams
    denoise: DenoiseParams = field(default_factory=DenoiseParams)
    # TreeAIBox weights for the learned detector, and whether that model set has a
    # stem-classification stage before tree location.
    dl_stemcls: str = "treeisonet_tls_boreal_stemcls_esegformer3D_128_4cm(GPU3GB)"
    dl_treeloc: str = "treeisonet_tls_boreal_treeloc_esegformer3D_128_10cm(GPU3GB)"
    dl_stem_stage: bool = True
    max_points: int | None = None  # decimate on load; None reads everything
    notes: str = ""


TLS = SensorPreset(
    name="TLS",
    seed_method="cross-section",
    # Fine cloth: a static terrestrial scan resolves the ground in detail, and the
    # 0.25 quantile beat the textbook minimum by 0.26 m of bias on the Day 3 plot.
    csf=CsfParams(cloth_resolution=0.20, class_threshold=0.30, rigidness=2),
    # The demo's slab. eps 0.04 separates stems 0.31 m apart; 0.08 merged them.
    seeds=SeedParams(slice_lo=1.2, slice_hi=1.4, eps=0.04, min_samples=20, min_support=15),
    grow=GrowParams(ground_z=0.30, voxel=0.10, k=9, max_edge=0.25),
    # Reflectance separates bark from foliage by about 9 dB, so it carries most of
    # the weight; the radial term needs seeds and so starts at zero.
    score=StemScoreParams(k=20, w_vertical=0.4, w_reflectance=0.4, w_radial=0.2,
                          prescreen_pct=40),
    chm=ChmParams(pixel_size=0.20, min_distance=0.6, min_tree_height=2.0),
    taper=TaperParams(),
    # Mixed pixels around stems are the concern, not birds: keep it gentle.
    denoise=DenoiseParams(method='statistical', k=8, n_sigma=2.5),
    max_points=8_000_000,
    notes="Dense, from below. Stems richly sampled; canopy poorly. Occlusion behind "
          "stems is the dominant error. Decimated on load: a full Day 4 TLS plot is "
          "290 M points, 6.5 GB of coordinates.",
)

MLS = SensorPreset(
    name="MLS",
    seed_method="cross-section",
    csf=CsfParams(cloth_resolution=0.30, class_threshold=0.30, rigidness=2),
    # Thinner returns per stem than TLS, so the slab is deepened and the cluster
    # thresholds relaxed rather than losing stems outright.
    seeds=SeedParams(slice_lo=1.1, slice_hi=1.5, eps=0.06, min_samples=12,
                     min_cluster_pts=25, min_support=8),
    grow=GrowParams(ground_z=0.30, voxel=0.12, k=9, max_edge=0.30),
    score=StemScoreParams(k=25, w_vertical=0.45, w_reflectance=0.35, w_radial=0.2,
                          prescreen_pct=50),
    chm=ChmParams(pixel_size=0.25, min_distance=0.8, min_tree_height=2.0),
    taper=TaperParams(min_points=60, slice_thickness=0.15),
    # Mobile data carries more stray returns; tighter than TLS.
    denoise=DenoiseParams(method='statistical', k=8, n_sigma=2.0),
    max_points=8_000_000,
    notes="From below and moving. Sees stems but with fewer returns each and some "
          "trajectory noise, so cluster thresholds are looser than TLS. Registration "
          "drift, not occlusion, is the thing to watch.",
)

ALS = SensorPreset(
    name="ALS",
    seed_method="chm",  # the important line in this file
    # Coarser cloth: airborne ground returns are sparse under canopy, and a fine
    # cloth chases noise it cannot support.
    csf=CsfParams(cloth_resolution=0.50, class_threshold=0.30, rigidness=2),
    seeds=SeedParams(),  # present for interface symmetry; unused when seed_method="chm"
    grow=GrowParams(ground_z=0.50, voxel=0.30, k=9, max_edge=0.80),
    score=StemScoreParams(w_vertical=1.0, w_reflectance=0.0, w_radial=0.0,
                          prescreen_pct=100),
    # This is where ALS trees come from. Pixel and separation are set from crown
    # size rather than stem size, which is the whole difference.
    chm=ChmParams(pixel_size=0.50, min_distance=1.5, min_tree_height=3.0,
                  min_crown_area=3.0, smooth_sigma=1.0),
    taper=TaperParams(min_points=40, slice_thickness=0.50, vertical_step=0.50),
    # Airborne returns are sparse; a harsh filter deletes real canopy.
    denoise=DenoiseParams(method='statistical', k=6, n_sigma=3.0),
    # The only published ALS models are trained on reclamation sites, not boreal
    # forest, and there is no ALS stem classifier at all. Running them here is a
    # domain-transfer test, not a like-for-like comparison.
    dl_stemcls="treeisonet_als_reclamation_treeloc_esegformer3D_128_10cm(GPU4GB)",
    dl_treeloc="treeisonet_als_reclamation_treeloc_esegformer3D_128_10cm(GPU4GB)",
    dl_stem_stage=False,
    max_points=None,
    notes="From above. No usable stem returns under canopy, so cross-section seeding "
          "has nothing to find and CHM watershed is the only route. Expect suppressed "
          "trees to be missed entirely: that is a property of looking down, not a "
          "tuning failure. Taper is not meaningful from ALS alone.",
)

PRESETS: dict[str, SensorPreset] = {p.name: p for p in (TLS, MLS, ALS)}


def preset_for(name_or_path: str) -> SensorPreset:
    """Pick a preset by name, or guess it from a file name.

    Guessing is a convenience for notebooks, not a classifier. It looks for TLS,
    MLS or ALS in the string and falls back to TLS, which is the safest default
    because it is the one whose assumptions fail loudly rather than quietly.
    """
    s = str(name_or_path).upper()
    for key in ("TLS", "MLS", "ALS"):
        if key in s:
            return PRESETS[key]
    return TLS
