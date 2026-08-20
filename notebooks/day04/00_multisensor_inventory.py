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

Run:  uv run marimo edit notebooks/day04/00_multisensor_inventory.py --watch
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

    One thing to know before step 5. **Nothing here measures a whole stem.** The taper
    reconstruction stops where the returns thin out, so the notebook reports three
    volumes per tree, measured strict, measured relaxed and modelled to the tip, each
    with the fraction of the tree it actually covers. Picking one and calling it stem
    volume is the mistake this notebook is arranged to prevent.
    """)
    return


@app.cell
def _():
    from pathlib import Path

    import altair as alt
    import matplotlib
    import numpy as np
    import pandas as pd

    matplotlib.use("Agg")  # server-rendered PNG: see the note on plotly in the README
    import matplotlib.pyplot as plt

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
        ALS,
        CLOUDS,
        MLS,
        OUTDIR,
        TLS,
        TaperParams,
        alt,
        join_sensors,
        match_positions,
        np,
        pd,
        plt,
        run_sensor,
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
    ### Semantic segmentation: what each sensor is able to label

    Instance segmentation asks *which tree is this point*. Semantic segmentation asks
    *what kind of thing is it*, here ground, stem or foliage. The two are independent,
    and the second one is where the three sensors stop being interchangeable.

    A ground-based scanner sees bark directly, so stem is a class it can assign from
    the data. A helicopter does not: under a closed canopy almost nothing of the stem
    is ever hit, so **ALS has no stem class to give**, and the panels below show that
    rather than argue it. Everything ALS knows about a stem it infers from the crown
    above it, which is exactly why the Day 4 objective needs both platforms.

    The stem class here comes from `novatrees.extract.semantic_labels` with
    `method="tracked"`: each stem is followed band by band from breast height, its
    centre and radius refitted as it goes, so lean and mild sweep stay inside the class
    and the stem ends where the returns stop rather than at a fixed height.
    """)
    return


@app.cell
def _(mo):
    sem_det = mo.ui.dropdown(["heuristic", "learned"], value="heuristic",
                             label="detector to classify")
    sem_thick = mo.ui.slider(0.5, 6.0, value=2.0, step=0.5,
                             label="cross-section thickness (m)", show_value=True)
    sem_run = mo.ui.run_button(label="Classify ground, stem and foliage")
    mo.vstack([sem_det, sem_thick, sem_run])
    return sem_det, sem_run, sem_thick


