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

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
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
    """)
    return


@app.cell(hide_code=True)
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
        extract_trees,
        grow_instances,
        instance_scores,
        normalize_heights,
        read_cloud,
        semantic_labels,
        tree_table,
        write_cloud,
    )

    REPO = Path(__file__).resolve().parents[1]
    RAW = REPO / "PCT_demo" / "PCT_demo" / "crsot_mixed_stand.laz"
    CLOUD = REPO / "Day03_ToumasYrttima" / "crsot_mixed_stand_hnorm.laz"
    OUTDIR = REPO / "out" / "trees"
    return (
        CLOUD,
        ChmParams,
        GrowParams,
        OUTDIR,
        SeedParams,
        alt,
        chm_segment,
        detect_seeds,
        extract_trees,
        grow_instances,
        instance_scores,
        laspy,
        np,
        pd,
        read_cloud,
        semantic_labels,
        tree_table,
    )


@app.cell(hide_code=True)
def _(CLOUD, mo, np, read_cloud):
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
    return reference, xyz


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Why this stand is hard

    Most of the trees never reach the canopy. That single fact decides which method
    can work here, so it is worth seeing before touching any parameters.
    """)
    return


@app.cell(hide_code=True)
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


@app.cell(hide_code=True)
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
    mo.md(r"""
    ## Ground removal
    """)
    return


@app.cell
def _(mo):
    ground_z = mo.ui.slider(
        0.0, 1.0, value=0.30, step=0.05, label="drop points below (m)", show_value=True
    )
    ground_z
    return (ground_z,)


@app.cell(hide_code=True)
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


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Method A — CHM watershed (PCT port)

    `pc2dem(max)` → gaussian(σ=1) → local-maxima tree tops → marker-controlled
    watershed → drop crowns below `min_crown_area`. Defaults are PCT's own
    (`chmPixelSize = 0.2`, `minCrownArea = 2`, `minTreeHeight = 2`).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    chm_px = mo.ui.slider(0.1, 0.5, value=0.2, step=0.05, label="CHM pixel (m)", show_value=True)
    chm_dist = mo.ui.slider(
        0.3, 2.0, value=0.6, step=0.1, label="min tree-top spacing (m)", show_value=True
    )
    chm_minh = mo.ui.slider(1.0, 8.0, value=2.0, step=0.5, label="min tree height (m)", show_value=True)
    mo.vstack([chm_px, chm_dist, chm_minh])
    return chm_dist, chm_minh, chm_px


@app.cell(hide_code=True)
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


@app.cell(hide_code=True)
def _(alt, mo, result_a):
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


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Method B — cross-section seeds

    Slice at breast height, cluster in 2D, fit a circle per cluster, and keep only
    clusters that are stem-shaped *and* vertically continuous — points must also
    exist in a slab above and a slab below. That continuity check is what rejects
    understory clutter and low branches.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    slice_lo = mo.ui.slider(0.5, 2.5, value=1.15, step=0.05, label="slice bottom (m)", show_value=True)
    slice_hi = mo.ui.slider(0.6, 3.0, value=1.45, step=0.05, label="slice top (m)", show_value=True)
    eps = mo.ui.slider(0.03, 0.20, value=0.08, step=0.01, label="DBSCAN eps (m)", show_value=True)
    min_support = mo.ui.slider(0, 60, value=15, step=5, label="min vertical support", show_value=True)
    mo.vstack([slice_lo, slice_hi, eps, min_support])
    return eps, min_support, slice_hi, slice_lo


@app.cell(hide_code=True)
def _(SeedParams, detect_seeds, eps, min_support, slice_hi, slice_lo, xyz):
    seed_params = SeedParams(
        slice_lo=slice_lo.value,
        slice_hi=max(slice_hi.value, slice_lo.value + 0.05),
        eps=eps.value,
        min_support=min_support.value,
    )
    seeds = detect_seeds(xyz, seed_params)
    return seed_params, seeds


@app.cell(hide_code=True)
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


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Method B — 3D Dijkstra region growing

    A kNN graph over the voxel-downsampled above-ground points, edges weighted by
    distance and refused beyond $d_{\max}$ (`max_edge`):

    $$w(u,v) =
      \begin{cases}
        \lVert \mathbf{p}_{u} - \mathbf{p}_{v} \rVert_{2},
          & v \in \mathrm{kNN}_{k}(u) \ \wedge\ \lVert \mathbf{p}_{u} - \mathbf{p}_{v} \rVert_{2} \le d_{\max} \\
        \infty, & \text{otherwise}
      \end{cases}$$

    Multi-source Dijkstra then gives each node the label of its geodesically nearest
    seed — a **geodesic Voronoi partition**:

    $$d_{g}(s, x) = \min_{\pi \in \Pi(s,x)} \sum_{(a,b) \in \pi} w(a,b),
      \qquad \ell(x) = \arg\min_{s \in S} d_{g}(s, x)$$

    $d_{\max}$ is the parameter that matters: a graph allowed to leap wide gaps will
    happily leap into a neighbouring crown. Distance *through the tree*, rather than
    straight-line, is what keeps a low branch with the trunk it hangs from.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    voxel = mo.ui.slider(0.05, 0.30, value=0.10, step=0.05, label="voxel size (m)", show_value=True)
    max_edge = mo.ui.slider(0.2, 1.5, value=0.5, step=0.1, label="max edge length (m)", show_value=True)
    knn = mo.ui.slider(5, 20, value=9, step=1, label="kNN", show_value=True)
    run = mo.ui.run_button(label="Run region growing")
    mo.vstack([voxel, max_edge, knn, run])
    return knn, max_edge, run, voxel


