"""Individual project, step 3: terrain, and the vertical datum problem underneath it.

A photogrammetric cloud reconstructs only surfaces the cameras could see, and under a
closed canopy the ground is not one of them. On plot 167 the drone clouds hold almost
nothing below 15 m, so their terrain has to come from the laser scanning.

Which laser scanning turns out to matter. This notebook builds a terrain model from
the helicopter ALS, checks it against MLS ground returns, and finds the two are not on
the same vertical datum. Everything downstream depends on catching that first.

SPDX-License-Identifier: GPL-3.0-or-later
Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University

Run:  uv run marimo edit notebooks/project/02_terrain_and_heights.py --watch
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
    # Terrain from lidar, and what it exposed

    ## Why the terrain cannot come from the drone

    Normalising a cloud means subtracting a ground surface from every height. The usual
    route classifies ground points inside the cloud itself and interpolates them, which
    is what `novatrees.csf.normalize_heights` does and what works for laser scanning.

    Photogrammetry cannot do this. It reconstructs the surface the cameras saw, and in
    closed forest that surface is the canopy. Measured in a 5 m circle at the plot
    centre, the drone clouds put their **first percentile 14 m above the ground**: there
    is no ground in them to find. Normalising against their own lowest points would
    subtract canopy and make every tree shorter by however much canopy was mistaken for
    terrain.

    So the terrain comes from the lidar, through `novatrees.terrain`, which builds a DTM
    from one cloud and applies it to another.
    """)
    return


@app.cell
def _():
    from pathlib import Path

    import numpy as np

    from novatrees.csf import CsfParams, csf_ground
    from novatrees.io import read_sample
    from novatrees.terrain import dtm_from_ground, normalize_against

    CX, CY = 420407.631019, 6481815.135773      # plot 167 centre, SWEREF99 TM
    SURVEY = 137.642                            # surveyed ground at the centre, RH2000
    CSF_P = CsfParams(cloth_resolution=0.5, class_threshold=0.30, rigidness=2)

    ROOT = Path(__file__).resolve().parents[2]
    FIELD = Path("/mnt/c/Users/jose.beltran/Proton Drive/jobel/My files/SLU/data/field")
    DRONE = ROOT / "data" / "drone" / "clip"
    return (
        CSF_P, CX, CY, CsfParams, DRONE, FIELD, Path, ROOT, SURVEY,
        csf_ground, dtm_from_ground, normalize_against, np, read_sample,
    )


@app.cell
def _(CSF_P, CX, CY, FIELD, csf_ground, dtm_from_ground, np, read_sample):
    # ALS, sampled out to 30 m so the DTM covers the whole 20 m plot including its edges.
    # read_sample thins inside the chunk loop; the naive "collect then thin" costs more
    # memory than this machine has.
    als = read_sample(FIELD / "als/helicopter_2021/ALS_helicopter.laz",
                      target=2_000_000, centre=(CX, CY), radius=30.0)
    A = np.column_stack([als["x"], als["y"], als["z"]])
    als_ground = csf_ground(A, CSF_P)
    dtm_raw = dtm_from_ground(A[als_ground], cell=0.5, quantile=0.25)
    return A, als, als_ground, dtm_raw


@app.cell
def _(CSF_P, CX, CY, FIELD, csf_ground, np, read_sample):
    # MLS ground returns are the control. A walked scanner sees the forest floor directly
    # and at close range, so where it reports ground is about as good as this plot offers
    # short of levelling it.
    mls = read_sample(FIELD / "mls/plot167/Plot_167_MLS.laz",
                      target=2_000_000, centre=(CX, CY), radius=20.0)
    M = np.column_stack([mls["x"], mls["y"], mls["z"]])
    Mg = M[csf_ground(M, CSF_P)]
    return M, Mg, mls


@app.cell
def _(Mg, dtm_raw, np):
    from novatrees.terrain import Dtm

    residual = Mg[:, 2] - dtm_raw.sample(Mg[:, 0], Mg[:, 1])
    offset = float(np.median(residual))
    # A new Dtm rather than `dtm_raw.grid += offset`: mutating an upstream value would
    # apply the offset again every time marimo re-ran this cell.
    dtm = Dtm(grid=dtm_raw.grid + offset, x0=dtm_raw.x0, y0=dtm_raw.y0, cell=dtm_raw.cell)
    residual_after = Mg[:, 2] - dtm.sample(Mg[:, 0], Mg[:, 1])
    return Dtm, dtm, offset, residual, residual_after


