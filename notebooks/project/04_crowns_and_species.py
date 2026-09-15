"""Individual project, step 5: crown level aggregation, and colour against species.

Interactive. Crowns come from `analysis.crowns()`, cached to out/project. Pick an index
and the separation is recomputed live.

A narrative-only copy is in `narrative/`.

SPDX-License-Identifier: GPL-3.0-or-later
Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University

Run:  uv run marimo edit notebooks/project/04_crowns_and_species.py --watch
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
    from scipy import stats
    from scipy.optimize import linear_sum_assignment

    import analysis as A

    CT = A.crowns()
    CLOUDS = ["Nadir_RGB", "Oblique_RGB", "Nadir_MS", "Oblique_MS"]

    def paired(a, b, tol=1.5):
        qa, qb = CT[CT.cloud == a], CT[CT.cloud == b]
        xa, xb = qa[["x", "y"]].to_numpy(), qb[["x", "y"]].to_numpy()
        cost = np.linalg.norm(xa[:, None, :] - xb[None, :, :], axis=2)
        i, j = linear_sum_assignment(cost)
        k = cost[i, j] <= tol
        return qa.iloc[i[k]].reset_index(drop=True), qb.iloc[j[k]].reset_index(drop=True)

    def auc(sub, col):
        p_, s_ = sub[sub.species == 1][col].dropna(), sub[sub.species == 2][col].dropna()
        if len(p_) < 3 or len(s_) < 3:
            return float("nan"), len(sub)
        u = stats.mannwhitneyu(s_, p_).statistic
        return u / (len(s_) * len(p_)), len(sub)

    return A, CLOUDS, CT, auc, linear_sum_assignment, np, paired, stats


@app.cell(hide_code=True)
def _(CT, mo):
    mo.md(
        f"""
        # From points to trees

        {len(CT)} crowns across four acquisitions, each carrying its area from the
        labelled raster, its height as the 95th percentile of its points, and the median
        of every colour index over its points. A median rather than a mean, because a
        crown edge picks up background and one bright pixel should not move the tree.
        """
    )
    return


@app.cell(hide_code=True)
def _(CLOUDS, CT, mo):
    size_rows = [
        f"| `{c}` | {len(CT[CT.cloud==c])} | {CT[CT.cloud==c].area.median():.1f} m² | "
        f"{CT[CT.cloud==c].h95.median():.2f} m |" for c in CLOUDS]
    mo.md("### Crowns delineated\n\n| cloud | crowns | median area | median h95 |\n"
          "|---|---:|---:|---:|\n" + "\n".join(size_rows)
          + "\n\n**Oblique crowns come out about a third larger and there are fewer of "
            "them.** That is the mechanism behind the lower oblique detection rate: "
            "off-nadir views smear the apex, neighbouring crowns merge, and the watershed "
            "returns fewer, fatter basins.")
    return


@app.cell(hide_code=True)
def _(mo, np, paired):
    pair_rows = []
    for pa, pb, plabel in (("Nadir_RGB", "Oblique_RGB", "RGB"),
                           ("Nadir_MS", "Oblique_MS", "multispectral")):
        px, py = paired(pa, pb)
        cells = []
        for pcol in ("G", "h95", "area"):
            d = px[pcol].to_numpy() - py[pcol].to_numpy()
            cells.append(f"{np.median(d):+.4f} [{np.percentile(d,25):+.4f}, "
                         f"{np.percentile(d,75):+.4f}]")
        pair_rows.append(f"| {plabel} | {len(px)} | " + " | ".join(cells) + " |")
    mo.md("### The same tree, seen twice\n\nNadir minus oblique, median with the "
          "interquartile range.\n\n| pair | crowns | G share | h95 (m) | crown area (m²) |\n"
          "|---|---:|---:|---:|---:|\n" + "\n".join(pair_rows)
          + "\n\nThe RGB difference survives the pairing, so it is a property of how each "
            "acquisition sees a given tree rather than of which trees each one sampled. "
            "The multispectral set, which has no blue band, moves less and the other way. "
            "**Height transfers between geometries; crown area does not.**")
    return


@app.cell
def _(CLOUDS, CT, mo):
    cloud_pick = mo.ui.dropdown(CLOUDS, value="Nadir_RGB", label="cloud")
    band_only = mo.ui.checkbox(value=True, label="restrict to the middle DBH quartiles")
    mo.hstack([cloud_pick, band_only], justify="start", gap=2)
    return band_only, cloud_pick


@app.cell(hide_code=True)
def _(CT, auc, band_only, cloud_pick, mo):
    sel = CT[(CT.cloud == cloud_pick.value) & (CT.species > 0)]
    if band_only.value:
        blo, bhi = sel.dbh.quantile(.25), sel.dbh.quantile(.75)
        sel = sel[(sel.dbh >= blo) & (sel.dbh <= bhi)]
    idx_cols = (["NDVI", "NDRE", "GNDVI", "G"] if cloud_pick.value.endswith("MS")
                else ["GCC", "RCC", "BCC"])
    auc_rows = []
    for icol in idx_cols:
        a, n = auc(sel, icol)
        strength = abs(a - 0.5) * 2
        auc_rows.append(f"| {icol} | {a:.3f} | {strength:.2f} | {n} |")
    mo.md(
        f"### Species separation, {cloud_pick.value}"
        + (" (size controlled)" if band_only.value else "")
        + "\n\nAUC is the probability a random spruce scores above a random pine. 0.5 is "
          "no information, and a value below 0.5 separates equally well with the sign "
          "reversed, which is why the strength column takes the distance from 0.5.\n\n"
          "| index | AUC | strength | n |\n|---|---:|---:|---:|\n" + "\n".join(auc_rows)
    )
    return


@app.cell(hide_code=True)
def _(CT, mo):
    corr = CT[(CT.cloud == "Nadir_RGB") & (CT.species > 0)]
    mo.md(
        f"""
        ### Crown metrics against field DBH

        | | Pearson r with DBH |
        |---|---:|
        | crown area | **{corr.area.corr(corr.dbh):+.3f}** |
        | crown h95 | {corr.h95.corr(corr.dbh):+.3f} |
        | GCC | {corr.GCC.corr(corr.dbh):+.3f} |

        Crown area predicts stem diameter better than height does, which is awkward
        because area is also the metric most disturbed by flight geometry.

        Greenness falls with size, and the spruce here are smaller. That is why the size
        control above matters: tick it off and the separation is partly a size effect;
        leave it on and what remains is the species. **Unlike the apparent species effect
        in detection, this one survives.**

        **An uncalibrated 20 MP RGB camera matches the four band multispectral payload**
        at separating these two species. Given the cost difference, that is the
        practically interesting result.

        ### What this does not settle

        Two species, one plot, about 50 crowns, spruce the minority class with 8 to 10
        within the DBH band, and no held out plot. An AUC near 1.0 on that sample says
        these two species are clearly different here, not that a classifier would
        generalise. GCC and BCC come from the same three channels and are near mirrors of
        each other, so they are not independent evidence.
        """
    )
    return


if __name__ == "__main__":
    app.run()