@app.cell(hide_code=True)
def _(
    GrowParams,
    ground_z,
    grow_instances,
    knn,
    max_edge,
    mo,
    run,
    seeds,
    voxel,
    xyz,
):
    # `labels_b` is always defined, even before the button is pressed. Using
    # mo.stop here instead would halt this cell, and every cell downstream would
    # report "ancestor stopped" rather than saying what to do about it.
    if not run.value:
        labels_b = None
        _out = mo.md("*Set the parameters above, then press **Run region growing**.*")
    elif len(seeds) == 0:
        labels_b = None
        _out = mo.md("**No seeds detected** — loosen the detection parameters.")
    else:
        _res = grow_instances(
            xyz,
            seeds,
            GrowParams(
                ground_z=ground_z.value, voxel=voxel.value, k=knn.value, max_edge=max_edge.value
            ),
        )
        labels_b = _res.labels
        _out = mo.md(
            f"""
            Graph: **{_res.stats['n_nodes']:,} nodes**, {_res.stats['n_edges']:,} edges.
            Reached {100 * _res.stats['frac_reached']:.1f}% of nodes;
            labelled {_res.stats['points_labelled']:,} points across
            {_res.stats['n_trees']} trees.
            """
        )
    _out
    return (labels_b,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Look at it in 3D

    Drag to rotate, scroll to zoom. Points are subsampled for the browser — the
    full 15.6 M would not survive the trip — but the segmentation shown is the real
    one, sampled uniformly.

    Flip between the two methods and the reference to see *where* they disagree.
    The give-away for method A is whole understory trees painted the colour of the
    dominant above them; for method B it is a crown that reaches across into its
    neighbour.
    """)
    return


@app.cell
def _(mo):
    which = mo.ui.dropdown(
        {"B — cross-section + Dijkstra": "b", "A — CHM watershed": "a", "reference treeid": "ref"},
        value="B — cross-section + Dijkstra",
        label="colour by",
    )
    n_show = mo.ui.slider(
        20_000, 200_000, value=60_000, step=20_000, label="points shown", show_value=True
    )
    hide_unlabelled = mo.ui.checkbox(value=True, label="hide unlabelled points")
    azim = mo.ui.slider(-180, 180, value=-60, step=5, label="azimuth", show_value=True)
    elev = mo.ui.slider(0, 89, value=18, step=1, label="elevation", show_value=True)
    mo.vstack([which, n_show, hide_unlabelled, azim, elev])
    return azim, elev, hide_unlabelled, n_show, which


@app.cell(hide_code=True)
def _(
    azim,
    elev,
    hide_unlabelled,
    labels_a,
    labels_b,
    n_show,
    np,
    reference,
    which,
    xyz,
):
    import matplotlib
    matplotlib.use("Agg")           # render server-side to a PNG; no JS, no WebGL
    import matplotlib.pyplot as _plt

    _avail = {"a": labels_a + 1, "ref": reference}
    if labels_b is not None:
        _avail["b"] = labels_b + 1
    _key = which.value if which.value in _avail else "a"
    _lab = _avail[_key]

    _keep = np.ones(len(xyz), bool) if not hide_unlabelled.value else (_lab > 0)
    _idx = np.flatnonzero(_keep)
    if len(_idx) > n_show.value:
        _idx = _idx[:: max(1, len(_idx) // n_show.value)][: n_show.value]

    # Metres from the plot corner, not UTM: matplotlib is float64 throughout so this
    # is cosmetic here, but it keeps the axes readable and matches the export.
    _o = xyz[:, :2].min(axis=0)
    _px, _py, _pz = xyz[_idx, 0] - _o[0], xyz[_idx, 1] - _o[1], xyz[_idx, 2]
    _l = _lab[_idx]

    # Spread neighbouring ids across the colormap so adjacent trees contrast.
    _uniq = np.unique(_l)
    _shuf = np.zeros(int(_uniq.max()) + 1, int)
    _shuf[_uniq] = (np.arange(len(_uniq)) * 7919) % max(len(_uniq), 1)
    _c = _plt.get_cmap("turbo")(_shuf[_l] / max(_shuf.max(), 1))
    _c[_l == 0] = (0.75, 0.75, 0.75, 1.0)          # unassigned stays grey

    _fig3d = _plt.figure(figsize=(11, 5.2), dpi=110)

    _ax = _fig3d.add_subplot(1, 2, 1, projection="3d")
    _ax.scatter(_px, _py, _pz, s=0.4, c=_c, linewidths=0, depthshade=False)
    _ax.view_init(elev=elev.value, azim=azim.value)
    _ax.set_box_aspect((np.ptp(_px), np.ptp(_py), np.ptp(_pz)))
    _ax.set_xlabel("x (m)"); _ax.set_ylabel("y (m)"); _ax.set_zlabel("height (m)")
    _ax.set_title(f"{_key.upper()} — {len(_idx):,} points, {len(_uniq[_uniq > 0])} trees")

    _ax2 = _fig3d.add_subplot(1, 2, 2)
    _ax2.scatter(_px, _py, s=0.4, c=_c, linewidths=0)
    _ax2.set_aspect("equal")
    _ax2.set_xlabel("x (m)"); _ax2.set_ylabel("y (m)")
    _ax2.set_title("plan view")

    _fig3d.tight_layout()
    _fig3d
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Scored against the reference labels
    """)
    return