@app.cell(hide_code=True)
def _(mo, np, offset, residual, residual_after):
    def line(r):
        return (f"median {np.median(r):+.3f} m, RMSE {np.sqrt((r**2).mean()):.3f} m, "
                f"p05 {np.percentile(r,5):+.3f}, p95 {np.percentile(r,95):+.3f}")

    mo.md(
        f"""
        ## The ALS is not on the same vertical datum as the MLS

        MLS ground minus ALS terrain, before any correction:

        > {line(residual)}

        That is not noise. A scatter of bad ground returns would spread over metres; this
        sits **{np.median(residual):+.3f} m** away with the 5th and 95th percentiles only
        {np.percentile(residual,95)-np.percentile(residual,5):.2f} m apart. It is a
        constant vertical shift.

        Applying it as a single offset:

        > {line(residual_after)}

        **RMSE {np.sqrt((residual_after**2).mean()):.3f} m after one constant.** The ALS
        terrain had the right shape all along and the wrong datum, so the fix is a shift,
        not a warp.
        """
    )
    return (line,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Results as measured

    ### The offset, and why it matters

    | | median | RMSE | p05 | p95 |
    |---|---:|---:|---:|---:|
    | before correction | +2.089 m | 2.100 m | +1.987 | +2.242 |
    | after correction | +0.000 m | **0.079 m** | -0.103 | +0.153 |

    513,390 MLS ground control points. **Uncaught, this would have made every
    drone-derived tree height 2.089 m too tall**, with nothing in the drone data to
    reveal it, because the drone clouds contain no ground of their own to argue with.

    The corrected terrain puts the plot centre at 137.236 m against a surveyed 137.642 m,
    a difference of -0.406 m. The survey value is a single marked point and may refer to
    the marker rather than the litter surface, so it is not treated as controlling.

    ### The TLS normalisation constant is not the surveyed elevation

    `Plot_167_TLS_GroundZero.laz` arrives with heights already normalised, but the
    constant used is not recorded. Matching its ground returns to the corrected terrain
    recovers it:

    > TLS z **+ 138.124 m** puts its ground on the terrain.

    The obvious guess, the surveyed plot-centre elevation of 137.642 m, is wrong by
    0.482 m. Worth noting because that guess is exactly what an earlier draft of this
    project made.

    ### Height distributions above the corrected terrain

    | cloud | points | p50 | p95 | p99 | max | below 0.5 m |
    |---|---:|---:|---:|---:|---:|---:|
    | `Nadir_RGB` | 745,114 | 20.07 | 23.76 | 24.91 | 27.40 | 4.8 % |
    | `Oblique_RGB` | 1,017,198 | 19.87 | 23.68 | 24.93 | 27.68 | 6.1 % |
    | `Nadir_MS` | 295,497 | 20.15 | 23.61 | 24.81 | 27.72 | 1.1 % |
    | `Oblique_MS` | 372,359 | 20.24 | 23.83 | 25.03 | 27.76 | 2.4 % |
    | TLS | 1,500,363 | 1.29 | 20.08 | 22.75 | 29.48 | 47.3 % |
    | MLS | 1,999,773 | 5.94 | 20.85 | 23.41 | 29.39 | 28.3 % |
    | ALS | 1,134,909 | 17.50 | 23.77 | 25.42 | 28.56 | 25.8 % |

    Three things are visible in that table.

    **The sensors do not sample the same forest.** Median height is 20 m for every drone
    cloud, 17.5 m for the ALS, 5.9 m for the MLS and 1.3 m for the TLS. The same stand,
    the same plot, and a median that moves by nearly 19 m depending on where the
    instrument stood. Nearly half the TLS returns are within 0.5 m of the ground against
    1 to 6 % of the drone returns.

    **On the upper canopy the drone matches the helicopter.** p95 is 23.6 to 23.8 m for
    all four drone clouds and 23.77 m for the ALS; p99 is 24.8 to 25.0 against 25.4.
    That is the first quantitative sign that a drone can stand in for airborne lidar on
    canopy height, which is RQ5b.

    **Maxima disagree and should not be trusted.** TLS and MLS reach 29.4 m where the
    drone clouds stop near 27.7 m. A maximum is one point. Upper percentiles are the
    statistic to report, which is why the table carries them.

    ### What this does not settle

    The offset is measured against MLS ground control, so it inherits whatever the MLS
    is worth. Nothing here says which of the two clouds carries the error, only that
    2.089 m separates them. Resolving that needs the flight metadata and the
    georeferencing method, which are among the questions put to the course teachers.
    """)
    return


if __name__ == "__main__":
    app.run()
