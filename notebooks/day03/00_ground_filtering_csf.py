"""Ground filtering with CSF, and height normalisation, from the raw cloud.

Takes `crsot_mixed_stand.laz` (raw elevations) to normalised heights without
leaving Python, and checks the result against the course's own `_hnorm` file and
against the CloudCompare qCSF plugin.

Run:  uv run marimo edit notebooks/00_ground_filtering_csf.py

SPDX-License-Identifier: GPL-3.0-or-later
Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
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
        # Ground filtering with CSF

        The Cloth Simulation Filter drapes a virtual cloth over the *inverted* point
        cloud; wherever the cloth settles onto points, those points are ground. One
        intuitive parameter - how stiff the cloth is - instead of a pile of
        morphological thresholds.

        It is installed here **twice, as the same algorithm**:

        | | how | speed |
        |---|---|---|
        | `cloth-simulation-filter` | Python bindings from the CSF authors | ~1 s on 15 M points |
        | `qCSF` | the CloudCompare plugin built for this machine | ~4 s, plus file I/O |

        So the answer to "can we use CSF in a notebook" is yes, natively - no
        subprocess, no LAZ round-trip. The plugin is still there for the GUI, and the
        last section runs both to see how far apart they land.

        Reference: [Zhang et al. 2016](https://doi.org/10.3390/rs8060501).
        """
    )
    return


@app.cell
def _():
    from pathlib import Path

    import altair as alt
    import numpy as np
    import plotly.graph_objects as go
    import pandas as pd

    from novatrees import (
        CsfParams,
        DenoiseParams,
        csf_ground,
        denoise,
        normalize_heights,
        read_cloud,
        write_cloud,
    )
    from novatrees.csf import compare_with_cloudcompare

    REPO = Path(__file__).resolve().parents[2]
    RAW = REPO / "PCT_demo" / "PCT_demo" / "crsot_mixed_stand.laz"
    HNORM = REPO / "Day03_ToumasYrttima" / "crsot_mixed_stand_hnorm.laz"
    OUTDIR = REPO / "out" / "csf"
    return (
        CsfParams,
        HNORM,
        OUTDIR,
        Path,
        RAW,
        alt,
        compare_with_cloudcompare,
        DenoiseParams,
        csf_ground,
        denoise,
        go,
        normalize_heights,
        np,
        pd,
        read_cloud,
        write_cloud,
    )


