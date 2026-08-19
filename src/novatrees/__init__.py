"""Tree instance segmentation for the NOVA 2026 course.

Ground filtering (CSF), cross-section stem detection for seeds, then 3D Dijkstra
region growing for per-point tree IDs — with a CHM-watershed reference method
ported from Yrttimaa's Point-Cloud-Tools for comparison.

Point clouds are carried as `xarray.Dataset` objects over a `point` dimension;
see `novatrees.dataset`.
"""

from .chm_watershed import ChmParams, chm_segment, rasterize_chm
from .csf import CsfParams, compare_with_cloudcompare, csf_ground, normalize_heights
from .dataset import as_dataset, attach, chm_dataarray, read_cloud, write_cloud, xyz
from .evaluate import confusion_pairs, instance_scores
from .io import read_xyz, write_labelled, write_seeds
from .pipeline import (
    GrowParams,
    SeedParams,
    detect_seeds,
    grow_instances,
    match_reference,
    segment,
)

__all__ = [
    "ChmParams",
    "CsfParams",
    "GrowParams",
    "SeedParams",
    "as_dataset",
    "attach",
    "chm_dataarray",
    "chm_segment",
    "compare_with_cloudcompare",
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
