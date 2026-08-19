"""Command-line entry point: LAZ in, tree-labelled LAZ out."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

from .extract import extract_trees, semantic_labels, tree_table
from .io import read_xyz, write_labelled, write_seeds
from .pipeline import GrowParams, SeedParams, detect_seeds, grow_instances, match_reference


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="nova-trees",
        description="Cross-section stem seeds + 3D Dijkstra region growing -> per-point treeID.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("input", help="height-normalised LAS/LAZ (Z above ground)")
    ap.add_argument("-o", "--outdir", default="out/trees")
    ap.add_argument("--reference", help="optional LAZ of reference stem positions, for scoring")

    g = ap.add_argument_group("ground removal")
    g.add_argument(
        "--ground-z",
        type=float,
        default=GrowParams.ground_z,
        help="drop points below this height; the graph must not run through the floor",
    )

    s = ap.add_argument_group("cross-section stem detection")
    s.add_argument("--slice-lo", type=float, default=SeedParams.slice_lo)
    s.add_argument("--slice-hi", type=float, default=SeedParams.slice_hi)
    s.add_argument("--eps", type=float, default=SeedParams.eps)
    s.add_argument("--min-samples", type=int, default=SeedParams.min_samples)
    s.add_argument("--min-support", type=int, default=SeedParams.min_support)

    d = ap.add_argument_group("dijkstra region growing")
    d.add_argument("--voxel", type=float, default=GrowParams.voxel)
    d.add_argument("--k", type=int, default=GrowParams.k)
    d.add_argument("--max-edge", type=float, default=GrowParams.max_edge)
    d.add_argument("--max-geodesic", type=float, default=None, help="cap path length from a seed")
    d.add_argument("--drop-unlabelled", action="store_true")

    x = ap.add_argument_group("per-tree extraction")
    x.add_argument(
        "--extract", action="store_true", help="write one LAZ per tree into <outdir>/individual"
    )
    x.add_argument("--min-tree-points", type=int, default=1000)
    x.add_argument(
        "--include-ground",
        action="store_true",
        help="append ground within each tree's footprint (misleading for volume)",
    )
    x.add_argument("--seeds-from", choices=["cross-section", "treeaibox"], default="cross-section")

    a = ap.parse_args(argv)

    seed_p = SeedParams(
        slice_lo=a.slice_lo,
        slice_hi=a.slice_hi,
        eps=a.eps,
        min_samples=a.min_samples,
        min_support=a.min_support,
    )
    grow_p = GrowParams(
        ground_z=a.ground_z,
        voxel=a.voxel,
        k=a.k,
        max_edge=a.max_edge,
        max_geodesic=a.max_geodesic if a.max_geodesic is not None else np.inf,
    )

    t0 = time.time()
    xyz = read_xyz(a.input)
    print(f"read {len(xyz):,} points  ({time.time() - t0:.1f}s)")

    zmin = xyz[:, 2].min()
    if zmin < -2.0 or xyz[:, 2].max() > 200:
        print(
            f"warning: Z spans {zmin:.1f}..{xyz[:, 2].max():.1f} m — this looks like "
            "absolute elevation, not normalised height. Run CSF and normalise first.",
            file=sys.stderr,
        )

    t = time.time()
    stem_mask = None
    if a.seeds_from == "treeaibox":
        from .treeaibox import treeaibox_seeds

        seeds, stem_mask, _timings = treeaibox_seeds(xyz)
    else:
        seeds = detect_seeds(xyz, seed_p)
    print(f"stems detected: {len(seeds)}  ({time.time() - t:.1f}s)")
    if len(seeds) == 0:
        print("no stems found; nothing to grow", file=sys.stderr)
        return 1
    print(f"  DBH  min {seeds[:, 2].min():.3f}  median {np.median(seeds[:, 2]):.3f}  max {seeds[:, 2].max():.3f} m")

    t = time.time()
    res = grow_instances(xyz, seeds, grow_p)
    st = res.stats
    print(f"region growing: {time.time() - t:.1f}s")
    print(f"  ground removed : {st['n_ground_removed']:,} points below {a.ground_z} m")
    print(f"  graph          : {st['n_nodes']:,} nodes / {st['n_edges']:,} edges")
    print(f"  reached        : {st['nodes_reached']:,} nodes ({100 * st['frac_reached']:.1f}%)")
    print(f"  labelled       : {st['points_labelled']:,} of {st['n_points']:,} points")
    print(
        f"  points/tree    : min {st['points_per_tree_min']:,} "
        f"median {st['points_per_tree_median']:,} max {st['points_per_tree_max']:,}"
    )

    if a.reference:
        ref = read_xyz(a.reference)
        m = match_reference(seeds, ref)
        print(
            f"  vs reference   : {m['reference_hit']}/{m['n_reference']} hit "
            f"(recall {m['recall']:.2f}, precision {m['precision']:.2f}, "
            f"median offset {m['median_offset']:.2f} m)"
        )

    semantic = semantic_labels(xyz, res.labels, seeds, ground_z=a.ground_z)
    table = tree_table(xyz, res.labels, seeds, semantic)

    outdir = Path(a.outdir)
    stem = Path(a.input).stem
    cloud_out = outdir / f"{stem}_treeid.laz"
    seeds_out = outdir / f"{stem}_stem_seeds.laz"
    n = write_labelled(a.input, cloud_out, res.labels, drop_unlabelled=a.drop_unlabelled)
    write_seeds(seeds_out, seeds, z=grow_p.seed_z, like=a.input)
    table_out = outdir / f"{stem}_trees.csv"
    table.to_csv(table_out, index=False)
    print(f"\nwrote {n:,} points -> {cloud_out}")
    print(f"wrote {len(seeds)} seeds  -> {seeds_out}")
    print(f"wrote {len(table)} rows   -> {table_out}")

    if a.extract:
        t = time.time()
        paths = extract_trees(
            xyz,
            res.labels,
            outdir / "individual",
            source=a.input,
            semantic=semantic,
            min_points=a.min_tree_points,
            include_ground=a.include_ground,
        )
        print(
            f"wrote {len(paths)} per-tree files -> {outdir / 'individual'} "
            f"({time.time() - t:.1f}s)"
        )

    print("\nIn CloudCompare: open the cloud and colour by 'treeID_dj'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
