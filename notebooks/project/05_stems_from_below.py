"""Individual project, step 6: stems and diameter, which only the ground sensors can give.

The canopy height model route scored TLS and MLS at F1 0.566, well below the drone. That
was never a fair test of what they are for. A CHM discards everything a ground based
scanner is good at, and the plot is also larger than the area those clouds cover.

This notebook detects stems in a breast height cross-section instead, fits each one with
a robust circle, and compares the diameters against the field.

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


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Measuring stems

    ## Two things had to be fixed before the comparison meant anything

    **The scored area.** TLS and MLS are delivered as a 30 by 30 m box on the plot
    centre, which is 900 m². The plot is a 20 m circle, which is 1256 m². **28 % of the
    plot was never scanned by either instrument**, and 24 of the 74 field stems fall
    outside the delivered box. Scoring them over the whole circle counts data that was
    not supplied as a miss. Everything below scores over the box.

    **The circle fit.** `pipeline.detect_seeds` fits a Taubin circle over every point in
    a cluster, which has no defence against a cluster that also holds a low branch, a
    neighbouring stem or understorey. `stems.detect_stems` fits by RANSAC and then gates
    on roundness, arc coverage and vertical continuity. Arc coverage matters most: a
    scanner sees one side of a stem, and a circle through a short arc is nearly
    unconstrained.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Results as measured

    ### The fit, on the same clusters

    | cloud | method | stems | recall | precision | F1 | DBH bias | DBH RMSE | r |
    |---|---|---:|---:|---:|---:|---:|---:|---:|
    | TLS | Taubin, loose gates | 37 | 0.473 | 0.946 | 0.631 | +7.26 cm | 10.91 cm | +0.117 |
    | TLS | **RANSAC + gates** | 35 | 0.473 | 1.000 | 0.642 | +3.58 cm | **3.88 cm** | **+0.972** |
    | MLS | Taubin, loose gates | 37 | 0.473 | 0.946 | 0.631 | +11.44 cm | 18.11 cm | -0.070 |
    | MLS | **RANSAC + gates** | 33 | 0.446 | 1.000 | 0.617 | +4.76 cm | **4.98 cm** | **+0.970** |

    Scored over the whole plot circle, and against the 2011 survey, which is why these
    F1 values are still low. The point of the table is the diameter: the Taubin fit
    produces numbers with **no relationship to the field measurement at all**, r = +0.117
    and -0.070, while the same clusters fitted robustly give r = +0.97. That is not a
    precision improvement, it is the difference between measuring the stem and measuring
    the cluster.

    ### Scored over the area actually scanned

    | cloud | reference | stems in box | recall | precision | F1 |
    |---|---|---:|---:|---:|---:|
    | TLS | 2011 survey | 50 | 0.680 | 0.971 | **0.800** |
    | MLS | 2011 survey | 50 | 0.660 | 1.000 | **0.795** |

    **Against the 0.566 of the canopy height model route, on exactly the same clouds.**
    The method has to change with the sensor, which is the Day 3 result appearing again
    from the other direction: on the TLS plot that day, cross-section seeding beat
    watershed at recall 0.68 against 0.15, and here the same reversal holds.

    Recall near 0.68 in a stand this dense is occlusion. A stem behind another stem is
    not measured from the ground, and no amount of point density fixes it.

    ### The diameter bias was the forest growing

    | cloud | reference | n | bias | RMSE | r |
    |---|---|---:|---:|---:|---:|
    | TLS | 2011 survey | 34 | +3.65 cm | 3.93 cm | +0.972 |
    | TLS | current list | 35 | **-1.26 cm** | **1.30 cm** | **+0.999** |
    | MLS | 2011 survey | 33 | +4.78 cm | 4.99 cm | +0.970 |
    | MLS | current list | 33 | **-0.14 cm** | **0.34 cm** | **+0.999** |

    The field survey is from 2011 and the scans from 2021 onwards. Median DBH on this
    plot was 25.8 cm in 2011 and is 31.3 cm in the current list, **+5.5 cm over fifteen
    years**. The measured bias against the 2011 survey is +3.7 and +4.8 cm, which is that
    growth and not an error in the fit.

    Against a contemporaneous list the bias essentially disappears. **But treat that
    second comparison as a check on the implementation, not as validation.** The current
    list carries heights to the millimetre for 441 trees, which no field crew produces,
    so it is almost certainly derived from this same laser scanning. Agreement at
    r = 0.999 says this pipeline reproduces another processing of the same data. It does
    not say the data are right.

    The honest pair of statements is therefore: diameters track the field survey at
    r = 0.97 with an offset explained by growth, and they reproduce an independent
    processing of the same clouds to within a centimetre.

    ### What this settles for RQ5

    | attribute | from above | from below |
    |---|---|---|
    | tree detection | F1 0.815 drone, 0.794 ALS | F1 0.800 TLS, 0.795 MLS |
    | canopy height | yes, p95 transfers between geometries | poorly, canopy under-sampled |
    | crown area | yes, r = +0.686 with DBH | no |
    | **stem diameter** | **not at all** | **RMSE 1.3 cm, r 0.999** |

    Detection is a draw. Everything else splits cleanly by viewpoint, and the split is
    not about quality. The drone cannot measure a diameter because it never sees a stem,
    and the TLS cannot give a canopy height because it barely sees the top. The boundary
    RQ5a asked about falls exactly where the line of sight does.

    ### What this does not settle

    Recall is bounded by occlusion and is not improved by a better fit. The gates were
    set from stem physics rather than tuned against the reference, but they were not
    cross-validated either. The current DBH list is of unknown provenance and is treated
    here as probably lidar derived; confirming that is worth a question to the course
    teachers.
    """)
    return


if __name__ == "__main__":
    app.run()
