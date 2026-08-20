"""Upscaling stem volume from twelve trees to the whole ALS footprint.

Day 4 stopped at a table: stem volume from the ground beside metrics from the air.
This is the step after it. Fit V = f(ALS metrics) where both exist, then apply it to
every ALS tree, including the ones no ground sensor ever reached.

Run:  uv run marimo edit notebooks/day05/00_upscaling_regression.py --watch

SPDX-License-Identifier: GPL-3.0-or-later
Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
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
    # From twelve trees to a hectare

    The ALS covers a 30 m radius. The ground sensors cover 15 m, and inside that
    circle only **twelve trees** were matched to an airborne crown. Everything below
    rests on those twelve.

    That is the exercise, and it is also the warning. A regression fitted on twelve
    points will look excellent in sample no matter what it is, so this notebook is
    arranged around not being fooled by it:

    | | |
    |---|---|
    | **every model is cross-validated** | leave-one-out, refitting twelve times |
    | **the null model is in the table** | predict the mean for every tree; anything that cannot beat it has learned nothing |
    | **the back-transform is corrected** | a log-log fit predicts the median, so summing it underestimates the total |
    | **the sensor is swapped** | fit on MLS volumes, then on TLS volumes, and see how far the answer moves |

    **What this cannot do.** One plot, one stand, one date. The result is a
    demonstration of the method, not a model of Swedish forest. Anything fitted here
    applies to this plot and species mix and nothing else.
    """)
    return


@app.cell
def _():
    from pathlib import Path

    import altair as alt
    import matplotlib
    import numpy as np
    import pandas as pd

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from novatrees import drop_fragments, join_sensors, match_by_crown
    from novatrees.upscale import (
        DEFAULT_SPECS,
        compare,
        fit_model,
        loocv,
        plot_total,
        predict,
    )

    REPO = Path(__file__).resolve().parents[2]
    DAY4 = REPO / "out" / "day04"
    OUTDIR = REPO / "out" / "day05"
    return (
        DAY4,
        DEFAULT_SPECS,
        OUTDIR,
        alt,
        compare,
        drop_fragments,
        fit_model,
        join_sensors,
        match_by_crown,
        loocv,
        np,
        pd,
        plot_total,
        plt,
        predict,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 1: the training set, and what it is made of

    Two files, both written by the Day 4 notebook. The joined table carries one row
    per matched tree, ground columns beside airborne ones. The ALS tree table carries
    every crown the helicopter found, which is what the model will be applied to.
    """)
    return


@app.cell
def _(DAY4, drop_fragments, mo, np, pd):
    _als = DAY4 / "trees_ALS_heuristic.csv"
    _vols = {_s: DAY4 / f"volumes_{_s}_heuristic.csv" for _s in ("MLS", "TLS")}
    mo.stop(not (_als.exists() and _vols["MLS"].exists()),
            mo.md(f"*Run the Day 4 notebook first: `{_vols['MLS']}` is missing.*"))

    # Per-sensor stem volumes, unjoined: the matching happens below, so that the rule
    # can be changed without rerunning Day 4.
    volumes = {}
    for _s, _p in _vols.items():
        if not _p.exists():
            continue
        _v = pd.read_csv(_p).rename(columns={"tree_id": "treeID"})
        volumes[_s] = _v

    # Every ALS crown the model will be applied to, debris and edge trees removed.
    als_trees = drop_fragments(pd.read_csv(_als))
    # A fitted model is applied to suffixed columns, so the raw table needs the
    # same names the joined frame will carry.
    als_air = als_trees.rename(columns={c: f"{c}_air" for c in als_trees.columns})

    PLOT_RADIUS_M = 30.0
    AREA_HA = float(np.pi * PLOT_RADIUS_M**2 / 10_000)

    mo.md(
        f"""
        | | |
        |---|---:|
        | ground stems with a volume, MLS | {len(volumes.get('MLS', []))} |
        | ground stems with a volume, TLS | {len(volumes.get('TLS', []))} |
        | with a modelled whole-stem volume (MLS) | {int(volumes['MLS'].vol_model_relaxed_m3.notna().sum())} |
        | ALS crowns to predict | {len(als_air)} |
        | ALS footprint | {AREA_HA:.3f} ha ({PLOT_RADIUS_M:.0f} m radius) |

        The two ground sensors see the same stems, so they are kept separate and used
        as a robustness check rather than pooled: the same trees, measured twice.
        """
    )
    return AREA_HA, als_air, als_trees, volumes


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Which stem does a crown belong to?

    The Day 4 join used nearest neighbour: each crown apex takes the closest stem
    within 3 m. That asks the wrong question. **An airborne crown is the top of one
    tree**, the one that reached the light there, and every other stem underneath it
    is a tree the helicopter could not see. Those are omissions, not matching
    failures, and calling them "unmatched" hides the single largest limitation of
    airborne inventory in a layered stand.

    `match_by_crown` asks the right question instead: collect every stem standing
    inside the crown footprint, give the crown to the **dominant** one, and record the
    rest as suppressed. A height check stops the rule from handing a 25 m crown to a
    6 m sapling standing under it, which is its obvious failure mode and which it did
    on this plot before the check existed.
    """)
    return


