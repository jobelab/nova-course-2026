"""Command-line entry point: LAZ in, tree-labelled LAZ out."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

from .extract import extract_trees, semantic_labels, tree_table
from .features import StemScoreParams, stem_prescreen
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

    w = ap.add_argument_group("weighted stem pre-screen (course demo phase 2)")
    w.add_argument(
        "--prescreen",
        type=float,
        default=None,
        metavar="PCT",
        help="keep this %% of the most stem-like points before clustering "
        "(lower is tighter; omit to disable). Needs a reflectance field for the "
        "reflectance term.",
    )
    w.add_argument("--normals-k", type=int, default=StemScoreParams.k)
    w.add_argument("--w-vertical", type=float, default=StemScoreParams.w_vertical)
    w.add_argument("--w-reflectance", type=float, default=StemScoreParams.w_reflectance)
    w.add_argument("--band-lo", type=float, default=0.7, help="bottom of the feature band")
    w.add_argument("--band-hi", type=float, default=2.0, help="top of the feature band")

    tp = ap.add_argument_group("stem taper")
    tp.add_argument("--taper", action="store_true", help="reconstruct a taper curve per tree")

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
        prescreen_mask = None
        if a.prescreen is not None:
            refl = None
            try:
                import laspy

                f = laspy.read(a.input)
                if "reflectance" in f.point_format.dimension_names:
                    refl = np.asarray(f.reflectance)
            except Exception:
                pass
            if refl is None:
                print(
                    "note: no reflectance field; screening on verticality alone",
                    file=sys.stderr,
                )
            band = (xyz[:, 2] >= a.band_lo) & (xyz[:, 2] < a.band_hi)
            sp = StemScoreParams(
                k=a.normals_k,
                w_vertical=a.w_vertical,
                w_reflectance=a.w_reflectance if refl is not None else 0.0,
                w_radial=0.0,  # no seeds yet, so the radial term cannot apply
                prescreen_pct=a.prescreen,
            )
            keep = stem_prescreen(
                xyz[band], reflectance=None if refl is None else refl[band], p=sp
            )
            prescreen_mask = np.zeros(len(xyz), bool)
            prescreen_mask[np.flatnonzero(band)[keep]] = True
            print(
                f"pre-screen: kept {prescreen_mask.sum():,} of {int(band.sum()):,} "
                f"band points ({a.prescreen:g}%)"
            )
        seeds = detect_seeds(xyz, seed_p, mask=prescreen_mask)
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

    if a.taper:
        from .taper import TaperParams, taper_curve

        t = time.time()
        rows = []
        for k in range(len(seeds)):
            sel = (res.labels == k) & (semantic == 1)
            if sel.sum() < TaperParams.min_points:
                continue
            r = taper_curve(xyz[sel], TaperParams())
            rows.append(
                {
                    "treeID": k + 1,
                    "dbh_taper_m": r.dbh,
                    "dbh_seed_m": float(seeds[k, 2]),
                    "volume_m3": r.volume,
                    "slices": r.stats.get("n_slices", 0),
                    "accepted": r.stats.get("n_accepted", 0),
                }
            )
        if rows:
            import pandas as pd

            taper_out = outdir / f"{stem}_taper.csv"
            pd.DataFrame(rows).to_csv(taper_out, index=False)
            print(f"wrote {len(rows)} taper curves -> {taper_out} ({time.time() - t:.1f}s)")

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