@app.cell
def _(ALS, MLS, TLS, mo, np, pd, runs, sem_det, sem_run, sem_thick):
    mo.stop(not sem_run.value, mo.md("*Press the button to classify.*"))

    # Aliased private: the volume cell below already owns the public name, and marimo
    # allows one owning cell per name.
    from novatrees import semantic_labels as _classify

    _PRESET = {"ALS": ALS, "MLS": MLS, "TLS": TLS}
    semantics = {}
    for _name in ("ALS", "MLS", "TLS"):
        _r = runs.get((_name, sem_det.value))
        if _r is None or isinstance(_r, Exception):
            continue
        _p = np.column_stack([_r.cloud.x.values, _r.cloud.y.values, _r.cloud.z.values])
        _gz = _PRESET[_name].grow.ground_z
        if _name == "ALS":
            # Two classes only, and the missing third one is the point. Seeds here are
            # canopy maxima with a placeholder diameter, so running the stem tracker on
            # them would invent a class the data cannot support.
            _s = np.where(_p[:, 2] <= _gz, 0, 2).astype(np.int8)
        else:
            _s = _classify(_p, _r.labels, _r.seeds, ground_z=_gz)

        # Keep only what the figure needs: a slab through the plot centre, plus the
        # stem points in plan view. Holding three full clouds again would not fit.
        # The slab is cut to 15 m either side for every sensor, the ground plots'
        # radius, so the three cross-sections cover the same ground and can be read
        # against each other. The ALS footprint is twice that; the plan view keeps it.
        _cx, _cy, _rad = _r.plot.x, _r.plot.y, _r.plot.radius
        _half = 15.0
        _slab = (np.abs(_p[:, 1] - _cy) <= sem_thick.value / 2) & \
                (np.abs(_p[:, 0] - _cx) <= _half)
        _idx = np.flatnonzero(_slab)
        if len(_idx) > 80_000:
            _idx = np.random.default_rng(0).choice(_idx, 80_000, replace=False)
        _stem = np.flatnonzero(_s == 1)
        if len(_stem) > 60_000:
            _stem = np.random.default_rng(1).choice(_stem, 60_000, replace=False)

        semantics[_name] = {
            "slab_xz": np.column_stack([_p[_idx, 0] - _cx, _p[_idx, 2]]),
            "slab_class": _s[_idx],
            "stem_xy": _p[_stem][:, :2] - np.array([_cx, _cy]),
            # What the sensor offers instead of a stem position. For ALS these are
            # canopy apices from the watershed, which is a different thing measured
            # in a different place, and the figure says so.
            "seed_xy": (_r.seeds[:, :2] - np.array([_cx, _cy])) if len(_r.seeds) else None,
            "counts": {_c: int((_s == _c).sum()) for _c in (0, 1, 2)},
            "n": int(len(_s)),
            "radius": _rad,
            "half": _half,
        }

    _tab = pd.DataFrame([
        {"sensor": _k, "points": f"{_v['n']:,}",
         "ground %": round(100 * _v["counts"][0] / _v["n"], 1),
         "stem %": round(100 * _v["counts"][1] / _v["n"], 2),
         "foliage %": round(100 * _v["counts"][2] / _v["n"], 1)}
        for _k, _v in semantics.items()
    ])
    mo.vstack([
        mo.ui.table(_tab, selection=None),
        mo.md(
            "The stem column is the one to read. It is a small share of any cloud, "
            "a few per cent at best, and it is **zero by construction for ALS**: "
            "the helicopter records no bark to classify."
        ),
    ])
    return (semantics,)