@app.cell
def _(mo):
    matcher = mo.ui.dropdown(
        ["crown ownership", "nearest neighbour"],
        value="crown ownership", label="matching rule",
    )
    crown_scale = mo.ui.slider(0.6, 1.6, value=1.0, step=0.1,
                               label="crown footprint scale", show_value=True)
    height_tol = mo.ui.slider(1.0, 10.0, value=4.0, step=0.5,
                              label="max height disagreement (m)", show_value=True)
    mo.vstack([matcher, crown_scale, height_tol])
    return crown_scale, height_tol, matcher


@app.cell
def _(
    als_trees,
    crown_scale,
    height_tol,
    join_sensors,
    match_by_crown,
    matcher,
    mo,
    volumes,
):
    if matcher.value == "crown ownership":
        joined = {
            _s: match_by_crown(_v, als_trees, scale=float(crown_scale.value),
                               max_height_diff=float(height_tol.value))
            for _s, _v in volumes.items()
        }
    else:
        joined = {
            _s: join_sensors(_v, als_trees, max_distance=3.0)
            for _s, _v in volumes.items()
        }

    _at = joined["MLS"].attrs
    if matcher.value == "crown ownership":
        _msg = f"""
        | | |
        |---|---:|
        | ground stems | {_at['n_ground']} |
        | standing under some crown | {_at['n_matched'] + _at['n_suppressed']} |
        | **owning a crown, so matched** | **{_at['n_matched']}** |
        | **suppressed, under a taller neighbour** | **{_at['n_suppressed']}** |
        | under no crown at all | {_at['n_ground_outside']} |
        | crowns with no stem beneath | {_at['n_air_empty']} |
        | median apex to stem offset | {_at['median_offset']:.2f} m |

        **The helicopter sees {100 * _at['n_matched'] / _at['n_ground']:.0f} per cent
        of the stems standing in this plot.** The other
        {_at['n_suppressed']} are under a crown belonging to something taller. That is
        not a tuning failure and no regression fixes it: those trees left no return in
        the canopy surface. It is the number to quote beside any per-hectare total
        below, because the total is over dominant trees, not over the forest.

        The {_at['n_air_empty']} empty crowns are mostly legitimate: the ALS covers a
        30 m radius and the ground sensors only 15 m, so most of them stand where no
        ground sensor ever looked.
        """
    else:
        _msg = f"""
        Nearest neighbour: **{_at['n_matched']} matched** of {_at['n_ground']} ground
        stems and {_at['n_air']} crowns, median offset {_at['median_offset']:.2f} m.
        Unmatched stems are counted but not explained. Switch to crown ownership to see
        how many of them are suppressed rather than missed.
        """
    mo.md(_msg)
    return (joined,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 2: which volume are we upscaling?

    Day 4 produced three, and they are three different claims. The choice matters more
    than any predictor below, so make it deliberately.

    | column | what it is |
    |---|---|
    | `vol_measured_strict_m3` | measured, spans a median 30 per cent of stem height |
    | `vol_measured_relaxed_m3` | measured, spans a median 75 per cent |
    | `vol_model_relaxed_m3` | the fitted taper integrated to the tip, refused where it did not close |
    """)
    return


@app.cell
def _(mo):
    response = mo.ui.dropdown(
        {
            "modelled whole stem (vol_model_relaxed)": "vol_model_relaxed_m3_ground",
            "measured, relaxed (vol_measured_relaxed)": "vol_measured_relaxed_m3_ground",
            "measured, strict (vol_measured_strict)": "vol_measured_strict_m3_ground",
        },
        value="modelled whole stem (vol_model_relaxed)",
        label="volume to upscale",
    )
    source = mo.ui.dropdown(["MLS", "TLS"], value="MLS", label="ground sensor as truth")
    mo.vstack([response, source])
    return response, source


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 3: every candidate model, cross-validated

    Read **`R2 cv`** and **`RMSE cv %`**, and treat the in-sample columns as a measure
    of optimism rather than of quality. The gap between `R2` and `R2 cv` is that
    optimism made visible.

    A negative `R2 cv` is not a bug. It means the model predicts a held-out tree worse
    than the training mean would, which happens easily at this sample size and is the
    single most useful thing the table can tell you.
    """)
    return


