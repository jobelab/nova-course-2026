"""Day 4: ALS, MLS and TLS over plot 167, ending in one joined table.

Six steps from the exercise:

    1. preprocess high density ALS
    2. detect and segment trees in the ALS
    3. extract ALS metrics
    4. detect trees in TLS and MLS over the same area
    5. estimate stem volume per detected tree
    6. match ALS and ground-based tree positions

Objective: a data frame with ground-derived stem volume beside ALS-derived metrics.
The regression that would upscale one from the other is deliberately not fitted here.

SPDX-License-Identifier: GPL-3.0-or-later
Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University

Run:  uv run marimo edit notebooks/day04/00_multisensor_inventory.py
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
    # Plot 167 from three sensors

    One plot, three viewpoints, and the reason the exercise is worth doing: **no single
    sensor measures everything.** The ground sees stems and cannot see the canopy top.
    The helicopter sees the canopy and cannot see a stem at all. Stem volume has to be
    measured from below; area-wide coverage only exists from above. Joining them is how
    a plot becomes a map.

    | | ALS helicopter | MLS | TLS |
    |---|---|---|---|
    | points | 11.2 M | 61.0 M | 290.3 M |
    | plot radius | 30 m | 15 m | 15 m |
    | density | ~3,000 /m2 | ~68,000 /m2 | ~323,000 /m2 |
    | stems visible | no | yes | yes, richly |
    | seeds from | canopy maxima | cross-section | cross-section |

    Three properties of this data drive most of what follows.

    **The TLS is not georeferenced in Z.** Its heights read -2.5 to 27.9 m while the
    other two sit at 135 to 166 m. Normalised height is the only datum all three share,
    so normalisation is a correctness requirement here, not a convenience.

    **All three are circular cookie cuts** on a common centre. A cutter slices through
    whatever crowns and stems straddle the boundary, so edge trees are measured from a
    fraction of themselves and their volume is biased low irreversibly. They are
    flagged, not corrected: correcting would mean assuming a shape.

    **Position means different things to each sensor.** The ground locates a tree by
    its stem; the air locates it by its canopy apex. Those differ by metres on leaning
    or asymmetric trees, and that offset is a real measurement property, not noise.
    """)
    return


@app.cell
def _():
    from pathlib import Path

    import altair as alt
    import numpy as np
    import pandas as pd

    from novatrees import (
        ALS,
        MLS,
        TLS,
        join_sensors,
        match_positions,
        run_sensor,
        taper_curve,
    )
    from novatrees.taper import TaperParams

    REPO = Path(__file__).resolve().parents[2]
    DATA = REPO / "Day04_MultiSensor"
    CLOUDS = {
        "ALS": DATA / "ALS_helicopter.laz",
        "MLS": DATA / "Plot_167_MLS.laz",
        "TLS": DATA / "Plot_167_TLS_GroundZero.laz",
    }
    OUTDIR = REPO / "out" / "day04"
    return (
        CLOUDS,
        OUTDIR,
        TaperParams,
        alt,
        join_sensors,
        match_positions,
        np,
        pd,
        run_sensor,
        taper_curve,
    )


@app.cell(hide_code=True)
def _(CLOUDS, mo):
    _missing = [k for k, v in CLOUDS.items() if not v.exists()]
    mo.stop(
        bool(_missing),
        mo.md(f"**Missing clouds: {_missing}.** Expected under `Day04_MultiSensor/`."),
    )
    mo.md("All three clouds present.")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Controls

    Decimation is not optional for the TLS: 290 M points is 6.5 GB of coordinates on a
    machine with about 9 GB free. Reading is strided, so it is reproducible and does not
    distort the spatial distribution.

    The learned detector uses TreeAIBox. On TLS and MLS those are the **boreal** stem
    and tree-location models, which suit this forest. On ALS the only models available
    are trained on **reclamation sites**, so that run is a domain-transfer test rather
    than a fair comparison, and it is labelled as such wherever its numbers appear.
    """)
    return


@app.cell
def _(mo):
    max_pts = mo.ui.slider(
        2_000_000, 12_000_000, value=8_000_000, step=1_000_000,
        label="max points per cloud", show_value=True,
    )
    detectors = mo.ui.multiselect(
        ["heuristic", "learned"], value=["heuristic"], label="detectors to run"
    )
    run_all = mo.ui.run_button(label="Run all three sensors")
    mo.vstack([max_pts, detectors, run_all,
               mo.md("*The learned detector adds a few minutes per ground cloud on CPU.*")])
    return detectors, max_pts, run_all


@app.cell
def _(CLOUDS, detectors, max_pts, mo, run_all, run_sensor):
    mo.stop(not run_all.value, mo.md("*Press **Run all three sensors** to begin.*"))

    runs = {}
    for _name, _path in CLOUDS.items():
        for _det in detectors.value:
            try:
                runs[(_name, _det)] = run_sensor(
                    _path, detector=_det, max_points=int(max_pts.value), verbose=False
                )
            except Exception as _e:  # a learned run can fail on a missing model
                runs[(_name, _det)] = _e
    mo.md(f"Completed **{sum(1 for v in runs.values() if not isinstance(v, Exception))}** "
          f"of {len(runs)} runs.")
    return (runs,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Steps 1 to 4: preprocessing and detection, all sensors
    """)
    return


