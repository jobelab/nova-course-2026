"""Tree instance segmentation: cross-section seeds + 3D Dijkstra, vs CHM watershed.

Two ways to cut a TLS plot into individual trees, scored against the reference
`treeid` labels that ship with the course cloud, and exported so the same result
can be inspected in CloudCompare.

    A  CHM watershed        top-down. A Python port of PCT's crown detection
                            (Yrttimaa, pc_detect_tree_crowns_v2.m).
    B  cross-section seeds  bottom-up. Detect stems in a slice at breast height,
       + 3D Dijkstra        then grow regions along a kNN graph of the points.

Run:  uv run marimo edit notebooks/01_tree_instance_segmentation.py
"""

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md(
        r"""
        # Tree instance segmentation on a TLS plot

        Same cloud, two philosophies.

        **A — CHM watershed (top-down).** Rasterise the canopy, smooth it, find the
        local maxima, let watershed basins grow down from those tree tops. This is a
        port of the crown-detection stage of Tuomas Yrttimaa's *Point-Cloud-Tools*
        (PCT) — the MATLAB toolbox behind `PCT_demo_installer.exe` in the course
        material.

        **B — cross-section seeds + 3D Dijkstra (bottom-up).** Slice the cloud at
        breast height, cluster the slice, fit circles, keep what looks like a stem.
        Those centres become seeds. Then every point is assigned to whichever seed is
        closest *through the point cloud* — geodesic distance along a nearest-neighbour
        graph, not straight-line distance.

        Both are scored against the per-point `treeid` field already in the cloud.

        > **Remove the ground first.** This is not housekeeping. The graph in method B
        > walks between neighbouring points, and the forest floor is one continuous
        > sheet touching the base of every stem. Leave it in and the cheapest path from
        > one tree's seed to another tree's crown runs straight through the ground —
        > labels bleed across the whole plot.
        """
    )
    return


@app.cell
def _():
    from pathlib import Path

    import altair as alt
    import laspy
    import numpy as np
    import pandas as pd

    from novatrees import (
        ChmParams,
        CsfParams,
        GrowParams,
        SeedParams,
        chm_segment,
        csf_ground,
        detect_seeds,
        grow_instances,
        instance_scores,
        normalize_heights,
        read_cloud,
        write_cloud,
    )

    REPO = Path(__file__).resolve().parents[1]
    RAW = REPO / "PCT_demo" / "PCT_demo" / "crsot_mixed_stand.laz"
    CLOUD = REPO / "Day03_ToumasYrttima" / "crsot_mixed_stand_hnorm.laz"
    OUTDIR = REPO / "out" / "trees"
    return (
        CLOUD,
        RAW,
        ChmParams,
        CsfParams,
        GrowParams,
        OUTDIR,
        Path,
        SeedParams,
        alt,
        chm_segment,
        csf_ground,
        detect_seeds,
        grow_instances,
        instance_scores,
        laspy,
        normalize_heights,
        np,
        pd,
        read_cloud,
        write_cloud,
    )


@app.cell
def _(CLOUD, laspy, mo, np):
    mo.stop(
        not CLOUD.exists(),
        mo.md(f"**Missing cloud.** Expected `{CLOUD}` — re-fetch the course data."),
    )

    ds = read_cloud(CLOUD)
    xyz = np.column_stack([ds.x.values, ds.y.values, ds.z.values])
    reference = ds.treeid.values.astype(np.int64)

    n_ref = len(np.unique(reference[reference > 0]))
    mo.md(
        f"""
        **{CLOUD.name}** — {len(xyz):,} points, Z from {xyz[:, 2].min():.2f} to
        {xyz[:, 2].max():.2f} m (height-normalised), extent
        {np.ptp(xyz[:, 0]):.1f} x {np.ptp(xyz[:, 1]):.1f} m.
        Reference labelling: **{n_ref} tree instances**,
        {(reference == 0).sum():,} points left unassigned.

        Carried as an `xarray.Dataset` over a `point` dimension, so every per-point
        attribute the file already had — `{"`, `".join(str(v) for v in ds.data_vars)}` —
        stays named and aligned:
        """
    )
    return ds, n_ref, reference, xyz


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Why this stand is hard

        Most of the trees never reach the canopy. That single fact decides which method
        can work here, so it is worth seeing before touching any parameters.
        """
    )
    return


@app.cell
def _(alt, np, pd, reference, xyz):
    _ids = np.unique(reference[reference > 0])
    _h = np.array([xyz[reference == t, 2].max() for t in _ids])
    tree_heights = pd.DataFrame({"treeid": _ids, "height": _h})

    _chart = (
        alt.Chart(tree_heights)
        .mark_bar(color="#4c78a8")
        .encode(
            x=alt.X("height:Q", bin=alt.Bin(step=2), title="tree height (m)"),
            y=alt.Y("count()", title="trees"),
            tooltip=["count()"],
        )
        .properties(height=200, title="Reference tree heights — most of the stand is suppressed")
    )
    _chart
    return (tree_heights,)


@app.cell
def _(mo, np, tree_heights, xyz):
    _under = int((tree_heights.height < 10).sum())
    mo.md(
        f"""
        **{_under} of {len(tree_heights)} trees are under 10 m**, with a canopy reaching
        {xyz[:, 2].max():.1f} m and a median tree only
        {np.median(tree_heights.height):.1f} m tall.

        A canopy height model records the *highest* return per cell, so a suppressed tree
        under a taller neighbour leaves no trace in it at all. Method A cannot find those
        trees no matter how it is tuned — not a bug in the port, a property of working
        from a raster of the canopy surface. Method B looks for stems at breast height,
        where a suppressed tree is just as visible as a dominant one.
        """
    )
    return


@app.cell
def _(mo):
    mo.md(r"""## Ground removal""")
    return


