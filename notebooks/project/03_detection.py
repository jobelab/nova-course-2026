"""Individual project, step 4: canopy height models, tree detection, and scoring.

Interactive. The detections come from `analysis.detections()`, which caches to
out/project, so this notebook opens in a second once that cache exists. The scoring is
recomputed live, so the match tolerance can be moved and its effect seen.

A narrative-only copy that needs no data at all is in `narrative/`.

SPDX-License-Identifier: GPL-3.0-or-later
Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University

Run:  uv run marimo edit notebooks/project/03_detection.py --watch
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

    TOPS = A.detections()
    FIELD = C.field_stems()
    REF = FIELD[["XCENT", "YCENT"]].to_numpy(float)
    DBH = FIELD.dbh.to_numpy()
    SPECIES = FIELD.SPECIES.to_numpy(int)
    SEPS = sorted(TOPS.sep.unique())
    ORDER = ["Nadir_RGB", "Oblique_RGB", "Nadir_MS", "Oblique_MS", "ALS", "MLS", "TLS"]
    SPACING = float(np.sqrt(np.pi * C.PLOT_R**2 / len(REF)))

    def tops_of(cloud, sep):
        q = TOPS[(TOPS.cloud == cloud) & (np.isclose(TOPS.sep, sep))]
        return q[["x", "y"]].to_numpy()

    return (
        A, C, DBH, ORDER, REF, SEPS, SPACING, SPECIES, TOPS,
        linear_sum_assignment, match_positions, np, tops_of,
    )


@app.cell(hide_code=True)
def _(REF, SPACING, mo):
    mo.md(
        f"""
        # Finding trees, and counting the misses honestly

        Seven acquisitions over plot 167, all normalised against the terrain model from
        the previous chapter. The reference is **{len(REF)} stems surveyed in 2011**,
        mean spacing **{SPACING:.2f} m**.

        The scans are from 2021 onwards, so any stem that died since 2011 counts here as
        a miss that is not the sensor's fault.
        """
    )
    return


@app.cell
def _(mo):
    tol = mo.ui.slider(1.0, 4.0, step=0.25, value=2.0, label="match tolerance (m)",
                       show_value=True)
    tol
    return (tol,)


@app.cell(hide_code=True)
def _(ORDER, REF, SEPS, SPACING, match_positions, mo, tol, tops_of):
    sweep_rows = []
    for sweep_cloud in ORDER:
        f1s = [match_positions(tops_of(sweep_cloud, s), REF, tol=tol.value)["f1"] for s in SEPS]
        top = max(f1s)
        sweep_rows.append("| `" + sweep_cloud + "` | " + " | ".join(
            (f"**{v:.3f}**" if v == top else f"{v:.3f}") for v in f1s) + " |")
    sweep_warn = ""
    if tol.value > SPACING / 2:
        sweep_warn = (
            f"\n\n> **Above half the {SPACING:.2f} m mean spacing.** One treetop can now "
            f"sit within tolerance of two stems. The matching here is one-to-one so the "
            f"inflation is bounded, but independent nearest-neighbour matching at 3 m "
            f"gave 49 detections a recall of 0.865 against 74 stems.")
    mo.md(
        f"### F1 at a {tol.value:.2f} m tolerance\n\n"
        + "| cloud | " + " | ".join(f"{s} m" for s in SEPS) + " |\n"
        + "|---" * (len(SEPS) + 1) + "|\n" + "\n".join(sweep_rows) + sweep_warn
    )
    return


@app.cell(hide_code=True)
def _(ORDER, REF, SEPS, match_positions, mo, tol, tops_of):
    best_rows = []
    for best_cloud in ORDER:
        scored = []
        for s in SEPS:
            bt = tops_of(best_cloud, s)
            scored.append((match_positions(bt, REF, tol=tol.value), s, len(bt)))
        m, s, n = max(scored, key=lambda r: r[0]["f1"])
        best_rows.append(
            f"| `{best_cloud}` | {s:.1f} | {n} | {m['matched']} | {m['recall']:.3f} | "
            f"{m['precision']:.3f} | **{m['f1']:.3f}** | {m['median_offset']:.2f} m |")
    mo.md("### At each cloud's best separation\n\n"
          "| cloud | sep | tops | matched | recall | precision | F1 | offset |\n"
          "|---|---:|---:|---:|---:|---:|---:|---:|\n" + "\n".join(best_rows))
    return


@app.cell(hide_code=True)
def _(DBH, ORDER, REF, SPECIES, linear_sum_assignment, mo, np, tol, tops_of):
    qs = np.quantile(DBH, [0, .25, .5, .75, 1.0])
    dbh_rows = []
    for dbh_cloud in ORDER:
        qt = tops_of(dbh_cloud, 1.5)
        cost = np.linalg.norm(qt[:, None, :] - REF[None, :, :], axis=2)
        i, j = linear_sum_assignment(cost)
        ok = cost[i, j] <= tol.value
        hit = np.zeros(len(REF), bool)
        hit[j[ok]] = True
        cls = np.clip(np.searchsorted(qs[1:-1], DBH, side="right"), 0, 3)
        dbh_rows.append(
            f"| `{dbh_cloud}` | " + " | ".join(f"{100*hit[cls==k].mean():.0f} %" for k in range(4))
            + f" | {100*hit[SPECIES==1].mean():.0f} % | {100*hit[SPECIES==2].mean():.0f} % |")
    mo.md("### Detection rate by field DBH quartile, at 1.5 m separation\n\n"
          + "| cloud | " + " | ".join(f"{qs[i]:.0f}-{qs[i+1]:.0f} cm" for i in range(4))
          + " | pine | spruce |\n" + "|---" * 7 + "|\n" + "\n".join(dbh_rows))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## What the tables say

    **Precision is high everywhere and recall is the limit.** Between 0.93 and 0.98 of
    what these methods detect is a real surveyed stem.

    **Nadir beats oblique, for both cameras.** Worth stating plainly because it runs
    against the point counts: the oblique surveys deliver 26 to 45 % more points over the
    same ground and detect fewer trees. More points are not more information.

    **The drone is competitive with the helicopter.**

    **A canopy height model is the wrong method for the ground-based clouds.** TLS and MLS
    score 0.566 here, not because they see less but because a CHM throws away what they
    are good at. The next chapter takes the same TLS cloud to 0.800.

    **The misses are the small trees**, and a recall of 0.72 is not missing a quarter of
    the forest: it is finding almost all of the canopy and none of what grows beneath it.

    **The species split is a size split.** Pine is detected better than spruce in every
    cloud, but the spruce here are smaller and 32 of the 37 larger-half stems are pine.

    ### What this does not settle

    The reference is fifteen years older than the data, and the separation is chosen
    against the same reference it is scored on.
    """)
    return


if __name__ == "__main__":
    app.run()