@app.cell
def _(RAW, mo, np, read_cloud):
    mo.stop(not RAW.exists(), mo.md(f"**Missing** `{RAW}` - unzip `PCT_demo.zip` first."))

    raw = read_cloud(RAW)
    mo.md(
        f"""
        **{RAW.name}** - {raw.sizes['point']:,} points, elevation
        {raw.z.min().item():.2f} to {raw.z.max().item():.2f} m
        (absolute, **not** normalised), extent
        {np.ptp(raw.x.values):.1f} x {np.ptp(raw.y.values):.1f} m.
        """
    )
    return (raw,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Cloth parameters

        `cloth_resolution` is the grid spacing of the cloth - roughly the finest
        terrain detail it can follow. `rigidness` is the stiffness: 1 for steep slopes,
        3 for flat ground. `class_threshold` $h_{cc}$ is how close to the settled cloth a
        point must be to count as ground:

        $$c(\mathbf{p}) =
          \begin{cases}
            \text{ground}, & \lvert z_{\mathbf{p}} - z_{\text{cloth}}(\mathbf{p}) \rvert \le h_{cc} \\
            \text{non-ground}, & \text{otherwise}
          \end{cases}$$

        The cloth itself settles by Verlet integration under gravity,
        $\mathbf{X}(t + \Delta t) = 2\mathbf{X}(t) - \mathbf{X}(t - \Delta t) + \frac{\mathbf{G}}{m}\Delta t^{2}$.
        See `02_methods_and_equations.py` for the full derivation.
        """
    )
    return


@app.cell
def _(mo):
    cloth_res = mo.ui.slider(0.05, 1.0, value=0.2, step=0.05, label="cloth resolution (m)", show_value=True)
    threshold = mo.ui.slider(0.05, 1.0, value=0.3, step=0.05, label="class threshold (m)", show_value=True)
    rigid = mo.ui.dropdown(
        {"1 - steep slope": 1, "2 - relief": 2, "3 - flat": 3}, value="2 - relief", label="rigidness"
    )
    run_csf = mo.ui.run_button(label="Run CSF")
    mo.vstack([cloth_res, threshold, rigid, run_csf])
    return cloth_res, rigid, run_csf, threshold


@app.cell
def _(CsfParams, cloth_res, csf_ground, mo, raw, rigid, run_csf, threshold):
    mo.stop(not run_csf.value, mo.md("*Set the cloth parameters, then press **Run CSF**.*"))

    ground = csf_ground(
        raw,
        CsfParams(
            cloth_resolution=cloth_res.value,
            class_threshold=threshold.value,
            rigidness=rigid.value,
        ),
    )
    mo.md(
        f"""
        **{ground.sum():,} ground points** ({100 * ground.mean():.1f}%),
        {(~ground).sum():,} off-ground.
        """
    )
    return (ground,)


@app.cell
def _(alt, ground, mo, np, pd, raw):
    _z = raw.z.values
    _bins = np.arange(_z.min(), _z.max() + 0.25, 0.25)
    _g, _ = np.histogram(_z[ground], bins=_bins)
    _n, _ = np.histogram(_z[~ground], bins=_bins)
    _df = pd.concat(
        [
            pd.DataFrame({"z": _bins[:-1], "points": _g, "class": "ground"}),
            pd.DataFrame({"z": _bins[:-1], "points": _n, "class": "off-ground"}),
        ]
    )
    _chart = (
        alt.Chart(_df)
        .mark_bar()
        .encode(
            y=alt.Y("z:Q", title="elevation (m)", scale=alt.Scale(zero=False)),
            x=alt.X("points:Q", title="points", stack=True),
            color=alt.Color(
                "class:N",
                scale=alt.Scale(domain=["ground", "off-ground"], range=["#8c6d31", "#54a24b"]),
            ),
            tooltip=["z:Q", "points:Q", "class:N"],
        )
        .properties(height=300, title="CSF classification by elevation")
    )
    mo.ui.altair_chart(_chart)
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ### The classification in 3D

        Drag to rotate. Brown is ground, green is everything else - the semantic split
        the rest of the pipeline is built on.
        """
    )
    return