@app.cell
def _(mo, pd, runs):
    _rows = []
    for (_name, _det), _r in runs.items():
        if isinstance(_r, Exception):
            _rows.append({"sensor": _name, "detector": _det, "status": f"failed: {_r}"})
            continue
        _s = _r.stats
        _rows.append({
            "sensor": _name, "detector": _det, "status": "ok",
            "points": f"{_s['n_points']:,}",
            "noise %": round(100 * _s["n_noise"] / max(_s["n_points"], 1), 2),
            "ground %": round(100 * _s["n_ground"] / max(_s["n_points"], 1), 1),
            "seeds": _s["n_seeds"], "trees": _s["n_trees"], "edge": _s["n_edge_trees"],
            "seconds": round(_s["total_s"], 1),
        })
    summary = pd.DataFrame(_rows)
    mo.vstack([
        mo.ui.table(summary, selection=None),
        mo.md(
            """
            **Read the tree counts against each other, not in isolation.** The two ground
            sensors should roughly agree, since they see the same stems. Where ALS reports
            many more, it is fragmenting crowns rather than finding trees the ground
            missed: a helicopter cannot see a stem the ground sensor stood next to.
            """
        ),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 5: stem volume, from both ground sensors

    Volume is the quantity ALS cannot measure, so it is the reason the ground clouds are
    here. It comes from the taper reconstruction: RANSAC circles up the stem, consistency
    filtering, then a smoothed curve integrated as $V = \int \pi r(z)^2\,dz$.

    Both TLS and MLS are run, and where they disagree that disagreement is the honest
    error bar on the whole exercise. Agreement between two independent instruments is
    worth more than either one's internal fit statistics.
    """)
    return


@app.cell
def _(mo):
    vol_run = mo.ui.run_button(label="Compute stem volumes (TLS and MLS)")
    vol_min_pts = mo.ui.slider(
        200, 5000, value=800, step=100, label="minimum stem points per tree", show_value=True
    )
    mo.vstack([vol_min_pts, vol_run])
    return vol_min_pts, vol_run


@app.cell
def _(TaperParams, mo, np, pd, runs, taper_curve, vol_min_pts, vol_run):
    mo.stop(not vol_run.value, mo.md("*Press the button to reconstruct stem taper.*"))

    from novatrees import semantic_labels

    volumes = {}
    for _sensor in ("TLS", "MLS"):
        _key = (_sensor, "heuristic")
        _r = runs.get(_key)
        if _r is None or isinstance(_r, Exception):
            continue
        _xyz = np.column_stack([_r.cloud.x.values, _r.cloud.y.values, _r.cloud.z.values])
        _sem = semantic_labels(_xyz, _r.labels, _r.seeds)
        _rows = []
        for _k in range(len(_r.seeds)):
            _sel = (_r.labels == _k) & (_sem == 1)
            if _sel.sum() < vol_min_pts.value:
                continue
            _h = float(_xyz[_r.labels == _k][:, 2].max())
            _t = taper_curve(_xyz[_sel], TaperParams(model="kozak"), total_height=_h)
            if not np.isfinite(_t.dbh):
                continue
            _rows.append({
                "treeID": _k + 1,
                "x": float(_r.seeds[_k, 0]), "y": float(_r.seeds[_k, 1]),
                "dbh_m": _t.dbh, "h_total_m": _h,
                "h_stem_m": _t.stats.get("height_stem", float("nan")),
                "volume_m3": _t.volume,
                "slices_ok": _t.stats.get("n_accepted", 0),
            })
        volumes[_sensor] = pd.DataFrame(_rows)

    mo.md(" ".join(
        f"**{_k}**: {len(_v)} trees with a reconstructed taper, "
        f"median volume {_v.volume_m3.median():.3f} m3."
        for _k, _v in volumes.items()
    ) or "No volumes reconstructed.")
    return (volumes,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Do the two ground sensors agree?

    Matched stem by stem. Systematic offset between them is more informative than
    scatter: MLS sees fewer returns per stem, so if its diameters run consistently
    larger, the mixed-pixel halo is the first thing to suspect.
    """)
    return


@app.cell
def _(alt, match_positions, mo, np, pd, volumes):
    mo.stop(len(volumes) < 2, mo.md("*Both TLS and MLS volumes are needed for this.*"))

    _t, _m = volumes["TLS"], volumes["MLS"]
    _pairs, _ut, _um = match_positions(_t[["x", "y"]].to_numpy(), _m[["x", "y"]].to_numpy(), 1.5)
    mo.stop(_pairs.empty, mo.md("*No stems matched between TLS and MLS.*"))

    _cmp = pd.DataFrame({
        "dbh_TLS": _t.dbh_m.to_numpy()[_pairs.a], "dbh_MLS": _m.dbh_m.to_numpy()[_pairs.b],
        "vol_TLS": _t.volume_m3.to_numpy()[_pairs.a], "vol_MLS": _m.volume_m3.to_numpy()[_pairs.b],
        "h_TLS": _t.h_total_m.to_numpy()[_pairs.a], "h_MLS": _m.h_total_m.to_numpy()[_pairs.b],
        "offset_m": _pairs.distance.to_numpy(),
    })
    _d_dbh = _cmp.dbh_MLS - _cmp.dbh_TLS
    _d_vol = _cmp.vol_MLS - _cmp.vol_TLS

    _sc = (
        alt.Chart(_cmp).mark_circle(size=70, opacity=0.7)
        .encode(x=alt.X("dbh_TLS:Q", title="DBH from TLS (m)"),
                y=alt.Y("dbh_MLS:Q", title="DBH from MLS (m)"),
                tooltip=["dbh_TLS:Q", "dbh_MLS:Q", "offset_m:Q"])
        .properties(width=320, height=320, title="DBH, sensor against sensor")
    )
    _lo = float(min(_cmp.dbh_TLS.min(), _cmp.dbh_MLS.min()))
    _hi = float(max(_cmp.dbh_TLS.max(), _cmp.dbh_MLS.max()))
    _line = alt.Chart(pd.DataFrame({"d": [_lo, _hi]})).mark_line(
        color="crimson", strokeDash=[4, 4]).encode(x="d:Q", y="d:Q")

    mo.vstack([
        _sc + _line,
        mo.md(
            f"""
            **{len(_cmp)} stems matched** within 1.5 m
            ({len(_ut)} TLS and {len(_um)} MLS unmatched).

            | | bias (MLS - TLS) | RMSE |
            |---|---:|---:|
            | DBH | {_d_dbh.mean():+.4f} m | {np.sqrt((_d_dbh ** 2).mean()):.4f} m |
            | volume | {_d_vol.mean():+.4f} m3 | {np.sqrt((_d_vol ** 2).mean()):.4f} m3 |
            | stem position | | {np.sqrt((_cmp.offset_m ** 2).mean()):.3f} m |

            A positive DBH bias means MLS reads thicker. Suspect the halo before
            believing the trees grew.
            """
        ),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 6: match ground to air, and the objective

    Ground trees carry stem volume; ALS trees carry the metrics that exist everywhere
    the helicopter flew. Matching is greedy and one-to-one, closest pairs first.

    Watch the **match rate** more than the offsets. A high rate with large offsets is a
    usable dataset with a known bias; a low rate means the two sensors disagree about
    how many trees exist, and no regression fitted on the survivors will fix that.
    """)
    return


@app.cell
def _(mo):
    match_dist = mo.ui.slider(
        1.0, 8.0, value=3.0, step=0.5, label="maximum match distance (m)", show_value=True
    )
    ground_ref = mo.ui.dropdown(["TLS", "MLS"], value="TLS", label="ground reference")
    drop_edge = mo.ui.checkbox(value=True, label="drop trees on the plot edge")
    mo.vstack([ground_ref, match_dist, drop_edge])
    return drop_edge, ground_ref, match_dist


@app.cell
def _(drop_edge, ground_ref, join_sensors, match_dist, mo, runs, volumes):
    mo.stop(not volumes, mo.md("*Stem volumes are needed first.*"))
    _als = runs.get(("ALS", "heuristic"))
    mo.stop(_als is None or isinstance(_als, Exception), mo.md("*The ALS run is needed first.*"))

    _g = volumes[ground_ref.value]
    _a = _als.trees
    if drop_edge.value and "edge_tree" in _a:
        _a = _a[~_a.edge_tree]

    joined = join_sensors(_g, _a, max_distance=float(match_dist.value))
    _at = joined.attrs
    mo.md(
        f"""
        **{_at.get('n_matched', 0)} trees matched** between {ground_ref.value} and ALS
        at up to {match_dist.value} m.

        | | |
        |---|---|
        | ground trees with volume | {_at.get('n_ground', 0)} |
        | ALS trees offered | {_at.get('n_air', 0)} |
        | matched | **{_at.get('n_matched', 0)}** |
        | unmatched ground | {_at.get('unmatched_ground', 0)} |
        | unmatched ALS | {_at.get('unmatched_air', 0)} |
        | median offset | {_at.get('median_offset', float('nan')):.2f} m |

        The offset is stem base against canopy apex, so it is not an error to be
        minimised. A leaning tree genuinely presents those in different places.
        """
    )
    return (joined,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### The objective: one row per tree
    """)
    return


@app.cell
def _(joined, mo):
    mo.stop(joined.empty, mo.md("*Nothing matched.*"))
    _cols = [c for c in (
        "treeID_ground", "volume_m3_ground", "dbh_m_ground", "h_total_m_ground",
        "h_p99_air", "h_max_air", "crown_area_m2_air", "crown_volume_m3_air",
        "h_p50_air", "h_p95_air", "frac_above_mean_air", "n_points_air", "distance",
    ) if c in joined.columns]
    mo.vstack([
        mo.ui.table(joined[_cols].round(3), selection=None),
        mo.md(
            "Ground-derived volume on the left, ALS-derived metrics on the right. "
            "**This is where the exercise stops.** The regression that would upscale "
            "volume from the airborne metrics is tomorrow's work, and fitting it on "
            f"{len(joined)} trees from one plot would in any case be a demonstration "
            "rather than a model."
        ),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Is there a relationship worth modelling?

    Not a fit, just a look. If ALS metrics carry no signal about stem volume here, that
    is worth knowing before tomorrow.
    """)
    return


@app.cell
def _(alt, joined, mo, np):
    mo.stop(joined.empty or len(joined) < 4, mo.md("*Too few matched trees to look at.*"))
    _y = "volume_m3_ground"
    _cands = [c for c in ("h_p99_air", "crown_area_m2_air", "crown_volume_m3_air", "h_p95_air")
              if c in joined.columns]
    _rows = []
    for _c in _cands:
        _ok = joined[[_c, _y]].dropna()
        if len(_ok) >= 4:
            _rows.append((_c, float(np.corrcoef(_ok[_c], _ok[_y])[0, 1])))
    _best = max(_rows, key=lambda r: abs(r[1]))[0] if _rows else _cands[0]

    _chart = (
        alt.Chart(joined.dropna(subset=[_best, _y]))
        .mark_circle(size=80, opacity=0.75)
        .encode(x=alt.X(f"{_best}:Q", title=_best.replace("_air", " (ALS)")),
                y=alt.Y(f"{_y}:Q", title="stem volume from the ground (m3)"),
                tooltip=[_best, _y])
        .properties(width=420, height=320, title=f"stem volume against {_best}")
    )
    mo.vstack([
        _chart,
        mo.md("| ALS metric | correlation with stem volume |\n|---|---:|\n"
              + "\n".join(f"| {_c2} | {_v2:+.3f} |"
                          for _c2, _v2 in sorted(_rows, key=lambda _q: -abs(_q[1])))),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Export
    """)
    return


@app.cell
def _(mo):
    do_export = mo.ui.run_button(label="Write the joined table and per-sensor tables")
    do_export
    return (do_export,)


@app.cell
def _(OUTDIR, do_export, joined, mo, runs, volumes):
    mo.stop(not do_export.value, mo.md("*Press to write CSVs.*"))
    OUTDIR.mkdir(parents=True, exist_ok=True)
    _written = []
    for (_name, _det), _r in runs.items():
        if isinstance(_r, Exception) or _r.trees.empty:
            continue
        _p = OUTDIR / f"trees_{_name}_{_det}.csv"
        _r.trees.to_csv(_p, index=False)
        _written.append(_p.name)
    for _name, _df in volumes.items():
        _p = OUTDIR / f"volumes_{_name}.csv"
        _df.to_csv(_p, index=False)
        _written.append(_p.name)
    if not joined.empty:
        _p = OUTDIR / "joined_ground_air.csv"
        joined.to_csv(_p, index=False)
        _written.append(_p.name)
    mo.md(f"Wrote **{len(_written)}** files to `{OUTDIR}`:\n\n"
          + "\n".join(f"- `{n}`" for n in _written))
    return


if __name__ == "__main__":
    app.run()