@app.cell
def _(mo):
    ground_z = mo.ui.slider(
        0.0, 1.0, value=0.30, step=0.05, label="drop points below (m)", show_value=True
    )
    ground_z
    return (ground_z,)


@app.cell
def _(alt, ground_z, mo, np, pd, xyz):
    _above = xyz[:, 2] > ground_z.value
    # Bin in numpy, not in Vega: shipping 15 M rows to the browser is how you
    # hang a notebook. Altair refuses anything over 20 000 rows anyway.
    _counts, _edges = np.histogram(xyz[:, 2], bins=np.arange(-1, xyz[:, 2].max() + 0.5, 0.5))
    _prof = pd.DataFrame({"z": _edges[:-1], "points": _counts})
    _chart = (
        alt.Chart(_prof)
        .mark_bar(color="#54a24b")
        .encode(
            y=alt.Y("z:Q", title="height (m)", scale=alt.Scale(zero=False)),
            x=alt.X("points:Q", title="points"),
            tooltip=["z:Q", "points:Q"],
        )
        .properties(height=260, title="Vertical point distribution")
    )
    _rule = alt.Chart(pd.DataFrame({"z": [ground_z.value]})).mark_rule(
        color="crimson", strokeDash=[4, 4], size=2
    ).encode(y="z:Q")

    mo.vstack(
        [
            _chart + _rule,
            mo.md(
                f"Removing **{(~_above).sum():,}** points "
                f"({100 * (~_above).mean():.1f}%), keeping **{_above.sum():,}**."
            ),
        ]
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Method A — CHM watershed (PCT port)

        `pc2dem(max)` → gaussian(σ=1) → local-maxima tree tops → marker-controlled
        watershed → drop crowns below `min_crown_area`. Defaults are PCT's own
        (`chmPixelSize = 0.2`, `minCrownArea = 2`, `minTreeHeight = 2`).
        """
    )
    return


@app.cell
def _(mo):
    chm_px = mo.ui.slider(0.1, 0.5, value=0.2, step=0.05, label="CHM pixel (m)", show_value=True)
    chm_dist = mo.ui.slider(
        0.3, 2.0, value=0.6, step=0.1, label="min tree-top spacing (m)", show_value=True
    )
    chm_minh = mo.ui.slider(1.0, 8.0, value=2.0, step=0.5, label="min tree height (m)", show_value=True)
    mo.vstack([chm_px, chm_dist, chm_minh])
    return chm_dist, chm_minh, chm_px


@app.cell
def _(ChmParams, chm_dist, chm_minh, chm_px, chm_segment, ground_z, xyz):
    result_a = chm_segment(
        xyz,
        ChmParams(
            pixel_size=chm_px.value,
            min_distance=chm_dist.value,
            min_tree_height=chm_minh.value,
            ground_z=ground_z.value,
        ),
    )
    labels_a = result_a["labels"]
    return labels_a, result_a


@app.cell
def _(alt, mo, np, pd, result_a):
    _chm = result_a["chm"]  # xarray DataArray, real x/y coords
    _step = max(1, _chm.sizes["y"] // 120)
    _sub = _chm.isel(y=slice(None, None, _step), x=slice(None, None, _step))
    _df = _sub.to_dataframe(name="height").reset_index()

    _heat = (
        alt.Chart(_df)
        .mark_rect()
        .encode(
            x=alt.X("x:O", axis=None),
            y=alt.Y("y:O", axis=None, sort="descending"),
            color=alt.Color("height:Q", scale=alt.Scale(scheme="viridis"), title="CHM (m)"),
            tooltip=["height:Q"],
        )
        .properties(width=340, height=340, title="Canopy height model")
    )
    mo.vstack(
        [
            _heat,
            mo.md(
                f"**{result_a['stats']['n_trees']} crowns** kept from "
                f"{result_a['stats']['n_tops_detected']} detected tops. "
                f"CHM is a `DataArray` of {dict(_chm.sizes)} at "
                f"{_chm.attrs['pixel_size']} m."
            ),
        ]
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Method B — cross-section seeds

        Slice at breast height, cluster in 2D, fit a circle per cluster, and keep only
        clusters that are stem-shaped *and* vertically continuous — points must also
        exist in a slab above and a slab below. That continuity check is what rejects
        understory clutter and low branches.
        """
    )
    return