@app.cell
def _(compare, joined, mo, response, source):
    table = compare(joined[source.value], response.value)
    _best = table.dropna(subset=["R2 cv"]).sort_values("RMSE cv").head(1)
    mo.vstack([
        mo.ui.table(table.drop(columns=["note"]), selection=None),
        mo.md(
            f"""
            Best by cross-validated error: **{_best.model.iloc[0]}**,
            RMSE {_best['RMSE cv'].iloc[0]:.3f} m3
            ({_best['RMSE cv %'].iloc[0]:.1f} per cent of the mean tree),
            R2 cv {_best['R2 cv'].iloc[0]:.3f}.

            `correction` is the Baskerville factor applied on the back-transform. A
            log-log fit predicts the conditional **median**, so exponentiating without
            it biases every total low, by that factor.
            """
        ),
    ])
    return (table,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### The response variable matters more than the predictors

    Run the table above once for each volume column and the pattern is stark. On this
    plot, with height and crown volume as predictors:

    | response | n | R2 cv | RMSE cv |
    |---|---:|---:|---:|
    | modelled whole stem | 10 | **+0.557** | 19.8 % |
    | measured, relaxed | 12 | -0.054 | 41.3 % |

    **The partial volumes are barely predictable from the air, and the whole-stem
    estimate is.** That follows from what each one is. A partial volume depends on how
    far up the stem the ground reconstruction happened to reach, which is a property of
    occlusion and return density, and the helicopter knows nothing about either. The
    modelled volume is a property of the tree.

    It is also the answer to a fair objection against the Day 4 work: the modelled
    column is the one carrying extrapolation, so it looked like the least trustworthy
    of the three. It is the only one that upscales.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### The better matching gives the worse-looking model

    Switching the matching rule at the top changes the training set, and the result is
    uncomfortable in a useful way. Same response, same predictors, height and crown
    volume:

    | matching | n | fitted | R2 cv | RMSE cv |
    |---|---:|---|---:|---:|
    | nearest neighbour | 10 | `V = 2.81e-07 h_max^4.060 crown_volume^0.326` | **+0.557** | 19.8 % |
    | crown ownership | 11 | `V = 0.000897 h_max^1.523 crown_volume^0.341` | -0.116 | 29.9 % |

    **The physically better rule produces a physically better exponent and a worse
    prediction.** A stem is roughly a cone, so height should enter at a power near 2 to
    3 once crown size is accounted for. Nearest neighbour returned 4.06, which is not a
    taper relationship, it is a small sample letting one variable absorb the
    correlation with everything else. Crown ownership returns 1.52, and predicts worse.

    The explanation is selection. Nearest-neighbour matching within 3 m quietly keeps
    the trees whose stem base sits almost under their own apex: isolated, upright,
    dominant trees. That is an easier sample, not a better one, and its flattering
    cross-validation score came from the sample rather than from the model.

    The honest reading of the second row is that **eleven trees cannot support this
    regression**, which was equally true of the first row and was hidden by the
    selection. Neither number is a model of anything. That is the finding.
    """)
    return


@app.cell
def _(mo):
    model_pick = mo.ui.dropdown(
        ["height + crown volume", "height only", "height + crown area",
         "crown volume only", "crown area only", "height + crown area + p50",
         "null (mean volume)"],
        value="height + crown volume", label="model to carry forward",
    )
    model_pick
    return (model_pick,)


@app.cell
def _(DEFAULT_SPECS, fit_model, joined, loocv, mo, model_pick, response, source):
    spec = next(s for s in DEFAULT_SPECS if s.name == model_pick.value)
    fit = fit_model(joined[source.value], response.value, spec)
    cv = loocv(joined[source.value], response.value, spec)

    mo.md(
        f"""
        ### {spec.name}, fitted on {source.value}

        $$\\texttt{{{fit.equation()}}}$$

        | | |
        |---|---:|
        | trees used | {fit.n} |
        | residual sigma, log space | {fit.sigma_log:.3f} |
        | Baskerville correction | {fit.correction:.4f} |
        | RMSE, in sample | {fit.rmse:.3f} m3 |
        | **RMSE, leave-one-out** | **{cv['rmse']:.3f} m3** ({cv['rmse_pct']:.1f} %) |
        | **R2, leave-one-out** | **{cv['r2']:.3f}** |
        | bias, leave-one-out | {cv['bias']:+.4f} m3 |

        The exponent on height is the number to look at. A stem is roughly a cone, so
        volume should go as height to a power between 2 and 3 once crown size is
        accounted for. Anything far above that is the fit absorbing the correlation
        between height and everything else in a twelve-tree sample, not a physical
        relationship.
        """
    )
    return cv, fit, spec


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Diagnostics

    Observed against predicted, and the residuals. With twelve points, look at
    individual trees rather than at a trend line: one influential tree can carry the
    whole fit.
    """)
    return