@app.cell(hide_code=True)
def _(instance_scores, labels_a, labels_b, mo, pd, reference):
    _methods = [("A  CHM watershed", labels_a)]
    if labels_b is not None:
        _methods.append(("B  XS + Dijkstra", labels_b))

    _rows = []
    for _name, _lab in _methods:
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
                r"""
                Instances are sets of points, so overlap is intersection over union:

                $$\mathrm{IoU}(P_{i}, R_{j}) =
                  \frac{\lvert P_{i} \cap R_{j} \rvert}{\lvert P_{i} \cup R_{j} \rvert},
                  \qquad
                  \mathrm{precision} = \frac{\mathrm{TP}}{\lvert \hat{\mathcal{T}} \rvert},
                  \qquad
                  \mathrm{recall} = \frac{\mathrm{TP}}{\lvert \mathcal{T} \rvert}$$

                *matched* counts predictions hitting a reference tree at
                $\mathrm{IoU} \ge 0.5$, paired greedily and one-to-one. *over-seg* counts
                reference trees split across several predictions; *under-seg* counts
                predictions swallowing several reference trees — the two failure modes
                precision and recall hide.
                """
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Pull individual trees out of the stand

    Instance ids answer *which tree*. To lift one tree out whole you also need
    *which part*, so a semantic labelling runs alongside:

    | | |
    |---|---|
    | 0 | ground |
    | 1 | stem — within the fitted radius of the tree's own vertical axis |
    | 2 | foliage — everything else belonging to the tree |

    Together those two labellings are a **panoptic** result: a class for every
    point, and an instance id for every point that belongs to a countable object.

    Ground deliberately gets **no** tree id. A patch of forest floor does not belong
    to the tree standing on it in any measurable sense, and assigning it inflates
    every per-tree statistic computed downstream.
    """)
    return


@app.cell(hide_code=True)
def _(labels_b, mo, seeds, semantic_labels, tree_table, xyz):
    if labels_b is None:
        semantic, trees = None, None
        _tbl = mo.md("*Run region growing first — the per-tree table needs its labels.*")
    else:
        semantic = semantic_labels(xyz, labels_b, seeds, ground_z=0.30)
        trees = tree_table(xyz, labels_b, seeds, semantic)
        _tbl = mo.vstack(
            [
                mo.ui.table(
                    trees.sort_values("points", ascending=False).round(
                        {"x": 2, "y": 2, "dbh_m": 3, "height_m": 2}
                    ),
                    selection=None,
                ),
                mo.md(
                    f"**{len(trees)} trees.** DBH and height come from the segmentation itself."
                ),
            ]
        )
    _tbl
    return semantic, trees


@app.cell
def _(mo):
    min_pts = mo.ui.slider(
        1000, 50_000, value=20_000, step=1000, label="minimum points per tree", show_value=True
    )
    with_ground = mo.ui.checkbox(value=False, label="include ground under each tree")
    do_extract = mo.ui.run_button(label="Write one LAZ per tree")
    mo.vstack([min_pts, with_ground, do_extract])
    return do_extract, min_pts, with_ground


@app.cell
def _(
    CLOUD,
    OUTDIR,
    do_extract,
    extract_trees,
    labels_b,
    min_pts,
    mo,
    semantic,
    with_ground,
    xyz,
):
    mo.stop(
        semantic is None,
        mo.md("*Run region growing first — extraction needs the tree labels.*"),
    )
    mo.stop(not do_extract.value, mo.md("*Press to write per-tree files.*"))

    _paths = extract_trees(
        xyz,
        labels_b,
        OUTDIR / "individual",
        source=CLOUD,
        semantic=semantic,
        min_points=min_pts.value,
        include_ground=with_ground.value,
    )
    mo.md(
        f"""
        Wrote **{len(_paths)} trees** to `{OUTDIR / "individual"}`.

        LAS classification codes are set on the way out — 2 ground, 5 stem, 4 foliage —
        so each file opens in CloudCompare already split by class.

        ```
        cloudcompare {OUTDIR / "individual"}/tree_001.laz
        ```
        """
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Export for CloudCompare

    Writes both labellings as extra scalar fields so the two methods and the
    reference can be flipped between in one viewer.

    Open the result and colour by **`treeID_dj`** (method B), **`treeID_chm`**
    (method A) or the original **`treeid`** (reference). The cloud already carries
    `treeid`, so nothing is overwritten.
    """)
    return


@app.cell
def _(mo):
    export = mo.ui.run_button(label="Write LAZ for CloudCompare")
    export
    return (export,)


