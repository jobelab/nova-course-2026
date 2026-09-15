"""Individual project, step 7: taper, volume, and a fusion argument that did not hold.

Interactive. Taper comes from `analysis.taper()`, cached to out/project, which
reconstructs every stem twice: once with a drone-supplied total height and once without.

A narrative-only copy is in `narrative/`.

SPDX-License-Identifier: GPL-3.0-or-later
Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University

Run:  uv run marimo edit notebooks/project/06_taper_and_volume.py --watch
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

    import _common as C
    import analysis as A

    TP = A.taper().dropna(subset=["volume"])
    PAIRED = TP.dropna(subset=["volume_no_h"])
    return A, C, PAIRED, TP, np


@app.cell(hide_code=True)
def _(TP, mo):
    mo.md(
        f"""
        # Taper, volume, and three answers to one question

        Each of the {len(TP)} stems was followed upward from breast height, fitted slice
        by slice with a RANSAC circle, and integrated. `taper` deliberately returns three
        volumes, because they answer different questions: the integral over the range
        actually reconstructed, an analytic model extrapolated to full height, and the
        cylinder a stem never reaches. The ratio of the first to the third is the form
        factor.
        """
    )
    return


@app.cell
def _(mo):
    cover_min = mo.ui.slider(0.0, 0.95, step=0.05, value=0.0, show_value=True,
                             label="keep stems whose reconstruction covered at least")
    cover_min
    return (cover_min,)


@app.cell(hide_code=True)
def _(TP, cover_min, mo, np):
    sub = TP[TP.covered >= cover_min.value]
    if len(sub) < 3:
        out = mo.md("Too few stems left at that threshold.")
    else:
        out = mo.md(
            f"""
            ### {len(sub)} stems above {cover_min.value:.2f} coverage

            | | median | p25 | p75 |
            |---|---:|---:|---:|
            | covered fraction | {sub.covered.median():.2f} | {sub.covered.quantile(.25):.2f} | {sub.covered.quantile(.75):.2f} |
            | form factor | **{sub.form.median():.3f}** | {sub.form.quantile(.25):.3f} | {sub.form.quantile(.75):.3f} |
            | stem volume (m³) | {sub.volume.median():.3f} | {sub.volume.quantile(.25):.3f} | {sub.volume.quantile(.75):.3f} |

            DBH from the taper curve against the independent cross-section fit:
            **r = {sub.dbh_taper.corr(sub.dbh_slice):+.3f}**. Form factor against covered
            fraction: **r = {sub.form.corr(sub.covered):+.3f}**.

            A form factor near 0.45 to 0.50 is what a boreal conifer should give, and that
            is the strongest single sign the whole chain, terrain to stem to integration,
            produces a physically sensible tree rather than a plausible-looking number.

            **Move the slider and watch the form factor rise.** It correlates with how
            much of each tree the scanner could see, so part of its spread is occlusion
            rather than tree shape. Reading a form factor as a property of the forest is a
            mistake when it is partly a property of the view.
            """
        )
    out
    return


@app.cell(hide_code=True)
def _(PAIRED, mo):
    mo.md(
        f"""
        ### The fusion argument, tested

        The same {len(PAIRED)} stems reconstructed with and without the drone height:

        | | with drone height | without |
        |---|---:|---:|
        | measured volume | {PAIRED.volume.median():.3f} m³ | {PAIRED.volume_no_h.median():.3f} m³ |
        | form factor | {PAIRED.form.median():.3f} | {PAIRED.form_no_h.median():.3f} |
        | covered fraction | {PAIRED.covered.median():.3f} | {PAIRED.covered_no_h.median():.3f} |

        **The volume is identical and the form factor moves by about 0.01.** Much less
        than expected, and worth stating plainly rather than quietly dropping.

        The reason is visible once seen: the TLS already reconstructs about 86 % of these
        trees, so its own upper extent is a close proxy for the top, and the measured
        volume is an integral over what was reconstructed. It never depended on the drone.

        **What the drone contributes is coverage, not the top of a stem.** The ground
        sensors cover 900 m² of a 1256 m² plot; the drone covers all of it, including the
        28 % with no ground-based data at all. That is a real and large contribution, but
        it is an argument about where the instrument was, not about what it could see from
        there.

        Whether fusion matters more on badly seen trees is a fair question this cannot
        answer: the stems in this comparison are the ones reconstructed well enough to
        pair, which selects for good coverage.

        ### What this does not settle

        Volume has no field reference here. Internal consistency and a form factor landing
        in a plausible band are not validation.
        """
    )
    return


if __name__ == "__main__":
    app.run()
