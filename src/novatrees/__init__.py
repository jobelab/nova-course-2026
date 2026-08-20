# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Tree instance segmentation for the NOVA 2026 course.

Ground filtering (CSF), cross-section stem detection for seeds, then 3D Dijkstra
region growing for per-point tree IDs - with a CHM-watershed reference method
ported from Yrttimaa's Point-Cloud-Tools for comparison.

Point clouds are carried as `xarray.Dataset` objects over a `point` dimension;
see `novatrees.dataset`.
"""

from .chm_watershed import ChmParams, chm_segment, rasterize_chm
from .csf import CsfParams, compare_with_cloudcompare, csf_ground, normalize_heights
from .dataset import as_dataset, attach, chm_dataarray, read_cloud, write_cloud, xyz
from .denoise import DenoiseParams, denoise, denoise_radius, denoise_statistical
from .evaluate import attribute_errors, confusion_pairs, instance_scores
from .features import (
    StemScoreParams,
    eigen_features,
    reflectance_bounds,
    reflectance_index,
    stem_prescreen,
    stem_score,
)
from .extract import (
    StemTrackParams,
    track_stem_axis,
    FOLIAGE,
    GROUND,
    STEM,
    attach_labels,
    extract_trees,
    semantic_labels,
    tree_table,
)
from .glossary import lookup as glossary_lookup
from .glossary import table as glossary_table
from .inventory import (
    PlotGeometry,
    als_metrics,
    flag_edge_trees,
    infer_plot_geometry,
    join_sensors,
    match_positions,
    tree_metrics,
)
from .io import read_xyz, write_labelled, write_seeds
from .presets import ALS, MLS, PRESETS, TLS, SensorPreset, preset_for
from .workflow import SensorRun, run_sensor
from .stemgeom import ForkParams, axis_ratio, find_forks, sector_occupancy
from .taper import TaperParams, TaperResult, slice_fits, taper_curve
from .pipeline import (
    GrowParams,
    SeedParams,
    detect_seeds,
    grow_instances,
    match_reference,
    segment,
)

__all__ = [
    "glossary_table",
    "glossary_lookup",
    "run_sensor",
    "SensorRun",
    "denoise_statistical",
    "denoise_radius",
    "denoise",
    "DenoiseParams",
    "join_sensors",
    "match_positions",
    "als_metrics",
    "tree_metrics",
    "flag_edge_trees",
    "infer_plot_geometry",
    "PlotGeometry",
    "preset_for",
    "SensorPreset",
    "PRESETS",
    "TLS",
    "MLS",
    "ALS",
    "track_stem_axis",
    "StemTrackParams",
    "sector_occupancy",
    "find_forks",
    "axis_ratio",
    "ForkParams",
    "taper_curve",
    "stem_score",
    "stem_prescreen",
    "slice_fits",
    "reflectance_index",
    "reflectance_bounds",
    "eigen_features",
    "TaperResult",
    "TaperParams",
    "StemScoreParams",
    "ChmParams",
    "CsfParams",
    "GrowParams",
    "SeedParams",
    "as_dataset",
    "attach",
    "chm_dataarray",
    "chm_segment",
    "compare_with_cloudcompare",
    "FOLIAGE",
    "GROUND",
    "STEM",
    "attach_labels",
    "attribute_errors",
    "extract_trees",
    "semantic_labels",
    "tree_table",
    "confusion_pairs",
    "csf_ground",
    "detect_seeds",
    "grow_instances",
    "instance_scores",
    "match_reference",
    "normalize_heights",
    "rasterize_chm",
    "read_cloud",
    "read_xyz",
    "segment",
    "write_cloud",
    "write_labelled",
    "write_seeds",
    "xyz",
]