@app.cell
def _(CLOUD, OUTDIR, export, labels_a, labels_b, laspy, mo, np, seeds):
    mo.stop(
        labels_b is None,
        mo.md("*Run region growing first — the export writes both methods.*"),
    )
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


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
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
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Inspect a single tree

    Pick a tree by its id and see it on its own. Coordinates are re-centred on that
    tree's stem, so the views are comparable between trees regardless of where in the
    plot it stands.

    Colours are the semantic classes the pipeline assigns — **stem** inside the fitted
    radius of the vertical axis, **foliage** everywhere else on the tree. This is the
    quickest way to see whether an instance is one clean tree or two merged ones: a
    merged instance shows two stems.
    """)
    return


@app.cell(hide_code=True)
def _(mo, trees):
    _opts = {
        f"tree {int(r.treeID):3d}  —  {r.height_m:5.1f} m,  DBH {r.dbh_m:.2f} m,  {int(r.points):,} pts": int(r.treeID)
        for r in trees.sort_values("height_m", ascending=False).itertuples()
    }
    tree_pick = mo.ui.dropdown(_opts, value=list(_opts)[0], label="tree")
    tree_max_pts = mo.ui.slider(5_000, 120_000, value=40_000, step=5_000,
                                label="points shown", show_value=True)
    mo.vstack([tree_pick, tree_max_pts])
    return tree_max_pts, tree_pick


@app.cell(hide_code=True)
def _(labels_b, mo, np, pd, semantic, tree_max_pts, tree_pick, trees, xyz):
    _tid = tree_pick.value - 1              # dropdown is 1-based, labels are 0-based
    _m = labels_b == _tid
    _ti = np.flatnonzero(_m)
    if len(_ti) > tree_max_pts.value:
        _ti = _ti[:: max(1, len(_ti) // tree_max_pts.value)][: tree_max_pts.value]

    # Re-centre on the stem so trees are comparable to each other.
    _row = trees.loc[trees.treeID == tree_pick.value].iloc[0]
    tree_pts = pd.DataFrame({
        "x": xyz[_ti, 0] - _row.x,
        "y": xyz[_ti, 1] - _row.y,
        "z": xyz[_ti, 2],
        "cls": np.where(semantic[_ti] == 1, "stem", np.where(semantic[_ti] == 0, "ground", "foliage")),
    })
    tree_pts["r"] = np.hypot(tree_pts.x, tree_pts.y)
    tree_info = _row
    mo.md(
        f"**Tree {int(_row.treeID)}** — {_row.points:,} points "
        f"({int(_row.stem_points):,} stem, {int(_row.foliage_points):,} foliage), "
        f"height **{_row.height_m:.1f} m**, DBH **{_row.dbh_m:.3f} m**. "
        f"Showing {len(tree_pts):,}."
    )
    return tree_info, tree_pts


@app.cell(hide_code=True)
def _(azim, elev, np, tree_info, tree_pts):
    import matplotlib.pyplot as _tplt   # backend already set to Agg by the overview cell

    _col = {"stem": "#8c4a2f", "foliage": "#3f8f4a", "ground": "#9a9a9a"}
    _cc = tree_pts.cls.map(_col).to_numpy()

    _tf = _tplt.figure(figsize=(11, 5.6), dpi=110)

    _a1 = _tf.add_subplot(1, 2, 1, projection="3d")
    _a1.scatter(tree_pts.x, tree_pts.y, tree_pts.z, s=0.6, c=_cc, linewidths=0, depthshade=False)
    _a1.view_init(elev=elev.value, azim=azim.value)
    _a1.set_box_aspect((np.ptp(tree_pts.x), np.ptp(tree_pts.y), np.ptp(tree_pts.z)))
    _a1.set_xlabel("x (m)"); _a1.set_ylabel("y (m)"); _a1.set_zlabel("height (m)")
    _a1.set_title(f"tree {int(tree_info.treeID)} — {tree_info.height_m:.1f} m")

    # Radius from the stem axis against height. A clean tree tapers from a tight stem
    # at the base; a merged instance shows two vertical bands.
    _a2 = _tf.add_subplot(1, 2, 2)
    _a2.scatter(tree_pts.r, tree_pts.z, s=0.6, c=_cc, linewidths=0)
    _a2.axvline(tree_info.dbh_m / 2, color="k", ls="--", lw=0.8, label=f"DBH/2 = {tree_info.dbh_m/2:.2f} m")
    _a2.axhline(1.3, color="crimson", ls=":", lw=0.9, label="breast height")
    _a2.set_xlabel("distance from stem axis (m)"); _a2.set_ylabel("height (m)")
    _a2.set_title("radial profile"); _a2.legend(fontsize=7, loc="upper right")

    _tf.tight_layout()
    _tf
    return


@app.cell(hide_code=True)
def _(alt, mo, tree_pts):
    _s = tree_pts if len(tree_pts) <= 12000 else tree_pts.iloc[:: max(1, len(tree_pts) // 12000)][:12000]
    _scale = alt.Scale(domain=["stem", "foliage", "ground"], range=["#8c4a2f", "#3f8f4a", "#9a9a9a"])
    _brush = alt.selection_interval(encodings=["x", "y"])

    _plan = (
        alt.Chart(_s).mark_circle(size=4, opacity=0.5)
        .encode(
            x=alt.X("x:Q", title="x from stem (m)", scale=alt.Scale(zero=False)),
            y=alt.Y("y:Q", title="y from stem (m)", scale=alt.Scale(zero=False)),
            color=alt.Color("cls:N", scale=_scale, title="class"),
            tooltip=["z:Q", "cls:N"],
        )
        .properties(width=290, height=290, title="plan view — drag to select")
        .add_params(_brush)
    )

    _side = (
        alt.Chart(_s).mark_circle(size=4, opacity=0.5)
        .encode(
            x=alt.X("r:Q", title="distance from stem axis (m)"),
            y=alt.Y("z:Q", title="height (m)", scale=alt.Scale(zero=False)),
            color=alt.condition(_brush, alt.Color("cls:N", scale=_scale, title="class"),
                                alt.value("#e2e2e2")),
            tooltip=["r:Q", "z:Q", "cls:N"],
        )
        .properties(width=290, height=290, title="radial profile")
    )

    _prof = (
        alt.Chart(_s).mark_bar()
        .encode(
            y=alt.Y("z:Q", bin=alt.Bin(step=0.5), title="height (m)"),
            x=alt.X("count()", title="points"),
            color=alt.Color("cls:N", scale=_scale, title="class"),
        )
        .properties(width=180, height=290, title="vertical profile")
    )

    mo.ui.altair_chart(alt.hconcat(_plan, _side, _prof).resolve_scale(color="shared"))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Weighted geometric filtering

    Three features say "this point is on a stem", and they disagree in useful ways.
    Rather than threshold each one separately, score every point on all three, weight
    the vote, and keep the best fraction.

    | feature | stem-like when | why |
    |---|---|---|
    | **verticality** | high | a stem surface is a vertical cylinder, so its normal is horizontal: $1 - \lvert n_z \rvert$ |
    | **reflectance** | high | bark returns far more strongly than foliage — about 9 dB apart here |
    | **radial distance** | low | stem points sit close to the tree's vertical axis; branches reach away from it |

    Reflectance uses the course demo's own arithmetic — add 26, divide by 31, invert,
    $\log_{10}$ — which for this sensor maps the raw range onto almost exactly 0–1.

    **Pre-screen %** keeps that percentage of the highest-scoring points. Lower is
    tighter: 10% keeps only the most stem-like tenth, 100% keeps everything.
    """)
    return