@app.cell
def _(mo, plt, semantics):
    mo.stop(not semantics, mo.md("*Classify first.*"))

    _COL = {0: "#8d8d8d", 1: "#b03030", 2: "#3f7d3f"}
    _NAME = {0: "ground", 1: "stem", 2: "foliage"}
    _order = [_k for _k in ("ALS", "MLS", "TLS") if _k in semantics]

    _fig, _ax = plt.subplots(2, len(_order), figsize=(4.6 * len(_order), 8.6),
                             gridspec_kw={"height_ratios": [1.35, 1]})
    if len(_order) == 1:
        _ax = _ax.reshape(2, 1)

    for _j, _name in enumerate(_order):
        _d = semantics[_name]
        _a = _ax[0, _j]
        for _c in (0, 2, 1):  # stem last so it is not buried
            _m = _d["slab_class"] == _c
            if not _m.any():
                continue
            _a.scatter(_d["slab_xz"][_m, 0], _d["slab_xz"][_m, 1], s=0.12,
                       c=_COL[_c], label=_NAME[_c], linewidths=0)
        _a.set_title(f"{_name}: cross-section through the plot centre", fontsize=10)
        _a.set_xlabel("x from plot centre (m)")
        _a.set_ylabel("height above ground (m)" if _j == 0 else "")
        _a.set_xlim(-_d["half"], _d["half"])
        _a.set_ylim(-1, 32)
        _a.set_aspect("equal")
        _leg = _a.legend(loc="upper right", fontsize=8, markerscale=28, framealpha=0.9)
        for _h in _leg.legend_handles:
            _h.set_sizes([18])

        _b = _ax[1, _j]
        if len(_d["stem_xy"]):
            _b.scatter(_d["stem_xy"][:, 0], _d["stem_xy"][:, 1], s=0.4,
                       c=_COL[1], linewidths=0)
            _b.set_title(f"{_name}: stem class from above, "
                         f"{_d['counts'][1]:,} points", fontsize=10)
        else:
            # No bark to classify, so show what the sensor offers instead. These are
            # canopy apices: a position for a tree, measured 20 m above the stem.
            if _d["seed_xy"] is not None:
                _b.scatter(_d["seed_xy"][:, 0], _d["seed_xy"][:, 1], s=26,
                           facecolors="none", edgecolors="#3f7d3f", linewidths=0.9,
                           label="canopy apex")
                _b.legend(loc="upper right", fontsize=8)
            _b.set_title(f"{_name}: no stem class, "
                         f"{0 if _d['seed_xy'] is None else len(_d['seed_xy'])} "
                         "canopy apices instead", fontsize=10)
        _b.add_artist(plt.Circle((0, 0), _d["radius"], fill=False, ls="--",
                                 lw=0.8, color="#606060"))
        _lim = _d["radius"] * 1.1
        _b.set_xlim(-_lim, _lim); _b.set_ylim(-_lim, _lim)
        _b.set_aspect("equal")
        _b.set_xlabel("x from plot centre (m)")
        _b.set_ylabel("y from plot centre (m)" if _j == 0 else "")

    _fig.tight_layout()
    mo.vstack([
        _fig,
        mo.md(
            """
            **Top row, the cross-section**, all three cut to the same 30 m of ground so
            they can be read against each other. Ground grey, stem dark red, foliage
            green. The ALS panel is a canopy with a floor and nothing in between: its
            returns stop at the crown surface, and the empty band under it is the volume
            no airborne sensor can measure. The MLS and TLS panels are the reverse,
            dense from the ground up, with stems standing out as continuous vertical
            bands.

            **Bottom row, the stem class from above.** Each red cluster is one stem,
            and counting them is essentially what step 4 did. The ALS panel has no red
            in it at all; the green rings are canopy apices, which are positions for
            trees measured twenty metres above the stem they stand on. That difference
            is the median 0.5 m offset in step 6, and on a leaning tree it is metres.

            The dashed circle is the plot boundary. Stems on it are cut by the cookie
            cutter and flagged as edge trees. The ALS circle is twice the radius: it is
            the coverage the ground sensors do not have, and the reason to want a model
            that carries stem volume outward from these plots.
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
    filtering, then a curve integrated as $V = \int_{z_0}^{z_1} \pi r(z)^2\,dz$.

    ### Read the limits before the number

    $z_0$ and $z_1$ are the first and last **accepted** slice, not the ground and the
    tip. Returns per stem thin with height until slices fall below `min_points` and the
    chain stops, typically in the lower canopy: on this plot the strict settings cover
    16 to 44 per cent of tree height. That integral is a partial stem volume, and
    reporting it as stem volume is simply wrong.

    So three numbers are computed per tree rather than one, and they are meant to be
    read together:

    | column | integrated over | what it is |
    | --- | --- | --- |
    | `vol_measured_strict_m3` | accepted slices, PCT thresholds | measured, partial, nothing extrapolated |
    | `vol_measured_relaxed_m3` | accepted slices, loosened thresholds | measured, partial, reaches higher, noisier |
    | `vol_model_relaxed_m3` | $0$ to $H$ | Kozak fitted then integrated whole, so extrapolated above the slices |

    Each measured column carries its own `cover_*` = $(z_1 - z_0)/H$. Without it the
    number cannot be interpreted at all.

    The check that catches this failure is the **form factor**, volume over the
    cylinder $\pi (D_{1.3}/2)^2 H$. Boreal conifer stems sit near 0.45 to 0.50. Near
    0.25 means the reconstruction stopped halfway, not that the tree is thin.

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
    # Which of the three goes forward into the join. There is no default that is
    # right for every purpose: the measured columns are what the scanner saw, the
    # model column is the only one that estimates a whole stem.
    vol_choice = mo.ui.dropdown(
        {
            "model, relaxed fit (whole stem, extrapolated)": "vol_model_relaxed_m3",
            "model, strict fit (whole stem, extrapolated)": "vol_model_strict_m3",
            "measured, relaxed (partial, reaches higher)": "vol_measured_relaxed_m3",
            "measured, strict (partial, PCT thresholds)": "vol_measured_strict_m3",
        },
        value="model, relaxed fit (whole stem, extrapolated)",
        label="volume carried into step 6",
    )
    mo.vstack([vol_min_pts, vol_choice, vol_run])
    return vol_choice, vol_min_pts, vol_run


@app.cell
def _(TaperParams, mo, np, pd, runs, vol_choice, vol_min_pts, vol_run):
    mo.stop(not vol_run.value, mo.md("*Press the button to reconstruct stem taper.*"))

    from novatrees import semantic_labels
    from novatrees.taper import VOLUME_COLUMNS, volume_variants

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
            # Reconstructs twice, strict and relaxed, and integrates both the
            # measured range and the fitted model. See novatrees.taper.
            _row = volume_variants(_xyz[_sel], total_height=_h,
                                   p=TaperParams(model="kozak"), tree_id=_k + 1)
            if not np.isfinite(_row["dbh_strict_m"]):
                continue
            _row["x"] = float(_r.seeds[_k, 0])
            _row["y"] = float(_r.seeds[_k, 1])
            _rows.append(_row)
        _df = pd.DataFrame(_rows, columns=VOLUME_COLUMNS + ["x", "y"])
        # Downstream cells read one column. Which one is the reader's choice, and
        # the alias keeps that choice visible rather than buried in the join.
        _df["volume_m3"] = _df[vol_choice.value]
        _df["dbh_m"] = _df["dbh_strict_m"]
        _df["h_total_m"] = _df["height_m"]
        volumes[_sensor] = _df.rename(columns={"tree_id": "treeID"})

    mo.md(" ".join(
        f"**{_k}**: {len(_v)} trees reconstructed, median {vol_choice.value} "
        f"{_v.volume_m3.median():.3f} m3."
        for _k, _v in volumes.items()
    ) or "No volumes reconstructed.")
    return (volumes,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### The three answers, side by side

    Read the `cover` columns first. They say how much of each stem the measured
    columns actually span, and therefore how much of the model column is
    extrapolation. The form factors say whether any of it is believable.
    """)
    return


@app.cell
def _(mo, pd, volumes):
    mo.stop(not volumes, mo.md("*Stem volumes are needed first.*"))

    _rows = []
    for _s, _v in volumes.items():
        _rows.append({
            "sensor": _s,
            "trees": len(_v),
            "measured strict (m3)": _v.vol_measured_strict_m3.median(),
            "cover strict": _v.cover_strict.median(),
            "measured relaxed (m3)": _v.vol_measured_relaxed_m3.median(),
            "cover relaxed": _v.cover_relaxed.median(),
            "model relaxed (m3)": _v.vol_model_relaxed_m3.median(),
            "cylinder (m3)": _v.vol_cylinder_m3.median(),
            "f measured strict": _v.ff_measured_strict.median(),
            "f measured relaxed": _v.ff_measured_relaxed.median(),
            "f model relaxed": _v.ff_model_relaxed.median(),
        })
    _tab = pd.DataFrame(_rows).round(3)

    mo.vstack([
        mo.ui.table(_tab, selection=None),
        mo.md(
            """
            Medians, so a single failed tree does not move them.

            What to look for. **Cover rising** from strict to relaxed is the relaxed
            settings buying reach. **Measured volume rising with it** is volume that
            was there all along and the strict thresholds refused to integrate.
            **The model column above both** is expected, since it includes the stem
            above the last accepted slice, and it is only trustworthy to the extent
            its form factor lands in the 0.45 to 0.50 range a boreal conifer keeps.

            A form factor near 0.25 on a measured column is not a finding about the
            trees. It is the arithmetic of integrating a third of a stem.
            """
        ),
    ])
    return


@app.cell
def _(alt, mo, pd, volumes):
    mo.stop(not volumes, mo.md("*Stem volumes are needed first.*"))

    _long = pd.concat([
        pd.DataFrame({
            "sensor": _s, "tree": _v.treeID, "height_m": _v.height_m,
            "reach_m": _v[f"z_top_{_tag}_m"], "cover": _v[f"cover_{_tag}"],
            "form factor": _v[f"ff_measured_{_tag}"], "settings": _tag,
        })
        for _s, _v in volumes.items() for _tag in ("strict", "relaxed")
    ], ignore_index=True).dropna(subset=["reach_m"])

    _reach = (
        alt.Chart(_long).mark_circle(size=60, opacity=0.7)
        .encode(x=alt.X("height_m:Q", title="tree height (m)"),
                y=alt.Y("reach_m:Q", title="highest accepted slice (m)"),
                color=alt.Color("settings:N", title=None),
                shape=alt.Shape("sensor:N", title=None),
                tooltip=["sensor", "tree", "height_m", "reach_m", "cover"])
        .properties(width=330, height=300, title="how far up the reconstruction got")
    )
    _diag = (
        alt.Chart(pd.DataFrame({"h": [0, float(_long.height_m.max())]}))
        .mark_line(color="crimson", strokeDash=[4, 4]).encode(x="h:Q", y="h:Q")
    )
    _ff = (
        alt.Chart(_long.dropna(subset=["form factor"]))
        .mark_circle(size=60, opacity=0.7)
        .encode(x=alt.X("cover:Q", title="cover, fitted range over tree height"),
                y=alt.Y("form factor:Q", title="form factor of the measured volume",
                        scale=alt.Scale(domain=[0, 0.8])),
                color=alt.Color("settings:N", title=None),
                shape=alt.Shape("sensor:N", title=None),
                tooltip=["sensor", "tree", "cover", "form factor"])
        .properties(width=330, height=300, title="form factor against cover")
    )
    _band = (
        alt.Chart(pd.DataFrame({"lo": [0.45], "hi": [0.50]}))
        .mark_rect(opacity=0.15, color="seagreen").encode(y="lo:Q", y2="hi:Q")
    )

    mo.vstack([
        alt.hconcat(_reach + _diag, _ff + _band),
        mo.md(
            """
            **Left.** Every point below the dashed 1:1 line is stem the reconstruction
            never reached. The strict series sits far below it; the relaxed series
            climbs toward it. The gap is the part of the volume that only a fitted
            taper can supply.

            **Right.** The green band is where a boreal conifer stem's form factor
            belongs. Measured form factor rises with cover, meeting the band only as
            cover approaches one, which is the same fact seen from the other side: a
            low form factor here is a short integral, not a thin tree.
            """
        ),
    ])
    return


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

    from novatrees import drop_fragments

    _g = volumes[ground_ref.value]
    # Watershed on a CHM makes more objects than there are trees, and the slivers
    # are positions, so they win nearest-neighbour matches and drag nonsense
    # heights into the table. Dropping them took the matched height RMSE from
    # 10.88 m to 2.09 m.
    _a = drop_fragments(_als.trees, drop_edge=bool(drop_edge.value))

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
        "treeID_ground", "volume_m3_ground",
        "vol_measured_strict_m3_ground", "cover_strict_ground",
        "vol_measured_relaxed_m3_ground", "cover_relaxed_ground",
        "vol_model_relaxed_m3_ground", "ff_model_relaxed_ground",
        "dbh_m_ground", "h_total_m_ground",
        "h_p99_air", "h_max_air", "crown_area_m2_air", "crown_volume_m3_air",
        "h_p50_air", "h_p95_air", "frac_above_mean_air", "n_points_air", "distance",
    ) if c in joined.columns]
    mo.vstack([
        mo.ui.table(joined[_cols].round(3), selection=None),
        mo.md(
            "Ground-derived volume on the left, ALS-derived metrics on the right. "
            "All three volume variants are kept in the row, not just the chosen one, "
            "so any regression fitted downstream has to say which it used. "
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


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---

    ## Results as measured

    A full pass takes about ninety minutes on this machine, most of it the learned
    detector on CPU, so the numbers from the run of **2026-08-20** are recorded here.
    Run the notebook to reproduce them; read them to know what to expect.

    ### Detection, 8 M points per cloud

    | sensor | detector | trees | on edge | time |
    | --- | --- | ---: | ---: | ---: |
    | ALS | heuristic | 92 | 15 | 22 s |
    | MLS | heuristic | 38 | 7 | 50 s |
    | TLS | heuristic | 48 | 9 | 66 s |
    | MLS | learned | 39 | 7 | 1,324 s |
    | TLS | learned | 35 | 8 | 4,894 s |

    ALS reports 92 objects because a watershed fragments crowns, not because a
    helicopter found trees the ground missed. Twenty-six are debris and are removed by
    `drop_fragments` before matching.

    ### Stem volume, medians per run

    | run | trees | strict | cover | f | relaxed | cover | f | model | f | model usable |
    | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
    | MLS heuristic | 38 | 0.407 | 0.30 | 0.24 | 0.772 | 0.75 | 0.44 | 0.981 | **0.49** | 26/38 |
    | TLS heuristic | 42 | 0.308 | 0.35 | 0.27 | 0.643 | 0.73 | 0.46 | 0.763 | **0.51** | 30/42 |
    | MLS learned | 23 | 0.139 | 0.17 | 0.18 | 0.522 | 0.74 | 0.47 | 0.826 | **0.51** | 11/23 |
    | TLS learned | 23 | 0.176 | 0.27 | 0.22 | 0.532 | 0.70 | 0.45 | 0.695 | **0.53** | 18/23 |

    Volumes in m3. **The strict column varies threefold across runs and the form
    factor does not.** That is the signature of a coverage artefact: the runs are
    measuring different amounts of stem, not different trees. Relaxing the thresholds
    collapses the spread to 0.44 to 0.47, and the model column to 0.49 to 0.53, where
    a boreal conifer belongs.

    The last column is the price. A fitted taper that does not close at the tip is
    refused rather than clamped flat, so only 26 of 38 trees carry a model volume on
    MLS and 11 of 23 on MLS learned. An earlier version clamped instead and reported
    every tree, with the MLS learned form factor at 0.60 rather than 0.51. The extra
    trees were cylinders running to the treetop.

    ### The ALS segmentation matters more than anything else here

    Our CHM watershed against `pcf`'s Dalponte crowns, on the same normalised heights
    so that only the segmentation differs. Run it with
    `run_sensor(..., detector="pcf")`:

    | | ours, watershed | `pcf`, dalponte2016 |
    |---|---:|---:|
    | objects found | 92 | 118 |
    | after fragment filtering | 53 | 97 |
    | crowns inside the 15 m ground plot | 13 | **25** |
    | median crown area | 84.1 m2 | **29.8 m2** |
    | stems per occupied crown | 2.64 | **1.31** |
    | **stems the ALS accounts for** | **34 %** | **63 %** |

    **Our crowns are about three times too large**, each swallowing two or three stems,
    and everything downstream inherits it. In Day 5 the fitted height exponent moves
    from 1.48 to 2.21, which is what a cone predicts, and the volume expansion ratio
    falls from 1.60 to 1.06.

    The lesson is not about `pcf`. It is that a result which looks like a sensor
    limitation, *the helicopter cannot see the understorey*, was mostly a software one,
    and only running someone else's implementation on the same data separated them.

    ### Matching to ALS

    | run | matched | median offset | height RMSE against ALS |
    | --- | ---: | ---: | ---: |
    | MLS heuristic | 12 | 0.53 m | **1.31 m** |
    | TLS heuristic | 12 | 0.59 m | 6.34 m |
    | MLS learned | 7 | 0.57 m | 1.51 m |
    | TLS learned | 8 | 2.34 m | 2.41 m |

    TLS matches as many trees as MLS and then disagrees with the air about their height
    by 6.34 m. That is occlusion: a tripod resolves the lower stem and loses the crown
    top behind everything in front of it. MLS, walking, sees the same crown from
    several sides. **Density is not coverage**, and TLS has four times the density here.

    ### The objective, twelve matched trees

    | ALS metric | strict (n=12) | relaxed (n=12) | model (n=10) |
    | --- | ---: | ---: | ---: |
    | h_max | +0.590 | +0.752 | **+0.822** |
    | h_p99 | +0.495 | +0.676 | **+0.763** |
    | crown volume | +0.680 | +0.724 | +0.689 |
    | crown area | +0.625 | +0.649 | +0.565 |

    Correlation with ground-derived stem volume, one column per variant. Nothing in the
    taper reconstruction knows about the ALS, so this is an independent test of which
    column is closest to the truth, and against the height metrics the ordering is
    unambiguous: a helicopter measures the top of the tree, so a volume including the
    upper stem should track it better than one stopping a third of the way up. It does.

    Against crown metrics the three are indistinguishable, which is also expected.
    Crown size answers to competition and growing space, not to the length of stem
    underneath.

    Form factors of these twelve trees: 0.436 to 0.526, median 0.49.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### The recorded table, and the recorded figures

    Everything below is read from `out/day04/`, written by the last full run. It is the
    same table and the same figures the cells above produce, kept so the notebook can be
    read straight through without executing anything. Re-run the notebook and they are
    regenerated in place.
    """)
    return


@app.cell
def _(OUTDIR, mo, pd):
    _csv = OUTDIR / "FINAL_joined_MLS_ALSfiltered.csv"
    mo.stop(not _csv.exists(),
            mo.md(f"*`{_csv}` not found. Run the notebook, or the Day 4 script, to write it.*"))

    final_table = pd.read_csv(_csv)
    _cols = {
        "treeID_ground": "tree", "h_total_m_ground": "H (m)", "dbh_strict_m_ground": "DBH (m)",
        "vol_measured_strict_m3_ground": "V strict", "cover_strict_ground": "cover",
        "vol_measured_relaxed_m3_ground": "V relaxed", "cover_relaxed_ground": "cover ",
        "vol_model_relaxed_m3_ground": "V model", "ff_model_relaxed_ground": "f",
        "h_max_air": "ALS h_max", "crown_area_m2_air": "crown m2",
        "crown_volume_m3_air": "crown m3", "distance": "match (m)",
    }
    _show = (final_table[[_c for _c in _cols if _c in final_table.columns]]
             .rename(columns=_cols).round(3)
             .sort_values("V model", ascending=False))

    mo.vstack([
        mo.ui.table(_show, selection=None, page_size=15),
        mo.md(
            f"""
            **{len(final_table)} trees**, MLS heuristic against the fragment-filtered ALS,
            median match offset
            {final_table.distance.median():.2f} m. Ground-derived on the left, ALS-derived
            on the right, and this is the objective the exercise was asking for.

            Median volumes: strict
            **{final_table.vol_measured_strict_m3_ground.median():.3f} m3**, relaxed
            **{final_table.vol_measured_relaxed_m3_ground.median():.3f} m3**, modelled
            **{final_table.vol_model_relaxed_m3_ground.median():.3f} m3**. Form factors of
            these trees run
            {final_table.ff_model_relaxed_ground.min():.3f} to
            {final_table.ff_model_relaxed_ground.max():.3f}, median
            {final_table.ff_model_relaxed_ground.median():.3f}, which is where a boreal
            conifer stem belongs and is the check that the modelled column is the one to
            carry forward.

            The full file has every ALS metric and both DBH estimates:
            `{_csv}`.
            """
        ),
    ])
    return


@app.cell
def _(OUTDIR, mo):
    # OUTDIR is <repo>/out/day04, so two levels up is the repository root.
    _figdir = OUTDIR.parent.parent / "docs" / "figures"
    _figs = [
        ("Semantic segmentation, three sensors",
         "day04_semantic_segmentation.png",
         "ALS has no stem class. The rings in its panel are canopy apices, positions "
         "measured twenty metres above the stem they belong to."),
        ("The three volume answers",
         "day04_volume_variants.png",
         "Every point below the 1:1 line is stem the reconstruction never reached, and "
         "the form factor of a measured volume rises with cover until it meets the band "
         "where a boreal conifer belongs."),
        ("Stem profile: cross-sections, the taper function, and the extrapolation",
         "day04_taper_profile.png",
         "Diameter against height for three real stems. Grey circles are slices "
         "accepted at PCT's thresholds, blue triangles the relaxed ones, the solid "
         "line is the Kozak fit through them and the dashed line its extrapolation "
         "to the tip. The red dot at 1.3 m is DBH, read from the curve rather than "
         "from any one slice. Where the fit does not close at the tip the model is "
         "refused outright, which is the red panel."),
        ("The objective, twelve matched trees",
         "day04_objective.png",
         "Against ALS height the modelled volume tracks better than the strict one, "
         "+0.79 against +0.59. Nothing in the taper reconstruction knows about the ALS, "
         "so this is an independent check."),
    ]
    _items = []
    for _title, _name, _cap in _figs:
        _p = _figdir / _name
        _items.append(mo.md(f"**{_title}**"))
        _items.append(
            mo.image(str(_p), alt=_title, width="100%", caption=_cap) if _p.exists()
            else mo.md(f"*`{_name}` has not been rendered yet.*")
        )
    mo.vstack(_items)
    return


if __name__ == "__main__":
    app.run()
