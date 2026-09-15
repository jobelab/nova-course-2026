"""Individual project, step 6: stems and diameter, which only the ground sensors give.

Interactive. Stems come from `analysis.stems()`, cached to out/project. Switch the fit
and the reference and the scoring recomputes.

A narrative-only copy is in `narrative/`.

SPDX-License-Identifier: GPL-3.0-or-later
Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University

Run:  uv run marimo edit notebooks/project/05_stems_from_below.py --watch
"""

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "project"))
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    import _common as C
    import analysis as A
    from novatrees.evaluate import match_positions

    ST = A.stems()
    FIELD, CURRENT = C.field_stems(), C.current_dbh()
    REFS = {
        "2011 field survey": (FIELD.XCENT.to_numpy(), FIELD.YCENT.to_numpy(), FIELD.dbh.to_numpy()),
        "contemporaneous list": (CURRENT.X.to_numpy(), CURRENT.Y.to_numpy(), CURRENT.DBH.to_numpy()),
    }

    def score(cloud, fit, refname, whole_plot):
        q = ST[(ST.cloud == cloud) & (ST.fit == fit)]
        P = q[["x", "y", "dbh"]].to_numpy()
        rx, ry, rd = REFS[refname]
        keep = np.ones(len(rx), bool) if whole_plot else C.in_box(rx, ry)
        R = np.column_stack([rx[keep], ry[keep]])
        m = match_positions(P[:, :2], R, tol=2.0)
        cost = np.linalg.norm(P[:, None, :2] - R[None, :, :], axis=2)
        i, j = linear_sum_assignment(cost)
        ok = cost[i, j] <= 2.0
        est, ref = P[i[ok], 2], rd[keep][j[ok]]
        err = est - ref
        return dict(n_ref=int(keep.sum()), n_det=len(P), **m, dbh_n=int(ok.sum()),
                    bias=float(err.mean()) if ok.any() else float("nan"),
                    rmse=float(np.sqrt((err**2).mean())) if ok.any() else float("nan"),
                    r=float(np.corrcoef(est, ref)[0, 1]) if ok.sum() > 2 else float("nan"))

    return A, C, CURRENT, FIELD, REFS, ST, linear_sum_assignment, match_positions, np, score


@app.cell(hide_code=True)
def _(C, FIELD, mo, np):
    n_box = int(C.in_box(FIELD.XCENT, FIELD.YCENT).sum())
    mo.md(
        f"""
        # Measuring stems

        ## The scored area has to match the delivered area

        TLS and MLS arrive as a 30 by 30 m box on the plot centre, which is 900 m².
        The plot is a 20 m circle, which is {np.pi * C.PLOT_R**2:.0f} m². **About 28 % of
        the plot was never scanned**, and only **{n_box} of the {len(FIELD)} field stems**
        fall inside the box. Scoring over the whole circle counts undelivered data as a
        miss, which is what the toggle below demonstrates.
        """
    )
    return


@app.cell
def _(mo):
    whole = mo.ui.checkbox(value=False, label="score over the whole plot circle "
                                             "(counts ground the scanners never covered)")
    ref_pick = mo.ui.dropdown(["2011 field survey", "contemporaneous list"],
                              value="2011 field survey", label="reference")
    mo.hstack([ref_pick, whole], justify="start", gap=2)
    return ref_pick, whole


@app.cell(hide_code=True)
def _(mo, ref_pick, score, whole):
    fit_rows = []
    for s_cloud in ("TLS", "MLS"):
        for s_fit, s_label in (("taubin", "Taubin, loose gates"), ("ransac", "RANSAC + gates")):
            r = score(s_cloud, s_fit, ref_pick.value, whole.value)
            fit_rows.append(
                f"| {s_cloud} | {s_label} | {r['n_det']} | {r['recall']:.3f} | "
                f"{r['precision']:.3f} | **{r['f1']:.3f}** | {r['bias']:+.2f} cm | "
                f"{r['rmse']:.2f} cm | **{r['r']:+.3f}** |")
    mo.md(
        f"### Against the {ref_pick.value}"
        + (", scored over the whole circle" if whole.value else ", scored over the scanned box")
        + "\n\n| cloud | fit | stems | recall | precision | F1 | DBH bias | DBH RMSE | r |\n"
          "|---|---|---:|---:|---:|---:|---:|---:|---:|\n" + "\n".join(fit_rows)
    )
    return


@app.cell(hide_code=True)
def _(CURRENT, FIELD, ST, mo):
    q = ST[(ST.cloud == "TLS") & (ST.fit == "ransac")]
    mo.md(
        f"""
        ### What the two toggles show

        **The fit.** A Taubin circle over every point in a cluster has no defence against
        a low branch or a neighbouring stem being in that cluster, and returns diameters
        with essentially no relationship to the field. The same clusters fitted by RANSAC
        and gated on roundness, arc coverage and vertical continuity give r near +0.97.
        That is not a precision improvement; it is the difference between measuring the
        stem and measuring the cluster. Median fit residual here is
        {q.sigma.median()*1000:.1f} mm over a median arc coverage of {q.arc.median():.2f}.

        **The reference.** Against the 2011 survey the diameters are biased high by about
        4 cm. That is not error, it is growth: median plot DBH was
        {FIELD.dbh.median():.1f} cm in 2011 and is {CURRENT.DBH.median():.1f} cm now,
        **{CURRENT.DBH.median()-FIELD.dbh.median():+.1f} cm in fifteen years**. Switch the
        reference to the contemporaneous list and the bias nearly vanishes.

        **But treat that second comparison as a check on the implementation rather than
        validation.** The contemporaneous list carries millimetre heights for 441 trees,
        which no field crew produces, so it is almost certainly derived from this same
        laser scanning. Agreement at r = 0.999 says this pipeline reproduces another
        processing of the same data. It does not say the data are right.

        ### What this settles for RQ5

        A canopy height model took the same TLS cloud to F1 0.566 in the previous chapter.
        The stem cross-section takes it to 0.800. **The method has to change with the
        sensor**, which is the Day 3 result reappearing from the other side. Recall near
        0.68 is occlusion: a stem behind another stem is not measured from the ground, and
        no amount of point density fixes it.
        """
    )
    return


if __name__ == "__main__":
    app.run()