@app.cell
def _(CLOUD, k_normals, laspy, mo, np, xyz):
    from scipy.spatial import cKDTree as _KD

    # Recomputed whenever k changes. The demo specifies a 0.015 m radius; k = 20 gives a
    # median radius of 0.012 m on this cloud, so the two are near-equivalent by default.
    _bandm = (xyz[:, 2] >= 0.7) & (xyz[:, 2] < 2.0)
    band_xyz = xyz[_bandm]
    _k = int(k_normals.value)
    _t = _KD(band_xyz)
    _d, _nn = _t.query(band_xyz, k=_k, workers=-1)
    _Q = band_xyz[_nn] - band_xyz[_nn].mean(axis=1, keepdims=True)
    _w, _v = np.linalg.eigh(np.einsum("nki,nkj->nij", _Q, _Q) / _k)
    band_vert = 1.0 - np.abs(_v[:, :, 0][:, 2])          # normal horizontal -> vertical surface

    # Course demo arithmetic: +26, /31, invert, log10. LOW values = strong return = bark.
    _refl_raw = np.asarray(laspy.read(str(CLOUD)).reflectance)[_bandm]
    band_refl_doc = np.log10(1.0 / np.clip((_refl_raw + 26.0) / 31.0, 1e-9, None))
    band_radius = np.median(_d[:, -1])

    mo.md(
        f"**{len(band_xyz):,} points** in the 0.7–2.0 m band, k = {_k} "
        f"(median neighbourhood radius **{band_radius:.4f} m**; the demo uses 0.015 m). "
        f"verticality median {np.median(band_vert):.3f}, "
        f"transformed reflectance median {np.median(band_refl_doc):.3f}."
    )
    return band_refl_doc, band_vert, band_xyz


@app.cell
def _(mo):
    k_normals = mo.ui.slider(
        5, 80, value=20, step=1, label="neighbours for surface normals (k)", show_value=True
    )
    w_vert = mo.ui.slider(0.0, 1.0, value=0.4, step=0.05, label="weight — verticality", show_value=True)
    w_refl = mo.ui.slider(0.0, 1.0, value=0.4, step=0.05, label="weight — reflectance", show_value=True)
    w_radial = mo.ui.slider(0.0, 1.0, value=0.2, step=0.05, label="weight — radial distance", show_value=True)
    prescreen = mo.ui.slider(
        5, 100, value=40, step=5, label="pre-screen % kept (lower = tighter)", show_value=True
    )
    mo.vstack([
        mo.md("**Surface normals**"), k_normals,
        mo.md("**Feature weights** — relative; they are normalised to sum to 1"),
        w_vert, w_refl, w_radial,
        mo.md("**Pre-screen**"), prescreen,
    ])
    return k_normals, prescreen, w_radial, w_refl, w_vert


@app.cell
def _(
    band_refl_doc,
    band_vert,
    band_xyz,
    mo,
    np,
    prescreen,
    seeds,
    w_radial,
    w_refl,
    w_vert,
):
    from scipy.spatial import cKDTree as _KD2

    def _unit(v, lo=1, hi=99, invert=False):
        """Robust 0-1 scaling on percentiles, so one outlier cannot squash the range."""
        a, b = np.percentile(v, lo), np.percentile(v, hi)
        s = np.clip((v - a) / max(b - a, 1e-9), 0.0, 1.0)
        return 1.0 - s if invert else s

    # Radial distance to the nearest known stem axis. Stem points hug their own axis;
    # branches reach away from it. Needs seeds, so it is only meaningful once the
    # cross-section pass has produced some -- weight it 0 to score without them.
    if len(seeds):
        _dr, _ = _KD2(seeds[:, :2]).query(band_xyz[:, :2], workers=-1)
    else:
        _dr = np.zeros(len(band_xyz))
    band_radial = _dr

    _wv, _wr, _wd = w_vert.value, w_refl.value, w_radial.value
    _tot = max(_wv + _wr + _wd, 1e-9)

    stem_score = (
        _wv * _unit(band_vert)
        + _wr * _unit(band_refl_doc, invert=True)      # low transformed value = bark
        + _wd * _unit(band_radial, invert=True)        # close to an axis = stem-like
    ) / _tot

    _cut = np.percentile(stem_score, 100 - prescreen.value)
    stem_keep = stem_score >= _cut

    mo.md(
        f"""
        Weights **{_wv:.2f} verticality / {_wr:.2f} reflectance / {_wd:.2f} radial**
        (normalised by {_tot:.2f}).
        Keeping the top **{prescreen.value}%** — score ≥ **{_cut:.3f}** —
        which is **{int(stem_keep.sum()):,}** of {len(stem_score):,} band points.
        """
    )
    return (stem_keep,)