@app.cell
def _(mo):
    slice_lo = mo.ui.slider(0.5, 2.5, value=1.15, step=0.05, label="slice bottom (m)", show_value=True)
    slice_hi = mo.ui.slider(0.6, 3.0, value=1.45, step=0.05, label="slice top (m)", show_value=True)
    eps = mo.ui.slider(0.03, 0.20, value=0.08, step=0.01, label="DBSCAN eps (m)", show_value=True)
    min_support = mo.ui.slider(0, 60, value=15, step=5, label="min vertical support", show_value=True)
    mo.vstack([slice_lo, slice_hi, eps, min_support])
    return eps, min_support, slice_hi, slice_lo


@app.cell
def _(SeedParams, detect_seeds, eps, min_support, slice_hi, slice_lo, xyz):
    seed_params = SeedParams(
        slice_lo=slice_lo.value,
        slice_hi=max(slice_hi.value, slice_lo.value + 0.05),
        eps=eps.value,
        min_support=min_support.value,
    )
    seeds = detect_seeds(xyz, seed_params)
    return seed_params, seeds


@app.cell
def _(alt, mo, np, pd, seed_params, seeds, xyz):
    _sl = xyz[(xyz[:, 2] >= seed_params.slice_lo) & (xyz[:, 2] < seed_params.slice_hi)]
    _s = _sl[:: max(1, len(_sl) // 12000)]
    _pts = pd.DataFrame({"x": _s[:, 0], "y": _s[:, 1]})
    _base = (
        alt.Chart(_pts)
        .mark_circle(size=2, opacity=0.25, color="#888")
        .encode(x=alt.X("x:Q", scale=alt.Scale(zero=False)), y=alt.Y("y:Q", scale=alt.Scale(zero=False)))
        .properties(width=380, height=380, title="Breast-height slice with detected stems")
    )
    _sd = pd.DataFrame({"x": seeds[:, 0], "y": seeds[:, 1], "dbh": seeds[:, 2]})
    _mark = (
        alt.Chart(_sd)
        .mark_point(color="crimson", filled=False, strokeWidth=2)
        .encode(x="x:Q", y="y:Q", size=alt.Size("dbh:Q", scale=alt.Scale(range=[30, 400]), title="DBH (m)"), tooltip=["dbh:Q"])
    )
    mo.vstack(
        [
            _base + _mark,
            mo.md(
                f"**{len(seeds)} stems** — DBH median "
                f"{np.median(seeds[:, 2]) if len(seeds) else float('nan'):.3f} m, "
                f"range {seeds[:, 2].min() if len(seeds) else 0:.3f}–"
                f"{seeds[:, 2].max() if len(seeds) else 0:.3f} m."
            ),
        ]
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Method B — 3D Dijkstra region growing

        A kNN graph over the voxel-downsampled above-ground points, edges weighted by
        distance and refused beyond `max_edge`. Multi-source Dijkstra from the stem
        seeds then labels every node with the seed it is geodesically nearest to.

        `max_edge` is the parameter that matters: a graph allowed to leap wide gaps will
        happily leap into a neighbouring crown.
        """
    )
    return


@app.cell
def _(mo):
    voxel = mo.ui.slider(0.05, 0.30, value=0.10, step=0.05, label="voxel size (m)", show_value=True)
    max_edge = mo.ui.slider(0.2, 1.5, value=0.5, step=0.1, label="max edge length (m)", show_value=True)
    knn = mo.ui.slider(5, 20, value=9, step=1, label="kNN", show_value=True)
    run = mo.ui.run_button(label="Run region growing")
    mo.vstack([voxel, max_edge, knn, run])
    return knn, max_edge, run, voxel


@app.cell
def _(GrowParams, grow_instances, ground_z, knn, max_edge, mo, run, seeds, voxel, xyz):
    mo.stop(not run.value, mo.md("*Set the parameters above, then press **Run region growing**.*"))
    mo.stop(len(seeds) == 0, mo.md("**No seeds detected** — loosen the detection parameters."))

    result_b = grow_instances(
        xyz,
        seeds,
        GrowParams(
            ground_z=ground_z.value, voxel=voxel.value, k=knn.value, max_edge=max_edge.value
        ),
    )
    labels_b = result_b.labels
    mo.md(
        f"""
        Graph: **{result_b.stats['n_nodes']:,} nodes**, {result_b.stats['n_edges']:,} edges.
        Reached {100 * result_b.stats['frac_reached']:.1f}% of nodes;
        labelled {result_b.stats['points_labelled']:,} points across
        {result_b.stats['n_trees']} trees.
        """
    )
    return labels_b, result_b


@app.cell
def _(mo):
    mo.md(r"""## Scored against the reference labels""")
    return


@app.cell
def _(instance_scores, labels_a, labels_b, mo, pd, reference):
    _rows = []
    for _name, _lab in (("A  CHM watershed", labels_a), ("B  XS + Dijkstra", labels_b)):
        _s = instance_scores(_lab, reference)
        _rows.append(
            {
                "method": _name,
                "trees found": _s["n_pred"],
                "matched": _s["matched"],
                "recall": round(_s["recall"], 2),
                "precision": round(_s["precision"], 2),
                "mean IoU": round(_s["mean_iou_matched"], 3),
                "missed": _s["missed"],
                "over-seg": _s["over_segmented_refs"],
                "under-seg": _s["under_segmented_preds"],
            }
        )
    scores = pd.DataFrame(_rows)
    mo.vstack(
        [
            mo.ui.table(scores, selection=None),
            mo.md(
                """
                *matched* = predicted instances hitting a reference tree at IoU ≥ 0.5.
                *over-seg* counts reference trees split across several predictions;
                *under-seg* counts predictions swallowing several reference trees.
                """
            ),
        ]
    )
    return (scores,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Export for CloudCompare

        Writes both labellings as extra scalar fields so the two methods and the
        reference can be flipped between in one viewer.

        Open the result and colour by **`treeID_dj`** (method B), **`treeID_chm`**
        (method A) or the original **`treeid`** (reference). The cloud already carries
        `treeid`, so nothing is overwritten.
        """
    )
    return


@app.cell
def _(mo):
    export = mo.ui.run_button(label="Write LAZ for CloudCompare")
    export
    return (export,)


@app.cell
def _(CLOUD, OUTDIR, export, labels_a, labels_b, laspy, mo, np, seeds):
    mo.stop(not export.value, mo.md("*Press the button to write the files.*"))

    OUTDIR.mkdir(parents=True, exist_ok=True)
    _f = laspy.read(str(CLOUD))
    _f.add_extra_dim(laspy.ExtraBytesParams(name="treeID_dj", type=np.int32))
    _f.add_extra_dim(laspy.ExtraBytesParams(name="treeID_chm", type=np.int32))
    _f.treeID_dj = (labels_b + 1).astype(np.int32)
    _f.treeID_chm = (labels_a + 1).astype(np.int32)
    _out = OUTDIR / "crsot_mixed_stand_compare.laz"
    _f.write(str(_out))

    from novatrees import write_seeds

    _seedfile = OUTDIR / "crsot_mixed_stand_stem_seeds.laz"
    write_seeds(_seedfile, seeds, like=str(CLOUD))

    mo.md(
        f"""
        Wrote **{len(_f.points):,} points** → `{_out.relative_to(OUTDIR.parents[1])}`
        and {len(seeds)} stem seeds → `{_seedfile.relative_to(OUTDIR.parents[1])}`.

        ```
        cloudcompare {_out}
        ```
        """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ---

        ### Credit

        Method A ports the crown-detection stage of **Point-Cloud-Tools** by
        Dr. Tuomas Yrttimaa (University of Eastern Finland), CC BY 4.0 —
        [zenodo.5779288](https://doi.org/10.5281/zenodo.5779288),
        [Yrttimaa et al. 2019](https://doi.org/10.3390/rs11121423),
        [2020](https://doi.org/10.1016/j.isprsjprs.2020.08.017).

        Note what is being compared: PCT uses crown segments as a *partition* step and
        then classifies stem points within each segment, so this is one stage of his
        pipeline against a complete alternative, not the whole toolbox.
        """
    )
    return


if __name__ == "__main__":
    app.run()
