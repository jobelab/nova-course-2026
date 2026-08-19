"""Cross-section stem detection + 3D Dijkstra region growing for tree instance IDs.

The method, in three moves:

1. **Remove the ground.** Non-negotiable, not tidiness. The region growing in
   step 3 walks a nearest-neighbour graph, and the forest floor is one
   continuous sheet of points touching the base of every stem. Leave it in and
   the cheapest path from tree A's seed to tree B's crown runs *through the
   ground*, so labels bleed across the whole plot in a single hop.

2. **Detect stems in a horizontal cross-section** at breast height. Cluster the
   slice in 2D, fit a circle to each cluster, and keep the ones that look like a
   stem and are vertically continuous. Those centres are the seeds.

3. **Grow regions by 3D Dijkstra** from those seeds over a kNN graph of the
   above-ground points. Every point is labelled with the seed it is
   geodesically closest to — distance *through the canopy*, not straight-line,
   which is what keeps interlocking crowns apart.

Where this fails, and where it does not
---------------------------------------

Big merged instances look like a growing problem and are almost always a
*seeding* problem. Measured on the course plot: the largest predicted instance
swallowed two reference trees nearly whole (99.5% and 99.7% of each). Ref 146 had
a seed 0.02 m away; ref 141 had none within 1.95 m. Dijkstra cannot split a
region between two trees when only one of them has a seed — there is nothing to
split toward.

Neither graph knob repairs it, and the sweeps are worth knowing so nobody repeats
them:

* `max_geodesic` truncates every tree at the same path length. Tightening it from
  inf to 8 m shrank the largest instance from 3.37 M to 0.76 M points but left
  69% of the cloud unlabelled, with mean IoU falling and height RMSE rising.
* `max_edge` from 0.50 down to 0.15 barely moved the largest instance at all
  (3.37 M to 3.35 M). The crowns are genuinely touching at short range, so no
  edge-length threshold separates them.

`max_edge = 0.25` is the default because it does modestly improve matching
(recall 0.51 to 0.57, precision 0.67 to 0.70), not because it addresses merging.

The real fix is a better seed set. `novatrees.treeaibox` supplies one: its trained
detector found the stem our cross-section missed, 0.21 m from ref 141, which is
exactly why its largest instance is 1.89 M points rather than 3.37 M.

Heights are assumed **normalised** (Z above ground), as in `*_hnorm.laz`. For a
raw cloud, run CSF first (see `csf/run-csf.sh`) and normalise, or pass
`--ground-z` to suit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from sklearn.cluster import DBSCAN

from .dataset import xyz as _xyz

__all__ = ["SeedParams", "GrowParams", "detect_seeds", "grow_instances", "segment"]


@dataclass
class SeedParams:
    """Cross-section stem detection."""

    slice_lo: float = 1.15  # bottom of the breast-height slab (m above ground)
    slice_hi: float = 1.45  # top of it
    eps: float = 0.08  # DBSCAN neighbourhood in the 2D slice (m)
    min_samples: int = 20
    min_cluster_pts: int = 40
    min_radius: float = 0.015  # 3 cm stems and up
    max_radius: float = 0.60
    max_extent: float = 1.20  # reject sprawling non-stem clusters (m)
    support_band: float = 0.30  # thickness of the check slabs above/below (m)
    support_gap: float = 0.15  # gap between the slice and those slabs (m)
    min_support: int = 15  # points required in each, within the stem radius
    support_slack: float = 0.10  # radius tolerance for the support check (m)


@dataclass
class GrowParams:
    """3D Dijkstra region growing."""

    ground_z: float = 0.30  # drop everything below this (m above ground)
    voxel: float = 0.10  # graph node spacing (m)
    k: int = 9  # kNN per node, including self
    max_edge: float = 0.25  # refuse to bridge gaps wider than this (m)
    max_geodesic: float = np.inf  # optional cap on path length from a seed (m)
    seed_z: float = 1.30  # height at which seeds enter the graph (m)


@dataclass
class Result:
    seeds: np.ndarray  # (n_trees, 3): x, y, dbh
    labels: np.ndarray  # (n_points,) tree index per input point, -1 = unassigned
    node_labels: np.ndarray  # (n_nodes,) per graph node
    nodes: np.ndarray  # (n_nodes, 3) voxel-downsampled above-ground points
    geodesic: np.ndarray  # (n_nodes,) distance to the winning seed
    stats: dict = field(default_factory=dict)


def detect_seeds(cloud, p: SeedParams = SeedParams(), mask: np.ndarray | None = None) -> np.ndarray:
    """Find stem centres in a horizontal cross-section. Returns (n, 3): x, y, dbh.

    `cloud` may be an xarray Dataset or an (n, 3) array.

    `mask` is an optional per-point boolean pre-screen, applied before slicing.
    Pass `novatrees.features.stem_prescreen(...)` to cluster only stem-like points:
    on the course plot that lifts recall from 0.63 to 0.77 and precision from 0.67
    to 0.87, because it separates stems standing closer together than the DBSCAN
    neighbourhood instead of merging them into one seed.
    """
    import circle_fit

    xyz = _xyz(cloud)
    if mask is not None:
        mask = np.asarray(mask, bool)
        if len(mask) != len(xyz):
            raise ValueError(f"mask ({len(mask)}) does not match points ({len(xyz)})")
        xyz = xyz[mask]

    sl = xyz[(xyz[:, 2] >= p.slice_lo) & (xyz[:, 2] < p.slice_hi)]
    if len(sl) == 0:
        return np.empty((0, 3))

    labels = DBSCAN(eps=p.eps, min_samples=p.min_samples, n_jobs=-1).fit_predict(sl[:, :2])

    # A stem is not a one-slice accident: it continues above and below breast
    # height. These two slabs are what separate stems from understory clutter,
    # low branches and the odd fence post of noise.
    lo0 = p.slice_lo - p.support_gap - p.support_band
    hi0 = p.slice_hi + p.support_gap
    below = cKDTree(xyz[(xyz[:, 2] >= lo0) & (xyz[:, 2] < lo0 + p.support_band)][:, :2])
    above = cKDTree(xyz[(xyz[:, 2] >= hi0) & (xyz[:, 2] < hi0 + p.support_band)][:, :2])

    seeds = []
    for c in range(labels.max() + 1):
        pts = sl[labels == c][:, :2]
        if len(pts) < p.min_cluster_pts:
            continue
        extent = float((pts.max(0) - pts.min(0)).max())
        if not (2 * p.min_radius <= extent <= p.max_extent):
            continue
        try:
            xc, yc, r, _sigma = circle_fit.taubinSVD(pts)
        except Exception:
            continue
        if not (p.min_radius <= r <= p.max_radius):
            continue
        probe = r + p.support_slack
        if len(below.query_ball_point([xc, yc], probe)) < p.min_support:
            continue
        if len(above.query_ball_point([xc, yc], probe)) < p.min_support:
            continue
        seeds.append((xc, yc, 2 * r))

    return np.array(seeds) if seeds else np.empty((0, 3))


def _voxel_downsample(pts: np.ndarray, voxel: float) -> np.ndarray:
    keys = np.floor(pts / voxel).astype(np.int64)
    _, idx = np.unique(keys, axis=0, return_index=True)
    return idx


def grow_instances(cloud, seeds: np.ndarray, p: GrowParams = GrowParams()) -> Result:
    """Label points by 3D Dijkstra region growing from stem seeds.

    `cloud` may be an xarray Dataset or an (n, 3) array.
    """
    xyz = _xyz(cloud)
    above_ground = xyz[:, 2] > p.ground_z  # <- step 1; see module docstring
    P = xyz[above_ground]

    idx = _voxel_downsample(P, p.voxel)
    V = P[idx]

    tree = cKDTree(V)
    d, nn = tree.query(V, k=p.k, workers=-1)

    # Edges longer than max_edge are dropped: a graph that can leap 2 m of empty
    # air is a graph that will happily leap into the neighbouring crown.
    rows = np.repeat(np.arange(len(V)), p.k - 1)
    cols = nn[:, 1:].ravel()
    w = d[:, 1:].ravel()
    m = w <= p.max_edge
    G = coo_matrix((w[m], (rows[m], cols[m])), shape=(len(V), len(V))).tocsr()

    seed_xyz = np.c_[seeds[:, 0], seeds[:, 1], np.full(len(seeds), p.seed_z)]
    _, seed_nodes = tree.query(seed_xyz, workers=-1)

    geo, _, src = dijkstra(
        G, directed=False, indices=seed_nodes, min_only=True, return_predecessors=True
    )

    node_labels = np.full(len(V), -1, np.int32)
    reached = np.isfinite(geo) & (geo <= p.max_geodesic)
    lut = {node: i for i, node in enumerate(seed_nodes)}
    node_labels[reached] = [lut.get(s, -1) for s in src[reached]]

    # Push voxel labels back onto every original point.
    labels = np.full(len(xyz), -1, np.int32)
    _, nearest = cKDTree(V).query(P, workers=-1)
    labels[above_ground] = node_labels[nearest]

    counts = np.bincount(labels[labels >= 0], minlength=len(seeds))
    stats = {
        "n_points": int(len(xyz)),
        "n_above_ground": int(above_ground.sum()),
        "n_ground_removed": int((~above_ground).sum()),
        "n_nodes": int(len(V)),
        "n_edges": int(G.nnz),
        "n_trees": int(len(seeds)),
        "nodes_reached": int(reached.sum()),
        "frac_reached": float(reached.sum() / max(len(V), 1)),
        "points_labelled": int((labels >= 0).sum()),
        "points_per_tree_min": int(counts.min()) if len(counts) else 0,
        "points_per_tree_median": int(np.median(counts)) if len(counts) else 0,
        "points_per_tree_max": int(counts.max()) if len(counts) else 0,
    }
    return Result(seeds, labels, node_labels, V, geo, stats)


def segment(
    cloud, seed_p: SeedParams = SeedParams(), grow_p: GrowParams = GrowParams()
) -> Result:
    """Full pipeline: cross-section seeds, then Dijkstra region growing."""
    seeds = detect_seeds(cloud, seed_p)
    if len(seeds) == 0:
        raise ValueError(
            "No stem seeds found. Check that Z is height-normalised and that "
            f"the slice {seed_p.slice_lo}-{seed_p.slice_hi} m contains stem points."
        )
    return grow_instances(cloud, seeds, grow_p)


def match_reference(detected: np.ndarray, reference: np.ndarray, tol: float = 0.5) -> dict:
    """Compare detected stem positions against reference seeds (XY, metres)."""
    if len(detected) == 0 or len(reference) == 0:
        return {"n_detected": len(detected), "n_reference": len(reference)}
    d_ref, _ = cKDTree(detected[:, :2]).query(reference[:, :2])
    d_det, _ = cKDTree(reference[:, :2]).query(detected[:, :2])
    hit = int((d_ref < tol).sum())
    tp = int((d_det < tol).sum())
    return {
        "n_detected": int(len(detected)),
        "n_reference": int(len(reference)),
        "reference_hit": hit,
        "recall": hit / len(reference),
        "precision": tp / len(detected),
        "median_offset": float(np.median(d_ref[d_ref < tol])) if hit else float("nan"),
    }