@app.cell
def _(mo):
    filt_eps = mo.ui.slider(0.03, 0.15, value=0.08, step=0.01,
                            label="cross-section DBSCAN eps (m)", show_value=True)
    score_it = mo.ui.run_button(label="Score this filter")
    mo.vstack([filt_eps, score_it])
    return filt_eps, score_it


@app.cell
def _(band_xyz, filt_eps, mo, np, stem_keep):
    import circle_fit as _cf
    from sklearn.cluster import DBSCAN as _DB

    # Cross-section on the pre-screened points only. The demo slices 1.2-1.4 m.
    _sm = (band_xyz[:, 2] >= 1.2) & (band_xyz[:, 2] < 1.4) & stem_keep
    _slice = band_xyz[_sm]

    _seeds2 = []
    if len(_slice) >= 40:
        _lab = _DB(eps=filt_eps.value, min_samples=20, n_jobs=-1).fit_predict(_slice[:, :2])
        for _c in range(_lab.max() + 1):
            _q = _slice[_lab == _c][:, :2]
            if len(_q) < 40 or (_q.max(0) - _q.min(0)).max() > 1.2:
                continue
            try:
                _xc, _yc, _r, _sg = _cf.taubinSVD(_q)
            except Exception:
                continue
            if 0.015 <= _r <= 0.6:
                _seeds2.append((_xc, _yc, 2 * _r))
    seeds_filtered = np.array(_seeds2) if _seeds2 else np.empty((0, 3))

    _msg = f"Slice holds **{len(_slice):,}** pre-screened points → **{len(seeds_filtered)} stems**."
    if len(seeds_filtered):
        _msg += (f" DBH median **{np.median(seeds_filtered[:, 2]):.3f} m** "
                 f"(range {seeds_filtered[:, 2].min():.3f}–{seeds_filtered[:, 2].max():.3f}).")
    mo.md(_msg)
    return (seeds_filtered,)


