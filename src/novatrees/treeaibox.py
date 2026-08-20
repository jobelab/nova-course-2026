# NOVA course 2026 — point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""TreeAIBox (NRCan) as a third method: learned stem classification and tree location.

TreeAIBox ships as a CloudCompare GUI plugin, but its `modules/` are ordinary
Python and torch, so the models can be driven directly. This wraps the TLS boreal
chain:

    stem classification   3D SegFormer over voxel blocks -> stem / non-stem
    tree location         a second network, run on the stem points only
    clustering            shortest path over the stem points

That last step is the same idea as `novatrees.pipeline` — geodesic growing from
seeds — which makes the interesting comparison a narrow one: **the seeds**. Ours
come from fitting circles in a cross-section; TreeAIBox's come from a trained
detector. Everything downstream can be held constant.

The models are labelled `(GPU3GB)`–`(GPU12GB)` but run on CPU. Measured here on
965 k points, 8 threads:

    stem classification   ~51 s
    tree location          ~2 s
    shortest-path cluster  ~0.1 s

so it scales to roughly a minute per million points, dominated entirely by the
stem classifier. Usable, not interactive.

Requires the TreeAIBox checkout and its virtualenv; see `TREEAIBOX.md`. Weights
are fetched on demand from the NRCan release page.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .dataset import xyz as _xyz

__all__ = ["TreeAIBoxConfig", "ensure_model", "stem_classification", "tree_locations", "treeaibox_seeds"]

MODEL_BASE = "https://github.com/NRCan/TreeAIBox/releases/download/v1.0"
DEFAULT_ROOT = Path("/home/sites/organizations/slu/courses/TreeAIBox")

# TLS boreal chain. Config file names keep the parentheses; weight files strip them.
STEMCLS = "treeisonet_tls_boreal_stemcls_esegformer3D_128_4cm(GPU3GB)"
TREELOC = "treeisonet_tls_boreal_treeloc_esegformer3D_128_10cm(GPU3GB)"


@dataclass
class TreeAIBoxConfig:
    root: Path = DEFAULT_ROOT
    models_dir: Path = Path("models")
    threads: int = 8
    use_cuda: bool = False


def _weight_name(model: str) -> str:
    return model.replace("(", "_").replace(")", "") + ".pth"


def ensure_model(model: str, cfg: TreeAIBoxConfig = TreeAIBoxConfig()) -> Path:
    """Download a TreeAIBox model if it is not already present."""
    import urllib.request

    cfg.models_dir.mkdir(parents=True, exist_ok=True)
    dst = cfg.models_dir / _weight_name(model)
    if dst.exists() and dst.stat().st_size > 0:
        return dst

    url = f"{MODEL_BASE}/{_weight_name(model)}"
    tmp = dst.with_suffix(".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(dst)
    return dst


def _prepare(cfg: TreeAIBoxConfig):
    import torch

    root = str(cfg.root)
    if root not in sys.path:
        sys.path.insert(0, root)
    torch.set_num_threads(cfg.threads)
    return Path(root) / "modules" / "treeisonet"


def stem_classification(cloud, cfg: TreeAIBoxConfig = TreeAIBoxConfig()) -> np.ndarray:
    """Learned stem / non-stem classification. Returns a boolean mask, True = stem.

    This is the slow step — about a minute per million points on CPU.
    """
    conf_dir = _prepare(cfg)
    from modules.filter.componentFilter import filterPoints  # noqa: E402

    pcd = _xyz(cloud)
    out = filterPoints(
        str(conf_dir / f"{STEMCLS}.json"),
        pcd,
        str(ensure_model(STEMCLS, cfg)),
        if_bottom_only=False,
        use_efficient=True,
        use_cuda=cfg.use_cuda,
    )
    # The network emits class 1 = non-stem, 2 = stem.
    return np.asarray(out).astype(np.int32) > 1


def tree_locations(cloud, stem_mask: np.ndarray, cfg: TreeAIBoxConfig = TreeAIBoxConfig()) -> np.ndarray:
    """Learned tree locations, run on the stem points only. Returns (n, 3) x/y/z.

    Feeding the whole cloud instead of just the stems is the mistake to avoid —
    the detector is trained on stem points and quietly finds fewer trees without
    them filtered.
    """
    conf_dir = _prepare(cfg)
    from modules.treeisonet.treeLoc import treeLoc  # noqa: E402

    pcd = _xyz(cloud)
    stems = pcd[stem_mask]
    if len(stems) == 0:
        return np.empty((0, 3))

    tops = treeLoc(
        str(conf_dir / f"{TREELOC}.json"),
        stems,
        str(ensure_model(TREELOC, cfg)),
        use_cuda=cfg.use_cuda,
        if_stem=True,  # selects the linear_pred head the released weights carry
    )
    return np.asarray(tops) if tops is not None else np.empty((0, 3))


def treeaibox_seeds(
    cloud, cfg: TreeAIBoxConfig = TreeAIBoxConfig(), default_dbh: float = 0.25, verbose: bool = True
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Full learned seeding: stem mask plus seeds in `detect_seeds` format.

    Returns `(seeds, stem_mask, timings)` where seeds is (n, 3) x/y/dbh, so it
    drops straight into `grow_instances` in place of the cross-section seeds.

    The detector returns positions, not diameters, so `default_dbh` fills the
    third column. It is used only for the stem/foliage split in
    `novatrees.extract`, never for the segmentation itself.
    """
    t0 = time.time()
    stem_mask = stem_classification(cloud, cfg)
    t1 = time.time()
    if verbose:
        print(f"stem classification: {t1 - t0:.1f}s, {stem_mask.sum():,} stem points")

    tops = tree_locations(cloud, stem_mask, cfg)
    t2 = time.time()
    if verbose:
        print(f"tree location: {t2 - t1:.1f}s, {len(tops)} trees")

    seeds = (
        np.c_[tops[:, 0], tops[:, 1], np.full(len(tops), default_dbh)]
        if len(tops)
        else np.empty((0, 3))
    )
    return seeds, stem_mask, {"stemcls_s": t1 - t0, "treeloc_s": t2 - t1}