@app.cell
def _(cv, fit, joined, mo, np, plt, response, source, spec):
    mo.stop(not np.isfinite(cv["rmse"]), mo.md("*Too few trees for this model.*"))

    _d = joined[source.value].dropna(subset=[response.value, *spec.predictors])
    _obs = cv["observed"]
    _pred = cv["predicted"]

    _f, _ax = plt.subplots(1, 3, figsize=(13.5, 4.3))
    _lim = float(max(_obs.max(), _pred.max())) * 1.1

    _ax[0].scatter(_obs, fit.fitted, s=60, c="#8aa8c8", edgecolors="k", linewidths=.4,
                   label="in sample")
    _ax[0].scatter(_obs, _pred, s=60, c="#9c3626", marker="^", edgecolors="k",
                   linewidths=.4, label="left out")
    _ax[0].plot([0, _lim], [0, _lim], "--", c="0.4", lw=1)
    _ax[0].set_xlabel("observed volume (m3)"); _ax[0].set_ylabel("predicted (m3)")
    _ax[0].set_xlim(0, _lim); _ax[0].set_ylim(0, _lim)
    _ax[0].set_title("the gap between the two is the optimism", fontsize=10)
    _ax[0].legend(fontsize=8)

    _res = _obs - _pred
    _ax[1].axhline(0, c="0.4", lw=1, ls="--")
    _ax[1].scatter(_pred, _res, s=60, c="#9c3626", edgecolors="k", linewidths=.4)
    for _x, _y, _t in zip(_pred, _res, _d.treeID_ground):
        _ax[1].annotate(int(_t), (_x, _y), fontsize=7, xytext=(4, 3),
                        textcoords="offset points", color="#5f6a5c")
    _ax[1].set_xlabel("predicted (m3)"); _ax[1].set_ylabel("observed - predicted (m3)")
    _ax[1].set_title("held-out residuals, labelled by tree", fontsize=10)

    _ax[2].scatter(_d[spec.predictors[0]], _obs, s=60, c="#2b5d8a",
                   edgecolors="k", linewidths=.4)
    _ax[2].set_xlabel(spec.predictors[0].replace("_air", " (ALS)"))
    _ax[2].set_ylabel("observed volume (m3)")
    _ax[2].set_title("the strongest single predictor", fontsize=10)
    _f.tight_layout()

    mo.vstack([
        _f,
        mo.md(
            f"Worst held-out tree: **{int(_d.treeID_ground.iloc[int(np.argmax(np.abs(_res)))])}**, "
            f"off by {np.abs(_res).max():.3f} m3. On twelve trees that one tree is "
            f"{100 * _res.max()**2 / np.sum(_res**2):.0f} per cent of the total squared error."
        ),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 4: swap the sensor, and see how much the answer moves

    The same twelve trees have two ground-derived volumes, one from MLS and one from
    TLS. Neither is truth. Fitting the same model to each gives an error bar that no
    internal statistic can produce: **how much does the upscaled total depend on which
    instrument we believed?**
    """)
    return


@app.cell
def _(als_air, fit_model, joined, mo, np, predict, response, spec):
    mo.stop(len(joined) < 2, mo.md("*Both sensors are needed for this.*"))

    _rows = []
    _pred = {}
    for _s, _df in joined.items():
        _f = fit_model(_df, response.value, spec)
        _p = predict(_f, als_air)
        _pred[_s] = _p
        _rows.append((_s, _f, _p))

    _a, _b = _rows[0], _rows[1]
    _ratio = np.nansum(_a[2]) / np.nansum(_b[2])

    mo.md(
        f"""
        | fitted on | n | equation | total over {int(np.isfinite(_a[2]).sum())} ALS trees |
        |---|---:|---|---:|
        | {_a[0]} | {_a[1].n} | `{_a[1].equation()}` | {np.nansum(_a[2]):.1f} m3 |
        | {_b[0]} | {_b[1].n} | `{_b[1].equation()}` | {np.nansum(_b[2]):.1f} m3 |

        **The two totals differ by {abs(1 - _ratio) * 100:.0f} per cent**, and the
        height exponent differs by
        {abs(_a[1].coef[1] - _b[1].coef[1]):.2f}.

        That is not a defect in either sensor. It is the honest width of this result:
        two instruments measuring the same twelve stems disagree enough to move the
        upscaled total by a quarter, and no amount of cross-validation inside one
        sensor's data would have revealed it. Quote it beside any number below.
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 5: apply it to the whole ALS footprint

    Every airborne crown gets a predicted volume, including the ones standing where no
    ground sensor ever reached. This is the step the airborne data exists for.
    """)
    return


@app.cell
def _(AREA_HA, als_air, cv, fit, mo, np, plot_total, predict):
    predicted = predict(fit, als_air)
    totals = plot_total(predicted, AREA_HA, cv_rmse=cv["rmse"])

    _lo, _hi = totals.get("sampling_ci_per_ha", (float("nan"), float("nan")))
    mo.md(
        f"""
        | | |
        |---|---:|
        | ALS crowns predicted | {totals['n_trees']} |
        | mean predicted tree | {totals['mean_tree_m3']:.3f} m3 |
        | **plot total** | **{totals['total_m3']:.1f} m3** |
        | **volume per hectare** | **{totals['per_ha_m3']:.0f} m3/ha** |
        | stems per hectare | {totals['stems_per_ha']:.0f} |
        | sampling interval, 95 % | {_lo:.0f} to {_hi:.0f} m3/ha |
        | model error if independent | {totals.get('model_error_independent_m3', float('nan')):.1f} m3 |
        | model error if correlated | {totals.get('model_error_correlated_m3', float('nan')):.1f} m3 |

        **Read the last two rows together.** Summing n trees each with a
        cross-validated error grows as `sqrt(n) * rmse` if the errors are independent
        and as `n * rmse` if they are not. A model fitted on twelve trees from one plot
        makes correlated errors, so the truth is much closer to the second number: the
        plot total carries something like
        {100 * totals.get('model_error_correlated_m3', float('nan')) / totals['total_m3']:.0f}
        per cent of model uncertainty, not
        {100 * totals.get('model_error_independent_m3', float('nan')) / totals['total_m3']:.0f}
        per cent.

        A boreal stand of this height typically carries 150 to 300 m3/ha, so the
        number is plausible. Plausible is not validated.
        """
    )
    return predicted, totals


@app.cell
def _(alt, als_air, mo, np, pd, predicted):
    mo.stop(not np.isfinite(predicted).any(), mo.md("*No predictions.*"))

    _d = pd.DataFrame({
        "x": als_air.x_air - als_air.x_air.mean(),
        "y": als_air.y_air - als_air.y_air.mean(),
        "volume": predicted,
        "height": als_air.h_max_air,
        "crown": als_air.crown_area_m2_air,
        "tree": als_air.treeID_air,
    }).dropna(subset=["volume"])

    _map = (
        alt.Chart(_d).mark_circle(opacity=.8)
        .encode(
            x=alt.X("x:Q", title="x from plot centre (m)"),
            y=alt.Y("y:Q", title="y from plot centre (m)"),
            size=alt.Size("volume:Q", title="predicted m3",
                          scale=alt.Scale(range=[30, 600])),
            color=alt.Color("height:Q", title="ALS h_max (m)",
                            scale=alt.Scale(scheme="viridis")),
            tooltip=["tree:Q", "volume:Q", "height:Q", "crown:Q"],
        )
        .properties(width=430, height=430, title="predicted stem volume across the ALS footprint")
    )
    _hist = (
        alt.Chart(_d).mark_bar(opacity=.85, color="#2b5d8a")
        .encode(x=alt.X("volume:Q", bin=alt.Bin(maxbins=22), title="predicted volume (m3)"),
                y=alt.Y("count()", title="trees"))
        .properties(width=330, height=430, title="distribution")
    )
    mo.vstack([
        alt.hconcat(_map, _hist),
        mo.md(
            "Each circle is an airborne crown, sized by its predicted stem volume. "
            "**The trees near the centre are the only ones a ground sensor ever "
            "measured**, and the model was fitted on twelve of them. Everything "
            "further out is extrapolation in space as well as in size: check that no "
            "predicted tree sits outside the range of heights and crowns the model was "
            "trained on, because a power law extrapolates enthusiastically."
        ),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Is any predicted tree outside the training range?

    A power law fitted over a narrow range and applied outside it is the classic way to
    produce a confident wrong number. This checks rather than assumes.
    """)
    return


@app.cell
def _(als_air, fit, joined, mo, np, pd, response, source, spec):
    _train = joined[source.value].dropna(subset=[response.value, *spec.predictors])
    _rows = []
    for _p in spec.predictors:
        _lo, _hi = float(_train[_p].min()), float(_train[_p].max())
        _v = als_air[_p].to_numpy(dtype=float)
        _out = np.isfinite(_v) & ((_v < _lo) | (_v > _hi))
        _rows.append({
            "predictor": _p.replace("_air", ""),
            "training range": f"{_lo:.1f} to {_hi:.1f}",
            "ALS range": f"{np.nanmin(_v):.1f} to {np.nanmax(_v):.1f}",
            "trees outside": int(_out.sum()),
            "share outside": f"{100 * _out.mean():.0f} %",
        })
    _t = pd.DataFrame(_rows)
    _any_out = sum(int(r["trees outside"]) for r in _rows)
    mo.vstack([
        mo.ui.table(_t, selection=None),
        mo.md(
            f"**{_any_out} predictor values fall outside the range the model was "
            f"fitted on.** Those predictions are extrapolation, and a power law whose "
            f"leading exponent is {fit.coef[1]:.2f} amplifies whatever it is given. If "
            f"the count is large, the honest move is to report the total only over the "
            f"trees inside the training range, and to say what was excluded."
            if _any_out else
            "**Every ALS tree falls inside the range the model was fitted on**, which "
            "is the one favourable thing about a plot where the ground sensors covered "
            "the middle and the helicopter covered the same stand around it."
        ),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 6: stop naming the tree, and count instead

    Everything above models the **dominant** stem under each crown, and on this plot
    that throws away 22 of 38 stems. A different question keeps them: *how many trees
    stand under this crown, and what do they add up to?*

    That changes the unit of analysis from the tree to the crown, and it changes the
    quantity to model from the volume **of** a stem to the volume **under** a crown.
    The second is the right target for upscaling, because summing it over every
    airborne crown recovers the suppressed trees, while summing a dominant-stem model
    reproduces the airborne undercount by construction.

    It also sidesteps the hardest part of matching. Naming the owner needs the stem
    detected, segmented and ranked correctly; counting needs only that it was
    detected. And with two ground sensors, the count can be averaged and their
    disagreement used as its error bar.

    One correctness detail: **crowns overlap**, so a stem can fall inside several
    footprints. Counting it in each inflates the total, on this plot from 38 stems to
    54. Each stem is therefore given to the single crown whose apex is nearest, which
    makes the crowns a partition and the sums addable.
    """)
    return


@app.cell
def _(als_trees, average_occupancy, crown_occupancy, crown_scale, mo, volumes):
    occupancy = {
        _s: crown_occupancy(_v, als_trees, scale=float(crown_scale.value),
                            exclusive=True)
        for _s, _v in volumes.items()
    }
    occ = average_occupancy(occupancy) if len(occupancy) > 1 else \
        list(occupancy.values())[0]
    occupied = occ[(occ.n_stems > 0) & occ.stem_volume_sum.notna()].copy()

    _rows = "\n".join(
        f"| {_s} | {_o.attrs['n_crowns_occupied']} | {_o.attrs['n_stems_covered']} "
        f"of {_o.attrs['n_ground']} | {_o.attrs['stems_per_occupied_crown']:.2f} |"
        for _s, _o in occupancy.items()
    )
    mo.md(
        f"""
        | sensor | crowns occupied | stems placed | stems per occupied crown |
        |---|---:|---:|---:|
        {_rows}
        | **averaged** | **{len(occupied)}** | | **{occupied.n_stems.mean():.2f}** |

        Median disagreement between the two sensors: **{occupied.n_stems_spread.median():.1f}
        stem** per crown. That is the honest error bar on a count, and no single-sensor
        statistic could produce it.

        Median share of the volume under a crown belonging to trees that are **not** its
        dominant stem: **{occupied.suppressed_volume_share.median():.2f}**.
        """
    )
    return occ, occupied


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Can a crown predict what stands under it?

    Same machinery, crowns instead of trees. Read `R2 cv` and expect to be
    disappointed.
    """)
    return


@app.cell
def _(compare, mo, occupied):
    from novatrees.upscale import ModelSpec as _MS

    _specs = (
        _MS("null (mean)", (), log=False),
        _MS("crown area", ("crown_area_m2_air",)),
        _MS("crown volume", ("crown_volume_m3_air",)),
        _MS("height", ("h_max_air",)),
        _MS("height + crown area", ("h_max_air", "crown_area_m2_air")),
        _MS("height + crown volume", ("h_max_air", "crown_volume_m3_air")),
    )
    _vol = compare(occupied, "stem_volume_sum", _specs)
    _cnt = compare(occupied, "n_stems", _specs)
    mo.vstack([
        mo.md("**Volume under the crown**"),
        mo.ui.table(_vol[["model", "n", "R2", "R2 cv", "RMSE cv", "RMSE cv %"]],
                    selection=None),
        mo.md("**Number of stems under the crown**"),
        mo.ui.table(_cnt[["model", "n", "R2", "R2 cv", "RMSE cv", "RMSE cv %"]],
                    selection=None),
        mo.md(
            """
            **Neither works, and the second fails completely.** On fourteen crowns the
            best volume model reaches R2 cv +0.12 with a 53 per cent error, and *every*
            stem-count model loses to predicting the mean.

            That is worth more than a fitted line. The crown-level quantity is the one
            an unbiased stand total actually needs, and it is much harder than the
            dominant-stem quantity that looked so promising earlier. The earlier score
            came from modelling an easier thing on a selected sample.

            How many trees hide under a crown is not written in that crown's height or
            width, at least not here. It is a property of the stand's layering, which
            is why the next cell stops trying to model it per crown and uses a
            stand-level ratio instead.
            """
        ),
    ])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### A ratio estimator instead of a model

    When the per-unit relationship cannot be fitted, the classical answer is not to
    fit a worse one. It is to measure the **ratio** on the sample where both are known
    and apply it to the whole:

    $$R = \frac{\sum_i V_i^{\text{under crown}}}{\sum_i V_i^{\text{dominant}}}$$

    A ratio of sums, not a mean of ratios, because it is the totals that get expanded.
    The interval comes from bootstrapping crowns.
    """)
    return


@app.cell
def _(AREA_HA, mo, np, occupied, totals):
    _o = occupied[occupied.stem_volume_dominant > 0]
    _R = float(_o.stem_volume_sum.sum() / _o.stem_volume_dominant.sum())
    _rng = np.random.default_rng(0)
    _idx = _rng.integers(0, len(_o), size=(2000, len(_o)))
    _num = _o.stem_volume_sum.to_numpy()[_idx].sum(axis=1)
    _den = _o.stem_volume_dominant.to_numpy()[_idx].sum(axis=1)
    _boot = _num / np.where(_den > 0, _den, np.nan)
    _lo, _hi = np.nanpercentile(_boot, [2.5, 97.5])

    _dom_total = totals["total_m3"]
    _stems = float(occupied.n_stems.mean()) * totals["n_trees"]

    mo.md(
        f"""
        | | |
        |---|---:|
        | crowns with both quantities | {len(_o)} |
        | **expansion ratio R** | **{_R:.3f}** (95 % {_lo:.2f} to {_hi:.2f}) |
        | per-crown ratio, median | {(_o.stem_volume_sum / _o.stem_volume_dominant).median():.2f} |
        | per-crown ratio, range | {(_o.stem_volume_sum / _o.stem_volume_dominant).min():.2f} to {(_o.stem_volume_sum / _o.stem_volume_dominant).max():.2f} |

        Applying it to the dominant-stem total of {_dom_total:.1f} m3:

        | | dominant stems only | corrected for what stands under them |
        |---|---:|---:|
        | plot total | {_dom_total:.1f} m3 | **{_dom_total * _R:.1f} m3** |
        | **per hectare** | {_dom_total / AREA_HA:.0f} m3/ha | **{_dom_total * _R / AREA_HA:.0f} m3/ha** |
        | 95 % on the ratio alone | | {_dom_total * _lo / AREA_HA:.0f} to {_dom_total * _hi / AREA_HA:.0f} m3/ha |
        | stems per hectare | {totals['stems_per_ha']:.0f} | **{_stems / AREA_HA:.0f}** |

        **The dominant-stem total was missing about a third of the wood**, and more
        than half the stems. The ground plot itself holds 38 stems in 0.071 ha, near
        540 per hectare, so the corrected stem density is the right order and the
        uncorrected one was not.

        The interval above covers the ratio only. It does not include the regression
        error, the sensor disagreement, or the fact that crowns outside the ground
        coverage are assumed to be layered like the ones inside it. That last
        assumption is the shakiest thing on this page: the ratio was measured on
        {len(_o)} crowns near the plot centre and applied to {totals['n_trees']}.
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Step 7: write it out
    """)
    return


@app.cell
def _(mo):
    do_write = mo.ui.run_button(label="Write the upscaled table")
    do_write
    return (do_write,)


@app.cell
def _(OUTDIR, als_air, do_write, fit, mo, occ, pd, predicted, spec, totals):
    mo.stop(not do_write.value, mo.md("*Press to write.*"))
    OUTDIR.mkdir(parents=True, exist_ok=True)

    _out = als_air.copy()
    _out["volume_predicted_m3"] = predicted
    _out.attrs["model"] = fit.equation()
    _p = OUTDIR / "als_predicted_volume.csv"
    _out.to_csv(_p, index=False)

    _o = OUTDIR / "crown_occupancy.csv"
    occ.to_csv(_o, index=False)

    _summary = pd.DataFrame([{
        "model": spec.name, "equation": fit.equation(), "n_train": fit.n,
        **{k: v for k, v in totals.items() if not isinstance(v, tuple)},
    }])
    _s = OUTDIR / "upscaled_summary.csv"
    _summary.to_csv(_s, index=False)
    mo.md(f"Wrote `{_p.name}` ({len(_out)} trees), `{_o.name}` "
          f"({len(occ)} crowns) and `{_s.name}` to `{OUTDIR}`.")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---

    ## What would make this a model rather than a demonstration

    In the order that would help most:

    1. **More plots.** Twelve trees from one plot cannot separate a species effect
       from a site effect from a sampling accident. Ten plots of twelve trees would be
       worth more than one plot of a hundred and twenty.
    2. **A held-out plot**, never touched during fitting. Leave-one-out on twelve
       trees measures how well the model interpolates between those twelve, which is a
       weaker claim than it sounds.
    3. **Species.** A power law fitted across pine, spruce and birch together is an
       average of three different taper forms. The Day 3 stand is explicitly mixed.
    4. **Better ground truth.** The response here is itself partly modelled, and
       swapping MLS for TLS moved the total by a quarter. That number is the floor on
       what any regression fitted here can achieve.
    5. **The trees the ALS missed.** Only 53 crowns survive filtering over 0.283 ha,
       roughly 187 stems per hectare, while the ground sensors found 38 to 48 stems in
       a plot an eighth of that area, near 600 per hectare. **The helicopter is not
       seeing most of the stand**, so the per-hectare total above is a total over
       dominant trees, not over the forest. That is the largest single caveat on this
       page and it is a detection problem, not a regression problem.
    """)
    return


if __name__ == "__main__":
    app.run()