@app.cell
def _(
    GrowParams,
    attribute_errors,
    grow_instances,
    instance_scores,
    mo,
    pd,
    reference,
    score_it,
    seeds_filtered,
    xyz,
):
    mo.stop(not score_it.value, mo.md("*Press **Score this filter** to grow and compare against the reference.*"))
    mo.stop(len(seeds_filtered) == 0, mo.md("**No stems survived** — raise the pre-screen % or lower the weights."))

    _res = grow_instances(xyz, seeds_filtered, GrowParams())
    _sc = instance_scores(_res.labels, reference)
    _er = attribute_errors(_res.labels, reference, xyz, _sc["pairs"])
    _base = dict(seeds=38, matched=24, recall=0.63, precision=0.67, miou=0.799)

    _rows = pd.DataFrame([
        {"run": "baseline (no filter)", "seeds": _base["seeds"], "matched": _base["matched"],
         "recall": _base["recall"], "precision": _base["precision"], "mean IoU": _base["miou"]},
        {"run": "weighted filter", "seeds": len(seeds_filtered), "matched": _sc["matched"],
         "recall": round(_sc["recall"], 3), "precision": round(_sc["precision"], 3),
         "mean IoU": round(_sc["mean_iou_matched"], 3)},
    ])
    mo.vstack([
        mo.ui.table(_rows, selection=None),
        mo.md(f"Height RMSE **{_er.get('height_rmse', float('nan')):.3f} m**, "
              f"XY RMSE **{_er.get('xy_rmse', float('nan')):.3f} m**, "
              f"over {_er.get('n_matched', 0)} matched trees."),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Stem taper curve

    Reconstruct the stem as a stack of circles: step up the tree, fit a circle to each
    horizontal slice by RANSAC, reject the fits that disagree with their neighbours,
    then smooth what survives into a taper curve $d(z)$.

    Defaults follow the PCT demo. Each control moves detail against robustness:

    | parameter | default | effect |
    |---|---:|---|
    | slice thickness | 0.10 m | thinner = more detail, fewer points per fit |
    | vertical step | 0.08 m | smaller = more detail |
    | min points per slice | 100 | lower = accepts noisier slices |
    | cubic smoothing | 0.50 | lower = relaxes smoothing, follows the data |
    | RANSAC iterations | 2000 | higher = more reproducible |
    | distance threshold | 0.04 m | lower = accepts noise as inliers |
    | radius tolerance | 0.03 m | higher = accepts noise between neighbouring slices |
    | centre tolerance | 0.06 m | higher = accepts a wandering stem axis |

    From the smoothed curve fall DBH at 1.3 m, merchantable heights, and stem volume
    by integrating $\pi r(z)^2$.
    """)
    return


@app.cell
def _(mo):
    taper_thick = mo.ui.slider(0.02, 0.30, value=0.10, step=0.01, label="slice thickness (m)", show_value=True)
    taper_step = mo.ui.slider(0.02, 0.40, value=0.08, step=0.01, label="vertical step (m)", show_value=True)
    taper_minpts = mo.ui.slider(10, 500, value=100, step=10, label="min points per slice", show_value=True)
    taper_smooth = mo.ui.slider(0.0, 1.0, value=0.50, step=0.05, label="cubic smoothing", show_value=True)
    taper_iters = mo.ui.slider(200, 8000, value=2000, step=200, label="RANSAC iterations", show_value=True)
    taper_dist = mo.ui.slider(0.005, 0.15, value=0.04, step=0.005, label="distance threshold (m)", show_value=True)
    taper_rtol = mo.ui.slider(0.005, 0.20, value=0.03, step=0.005, label="radius tolerance (m)", show_value=True)
    taper_ctol = mo.ui.slider(0.01, 0.30, value=0.06, step=0.01, label="centre tolerance (m)", show_value=True)
    taper_method = mo.ui.dropdown(
        ["cubic spline", "moving median", "monotonic (isotonic)", "none — raw fits"],
        value="cubic spline", label="taper method",
    )
    taper_stem_only = mo.ui.checkbox(value=True, label="restrict to stem-classified points")
    mo.vstack([
        mo.md("**Slicing**"), taper_thick, taper_step, taper_minpts,
        mo.md("**RANSAC circle fit**"), taper_iters, taper_dist,
        mo.md("**Consistency between slices**"), taper_rtol, taper_ctol,
        mo.md("**Smoothing**"), taper_smooth, taper_method, taper_stem_only,
    ])
    return (
        taper_ctol,
        taper_dist,
        taper_iters,
        taper_method,
        taper_minpts,
        taper_rtol,
        taper_smooth,
        taper_stem_only,
        taper_step,
        taper_thick,
    )


@app.cell
def _(
    labels_b,
    mo,
    np,
    pd,
    semantic,
    taper_ctol,
    taper_dist,
    taper_iters,
    taper_minpts,
    taper_rtol,
    taper_stem_only,
    taper_step,
    taper_thick,
    tree_pick,
    xyz,
):
    import circle_fit as _cf2
    from scipy.interpolate import UnivariateSpline as _Spline

    def _ransac_circle(P, iters, dist_thr, rng):
        """Circle by RANSAC: sample 3 points, take the circumcircle, count inliers.

        A least-squares fit alone is pulled off the stem by branch stubs and by the
        far-side returns that come through gaps, so the consensus step matters more
        here than the refinement does.
        """
        n = len(P)
        if n < 3:
            return None
        best_in, best = None, -1
        idx = rng.integers(0, n, size=(int(iters), 3))
        for tri in idx:
            a, b, c = P[tri]
            d = 2.0 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
            if abs(d) < 1e-12:
                continue
            ux = ((a @ a) * (b[1] - c[1]) + (b @ b) * (c[1] - a[1]) + (c @ c) * (a[1] - b[1])) / d
            uy = ((a @ a) * (c[0] - b[0]) + (b @ b) * (a[0] - c[0]) + (c @ c) * (b[0] - a[0])) / d
            r = np.hypot(a[0] - ux, a[1] - uy)
            if not (0.01 <= r <= 1.5):
                continue
            resid = np.abs(np.hypot(P[:, 0] - ux, P[:, 1] - uy) - r)
            n_in = int((resid <= dist_thr).sum())
            if n_in > best:
                best, best_in = n_in, resid <= dist_thr
        if best_in is None or best < 3:
            return None
        try:                                   # refine on the consensus set
            xc, yc, r, sig = _cf2.taubinSVD(P[best_in])
        except Exception:
            return None
        return xc, yc, r, sig, int(best_in.sum())

    # --- points for the selected tree ---------------------------------------------
    _tid2 = tree_pick.value - 1
    _mm = labels_b == _tid2
    if taper_stem_only.value:
        _mm = _mm & (semantic == 1)
    _TP = xyz[_mm]

    _rng = np.random.default_rng(0)            # fixed seed: reruns are reproducible
    _rows = []
    if len(_TP) >= taper_minpts.value:
        _z0, _z1 = _TP[:, 2].min(), _TP[:, 2].max()
        _prev = None
        for _zc in np.arange(_z0 + taper_thick.value / 2, _z1, taper_step.value):
            _sl2 = _TP[np.abs(_TP[:, 2] - _zc) <= taper_thick.value / 2]
            if len(_sl2) < taper_minpts.value:
                continue
            _fit = _ransac_circle(_sl2[:, :2], taper_iters.value, taper_dist.value, _rng)
            if _fit is None:
                continue
            _xc, _yc, _r, _sg, _nin = _fit
            _ok, _why = True, ""
            if _prev is not None:
                if abs(_r - _prev[2]) > taper_rtol.value:
                    _ok, _why = False, "radius jump"
                elif np.hypot(_xc - _prev[0], _yc - _prev[1]) > taper_ctol.value:
                    _ok, _why = False, "centre jump"
            _rows.append(dict(z=_zc, x=_xc, y=_yc, r=_r, d=2 * _r, sigma=_sg,
                              n=len(_sl2), inliers=_nin, ok=_ok, why=_why))
            if _ok:
                _prev = (_xc, _yc, _r)

    taper_raw = pd.DataFrame(_rows)
    mo.md(
        f"Tree **{tree_pick.value}**: {len(_TP):,} points"
        + (" (stem-classified only)" if taper_stem_only.value else "")
        + f" → **{len(taper_raw)}** slice fits, "
        + (f"**{int(taper_raw.ok.sum())}** passing the consistency checks."
           if len(taper_raw) else "none.")
    )
    return (taper_raw,)


@app.cell
def _(
    mo,
    np,
    pd,
    taper_method,
    taper_raw,
    taper_smooth,
    taper_step,
    tree_info,
):
    from scipy.interpolate import UnivariateSpline as _Sp
    from scipy.ndimage import median_filter as _medf
    from sklearn.isotonic import IsotonicRegression as _Iso

    _good = taper_raw[taper_raw.ok] if len(taper_raw) else taper_raw
    taper_curve = pd.DataFrame(columns=["z", "d"])

    if len(_good) >= 4:
        _z = _good.z.to_numpy()
        _d = _good.d.to_numpy()
        _m = taper_method.value

        if _m == "cubic spline":
            # UnivariateSpline's s bounds the summed squared residual. Higher slider =
            # more smoothing, matching the demo's wording (decrease to relax). Note this
            # is NOT MATLAB csaps' p parameter, which runs the other way.
            _s = float(taper_smooth.value) * len(_z) * (0.02 ** 2)
            _fit2 = _Sp(_z, _d, s=_s, k=3)
            _dd = _fit2(_z)
        elif _m == "moving median":
            _w = max(3, int(round(0.5 / max(taper_step.value, 1e-6))) | 1)
            _dd = _medf(_d, size=min(_w, len(_d) | 1), mode="nearest")
        elif _m == "monotonic (isotonic)":
            # A stem cannot widen with height; isotonic imposes exactly that.
            _dd = _Iso(increasing=False).fit(_z, _d).predict(_z)
        else:
            _dd = _d

        taper_curve = pd.DataFrame({"z": _z, "d": _dd, "d_raw": _d})

    if len(taper_curve) >= 2:
        _zc2, _dc = taper_curve.z.to_numpy(), taper_curve.d.to_numpy()
        dbh_taper = float(np.interp(1.3, _zc2, _dc)) if _zc2.min() <= 1.3 <= _zc2.max() else float("nan")
        stem_volume = float(np.trapezoid(np.pi * (_dc / 2) ** 2, _zc2))
        _seed_dbh = float(tree_info.dbh_m)
        mo.md(
            f"""
            **{taper_method.value}**, {len(taper_curve)} accepted slices from
            {_zc2.min():.2f} to {_zc2.max():.2f} m.

            | | |
            |---|---|
            | DBH from the taper curve at 1.3 m | **{dbh_taper:.3f} m** |
            | DBH from the cross-section seed | {_seed_dbh:.3f} m |
            | difference | {dbh_taper - _seed_dbh:+.3f} m |
            | stem volume over the fitted range | **{stem_volume:.3f} m³** |

            The seed DBH comes from one 0.30 m slab; the taper value comes from a smoothed
            fit through many slices, so where they disagree the taper figure is usually the
            one to trust.
            """
        )
    else:
        dbh_taper, stem_volume = float("nan"), float("nan")
        mo.md("**Too few accepted slices to build a curve** — lower the minimum points per slice, or loosen the tolerances.")
    return dbh_taper, taper_curve


@app.cell
def _(
    dbh_taper,
    np,
    taper_curve,
    taper_method,
    taper_minpts,
    taper_raw,
    tree_pick,
):
    import matplotlib.pyplot as _pplt

    _fg = _pplt.figure(figsize=(12, 5.0), dpi=110)

    # 1. taper curve
    _ax_t = _fg.add_subplot(1, 3, 1)
    if len(taper_raw):
        _bad = taper_raw[~taper_raw.ok]
        _ax_t.scatter(_bad.d, _bad.z, s=14, c="#c74c4c", marker="x", label="rejected")
        _okp = taper_raw[taper_raw.ok]
        _ax_t.scatter(_okp.d, _okp.z, s=14, c="#999999", label="raw fit")
    if len(taper_curve):
        _ax_t.plot(taper_curve.d, taper_curve.z, "-", lw=2, c="#4c78a8", label=taper_method.value)
    _ax_t.axhline(1.3, color="crimson", ls=":", lw=0.9)
    if np.isfinite(dbh_taper):
        _ax_t.plot([dbh_taper], [1.3], "o", c="crimson", ms=6, label=f"DBH {dbh_taper:.3f} m")
    _ax_t.set_xlabel("diameter (m)"); _ax_t.set_ylabel("height (m)")
    _ax_t.set_title(f"taper — tree {tree_pick.value}"); _ax_t.legend(fontsize=7); _ax_t.set_xlim(left=0)

    # 2. stem axis drift: does the fitted centre wander?
    _ax_c = _fg.add_subplot(1, 3, 2)
    if len(taper_raw):
        _o2 = taper_raw.iloc[0]
        _ax_c.plot(taper_raw.x - _o2.x, taper_raw.y - _o2.y, "-o", ms=3, lw=0.8, c="#54a24b")
        _ax_c.scatter([0], [0], c="k", s=25, zorder=5, label="base")
    _ax_c.set_aspect("equal"); _ax_c.set_xlabel("Δx (m)"); _ax_c.set_ylabel("Δy (m)")
    _ax_c.set_title("stem axis drift"); _ax_c.legend(fontsize=7)

    # 3. slice quality
    _ax_q = _fg.add_subplot(1, 3, 3)
    if len(taper_raw):
        _ax_q.plot(taper_raw.n, taper_raw.z, lw=1, c="#888", label="points in slice")
        _ax_q.plot(taper_raw.inliers, taper_raw.z, lw=1.4, c="#4c78a8", label="RANSAC inliers")
        _ax_q.axvline(taper_minpts.value, color="crimson", ls="--", lw=0.9, label="minimum")
    _ax_q.set_xlabel("points"); _ax_q.set_ylabel("height (m)")
    _ax_q.set_title("slice quality"); _ax_q.legend(fontsize=7)

    _fg.tight_layout()
    _fg
    return


if __name__ == "__main__":
    app.run()