@app.cell
def _(go, ground, mo, np, raw):
    _n = 60_000
    _xyz = np.column_stack([raw.x.values, raw.y.values, raw.z.values])
    _idx = np.arange(len(_xyz))[:: max(1, len(_xyz) // _n)][:_n]
    _p, _g = _xyz[_idx], ground[_idx]

    _fig = go.Figure()
    for _mask, _name, _col in ((_g, "ground", "#8c6d31"), (~_g, "off-ground", "#54a24b")):
        _fig.add_trace(
            go.Scatter3d(
                x=_p[_mask, 0], y=_p[_mask, 1], z=_p[_mask, 2],
                mode="markers", name=_name,
                marker=dict(size=1.2, color=_col, opacity=0.8),
            )
        )
    _fig.update_layout(
        height=600,
        margin=dict(l=0, r=0, t=30, b=0),
        scene=dict(aspectmode="data", xaxis_title="x (m)", yaxis_title="y (m)", zaxis_title="elevation (m)"),
        title=f"CSF classification - {len(_idx):,} of {len(_xyz):,} points shown",
        legend=dict(itemsizing="constant"),
    )
    mo.ui.plotly(_fig)
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Noise filtering

        Three different things get called noise, and only one of them is the real
        problem here.

        **Isolated returns** are birds, insects, rain and dust. Easy to remove, and
        mostly harmless anyway.

        **Mixed pixels** are the ones that matter. A beam clipping the edge of a stem
        returns a distance averaged between the stem and whatever is behind it, so the
        point lands in mid-air along the line of sight. They form a faint halo around
        every stem, and a circle fitted through that halo comes out **too large**. That
        is DBH and stem volume biased high, from a source no downstream tuning fixes.

        **Registration ghosts** are the same surface appearing twice, centimetres
        apart. Neither filter here touches those; they need better registration.

        Note what the filter is used for below. Noise points are excluded from the set
        that **defines the ground**, because a single return below the true surface
        drags the cloth down and every height above it inherits the error. They are not
        deleted from the cloud, so the point-to-point comparison against the course's
        own `_hnorm` file further down still lines up.
        """
    )
    return


@app.cell
def _(mo):
    denoise_on = mo.ui.checkbox(value=True, label="exclude noise from the ground surface")
    denoise_method = mo.ui.dropdown(
        {"statistical (k nearest)": "statistical", "radius (fixed neighbourhood)": "radius"},
        value="statistical (k nearest)", label="method",
    )
    denoise_k = mo.ui.slider(4, 30, value=8, step=1, label="k neighbours", show_value=True)
    denoise_sigma = mo.ui.slider(
        1.0, 4.0, value=2.5, step=0.1, label="reject beyond mean + n sigma", show_value=True
    )
    mo.vstack([denoise_on, denoise_method, denoise_k, denoise_sigma])
    return denoise_k, denoise_method, denoise_on, denoise_sigma


@app.cell
def _(DenoiseParams, denoise, denoise_k, denoise_method, denoise_on, denoise_sigma, mo, np, raw):
    if not denoise_on.value:
        keep_clean = np.ones(raw.sizes["point"], bool)
        _out = mo.md("*Noise filter off: every point counts toward the ground surface.*")
    else:
        keep_clean = denoise(
            raw,
            DenoiseParams(method=denoise_method.value, k=int(denoise_k.value),
                          n_sigma=float(denoise_sigma.value)),
        )
        _z = raw.z.values
        _rm = int((~keep_clean).sum())
        _out = mo.md(
            f"""
            Flagged **{_rm:,}** of {len(keep_clean):,} points as noise
            (**{100 * _rm / max(len(keep_clean), 1):.2f}%**).

            | | kept | flagged |
            |---|---|---|
            | highest | {_z[keep_clean].max():.2f} m | {(_z[~keep_clean].max() if _rm else float("nan")):.2f} m |
            | lowest | {_z[keep_clean].min():.2f} m | {(_z[~keep_clean].min() if _rm else float("nan")):.2f} m |

            Flagged points reaching *below* the kept minimum is the case that matters
            for this notebook: those are exactly the returns that would pull the cloth
            under the true ground.

            On the Day 4 plot this became checkable, because two sensors cover it. ALS
            put the true canopy top at 162.72 m while MLS carried 5,853 points above
            that height, which nothing in the plot can explain except noise.
            """
        )
    _out
    return (keep_clean,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Height normalisation

        A DTM from the ground points, subtracted from every Z:

        $$\mathrm{DTM}(i,j) = Q_{q}\big(\{\, z_{p} : p \in \mathcal{G},\ \kappa(p) = (i,j) \,\}\big),
          \qquad h_{p} = z_{p} - \mathrm{DTM}\big(\kappa(p)\big)$$

        The per-cell statistic $Q_q$ matters more than it looks. Taking the strict
        **minimum** ($q = 0$) is the textbook choice but is biased low, because TLS noise
        leaves a few returns beneath the real surface - and every tree then measures too
        tall. A low **quantile** is more robust.
        """
    )
    return


@app.cell
def _(mo):
    dtm_cell = mo.ui.slider(0.25, 2.0, value=0.5, step=0.25, label="DTM cell (m)", show_value=True)
    dtm_q = mo.ui.dropdown(
        {"minimum (textbook)": "min", "quantile 0.10": 0.10, "quantile 0.25": 0.25, "quantile 0.50": 0.50},
        value="quantile 0.25",
        label="per-cell statistic",
    )
    mo.vstack([dtm_cell, dtm_q])
    return dtm_cell, dtm_q


@app.cell
def _(dtm_cell, dtm_q, ground, keep_clean, normalize_heights, raw):
    # Ground points minus anything flagged as noise: one return below the true
    # surface is enough to drag the DTM cell down and bias every height above it.
    norm = normalize_heights(
        raw,
        ground & keep_clean,
        cell=dtm_cell.value,
        quantile=None if dtm_q.value == "min" else dtm_q.value,
    )
    return (norm,)


@app.cell
def _(HNORM, mo, norm, np, read_cloud):
    mo.stop(
        not HNORM.exists(),
        mo.md(f"Normalised: z {norm.z.min().item():.2f} to {norm.z.max().item():.2f} m."),
    )

    _ref = read_cloud(HNORM)
    _d = norm.z.values - _ref.z.values
    mo.md(
        f"""
        Normalised heights span **{norm.z.min().item():.2f} to {norm.z.max().item():.2f} m**.

        The course ships its own `_hnorm` file with the points in identical order, so
        this is a true point-to-point check. Over $n$ points, with $\\hat{{h}}_i$ ours and
        $h_i$ theirs:

        $$\\mathrm{{bias}} = \\frac{{1}}{{n}} \\sum_{{i=1}}^{{n}} (\\hat{{h}}_{{i}} - h_{{i}}),
          \\qquad
          \\mathrm{{RMSE}} = \\sqrt{{ \\frac{{1}}{{n}} \\sum_{{i=1}}^{{n}} (\\hat{{h}}_{{i}} - h_{{i}})^{{2}} }}
          \\qquad
          \\mathrm{{RMSE}}^{{2}} = \\mathrm{{bias}}^{{2}} + s^{{2}}$$

        Read together, not separately: the third identity says a small RMSE can still be
        pure systematic offset.

        | | |
        |---|---|
        | bias (mean difference) | **{_d.mean():+.3f} m** |
        | RMSE | **{np.sqrt((_d ** 2).mean()):.3f} m** |
        | within 0.25 m | **{100 * (np.abs(_d) < 0.25).mean():.1f}%** of points |

        Switch the statistic above to *minimum* to watch the bias jump to about
        +0.26 m - the low-noise effect, visible in one number.
        """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Cross-check: the CloudCompare plugin

        Same algorithm, different implementation. This shells out to the `qCSF` plugin
        built for this machine and compares the ground counts.
        """
    )
    return


@app.cell
def _(mo):
    run_cc = mo.ui.run_button(label="Run CloudCompare qCSF")
    run_cc
    return (run_cc,)


@app.cell
def _(OUTDIR, RAW, cloth_res, compare_with_cloudcompare, ground, mo, rigid, run_cc, threshold):
    mo.stop(not run_cc.value, mo.md("*Optional - needs the CloudCompare build.*"))

    _scene = {1: "SLOPE", 2: "RELIEF", 3: "FLAT"}[rigid.value]
    try:
        _cc = compare_with_cloudcompare(
            RAW,
            OUTDIR,
            scene=_scene,
            cloth_resolution=cloth_res.value,
            class_threshold=threshold.value,
        )
        _diff = int(ground.sum()) - _cc["ground"]
        _out = mo.md(
            f"""
            | | ground | off-ground |
            |---|---:|---:|
            | Python `cloth-simulation-filter` | {int(ground.sum()):,} | {int((~ground).sum()):,} |
            | CloudCompare `qCSF` (scene {_scene}) | {_cc['ground']:,} | {_cc['offground']:,} |
            | difference | **{_diff:+,}** | |

            The two disagree by {abs(_diff) / max(_cc['ground'], 1) * 100:.1f}%. The plugin's
            scene presets bundle post-processing the raw library leaves off, so a gap of
            a few percent is expected rather than alarming.
            """
        )
    except Exception as _e:
        _out = mo.md(f"**CloudCompare CSF unavailable:** `{_e}`")
    _out
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Export

        Writes the normalised cloud with `ground` and `z_orig` alongside, ready for
        `01_tree_instance_segmentation.py` or for CloudCompare.
        """
    )
    return


@app.cell
def _(mo):
    do_write = mo.ui.run_button(label="Write normalised LAZ")
    do_write
    return (do_write,)


@app.cell
def _(OUTDIR, RAW, do_write, mo, norm, write_cloud):
    mo.stop(not do_write.value, mo.md("*Press to write.*"))

    _out = OUTDIR / "crsot_mixed_stand_normalised.laz"
    _n = write_cloud(norm.drop_vars("z"), _out, source=RAW)
    mo.md(
        f"""
        Wrote **{_n:,} points** → `{_out}`.

        Note the Z written is the file's original elevation: LAS stores position, not
        height-above-ground, so the normalised value rides along as the `z_orig` and
        `ground` fields rather than overwriting geometry. Colour by `ground` in
        CloudCompare to inspect the classification.
        """
    )
    return


if __name__ == "__main__":
    app.run()
