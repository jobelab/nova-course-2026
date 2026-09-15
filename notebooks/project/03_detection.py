"""Individual project, step 4: canopy height models, tree detection, and scoring.

Detects treetops by marker-controlled watershed on a canopy height model, for every
acquisition over plot 167, and scores them against the 74 field-surveyed stems.

The scoring needed fixing before any of it meant anything. `pipeline.match_reference`
asks each side for its nearest neighbour independently, which lets one treetop claim
two stems when the tolerance is not small next to the spacing. On this plot that turned
49 detections into a recall of 0.865 against 74 stems. `evaluate.match_positions`
solves the assignment instead, so a detection is spent at most once.

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


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Finding trees, and counting the misses honestly

    Seven acquisitions cover plot 167: four from the drone, and TLS, MLS and helicopter
    ALS. All are normalised against the terrain model from the previous notebook, which
    is the ALS terrain shifted onto MLS ground control.

    The reference is **74 stems surveyed in the field in 2011**, from
    `treedataRemningstorp2011_final_only_within20m_trslg.txt`, with stem centres, DBH
    and species. DBH runs 15.0 to 36.4 cm, 45 pine and 29 spruce, and the mean spacing
    works out at 4.12 m.

    That 2011 date is worth holding on to. The scans are from 2021 onwards, so the
    reference is fifteen years older than the data being scored against it. Stem counts
    suggest the stand was not thinned in between, and the trees have grown, but any
    stem that died since 2011 counts here as a miss that is not the sensor's fault.
    """)
    return


@app.cell
def _():
    from pathlib import Path

    import numpy as np
    import pandas as pd

    from novatrees.chm_watershed import ChmParams, chm_segment
    from novatrees.csf import CsfParams, csf_ground
    from novatrees.evaluate import match_positions
    from novatrees.io import read_sample
    from novatrees.terrain import Dtm, dtm_from_ground, normalize_against

    CX, CY = 420407.631019, 6481815.135773
    CSF_P = CsfParams(cloth_resolution=0.5, class_threshold=0.30, rigidness=2)
    TLS_CONST = 138.124          # recovered in notebook 02

    ROOT = Path(__file__).resolve().parents[2]
    FIELD = Path("/mnt/c/Users/jose.beltran/Proton Drive/jobel/My files/SLU/data/field")
    GIS = FIELD / "gis/phd_course_demo_aug26"
    DRONE = ROOT / "data" / "drone" / "clip"
    return (
        CSF_P, CX, CY, ChmParams, CsfParams, DRONE, Dtm, FIELD, GIS, Path,
        ROOT, TLS_CONST, chm_segment, csf_ground, dtm_from_ground,
        match_positions, normalize_against, np, pd, read_sample,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Detection tuning, and the trap in the tolerance

    Two numbers control whether the score means anything.

    **`min_distance`**, the minimum separation between treetops, decides how many peaks
    the CHM is allowed to produce. It is swept rather than assumed, because the right
    value depends on crown size and therefore on the stand.

    **The match tolerance** decides when a detection counts as the same tree as a
    surveyed stem. It has to be small next to the mean spacing of 4.12 m, or one
    treetop can sit within tolerance of two stems. With a 3 m tolerance and independent
    nearest-neighbour matching, 49 detections scored a recall of 0.865, which is 64
    stems matched by 49 tops. The tolerance here is **2.0 m**, under half the spacing,
    and the matching is one-to-one.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Results as measured

    ### F1 against minimum treetop separation

    | cloud | 1.5 m | 2.0 m | 2.5 m | 3.0 m | 3.5 m |
    |---|---:|---:|---:|---:|---:|
    | `Nadir_RGB` | **0.815** | 0.733 | 0.649 | 0.535 | 0.409 |
    | `Oblique_RGB` | **0.780** | 0.707 | 0.611 | 0.454 | 0.387 |
    | `Nadir_MS` | **0.772** | 0.744 | 0.678 | 0.529 | 0.404 |
    | `Oblique_MS` | **0.750** | 0.684 | 0.611 | 0.454 | 0.370 |
    | ALS | 0.791 | **0.794** | 0.667 | 0.535 | 0.409 |
    | MLS | **0.566** | 0.500 | 0.437 | 0.333 | 0.279 |
    | TLS | **0.566** | 0.480 | 0.387 | 0.356 | 0.337 |

    ### At each cloud's best separation

    | cloud | sep | tops | matched | recall | precision | F1 | offset |
    |---|---:|---:|---:|---:|---:|---:|---:|
    | `Nadir_RGB` | 1.5 | 56 | 53 | 0.716 | 0.946 | **0.815** | 0.55 m |
    | `Oblique_RGB` | 1.5 | 49 | 48 | 0.649 | 0.980 | 0.780 | 0.63 m |
    | `Nadir_MS` | 1.5 | 53 | 49 | 0.662 | 0.925 | 0.772 | 0.69 m |
    | `Oblique_MS` | 1.5 | 46 | 45 | 0.608 | 0.978 | 0.750 | 0.74 m |
    | ALS | 2.0 | 52 | 50 | 0.676 | 0.962 | 0.794 | 0.65 m |
    | MLS | 1.5 | 32 | 30 | 0.405 | 0.938 | 0.566 | 0.81 m |
    | TLS | 1.5 | 32 | 30 | 0.405 | 0.938 | 0.566 | 0.74 m |

    **Precision is high everywhere and recall is the limit.** Between 0.93 and 0.98 of
    what these methods detect is a real surveyed stem. What they do not do is find all
    of them.

    **Nadir beats oblique, for both cameras.** 0.815 against 0.780 in RGB, 0.772 against
    0.750 in multispectral. This is worth stating plainly because it runs against the
    point counts: the oblique surveys deliver 26 to 45 % more points over the same
    ground and detect fewer trees. More points are not more information. The blur
    visible in the oblique plan views is the same effect, and a smeared crown apex is a
    weaker peak for the watershed to find.

    **The drone is competitive with the helicopter.** Nadir RGB at 0.815 against ALS at
    0.794, with the drone at 593 points per m² and the ALS at about 890 in the plot.

    **CHM detection is the wrong method for the ground-based clouds.** TLS and MLS score
    0.566, and not because they see less: they see more, from below. A canopy height
    model throws away everything they are good at. This repeats the Day 3 result, where
    the ranking reversed between sensors, and the right route for them is stem detection
    in the point cloud rather than peak finding on a raster.

    ### Where the misses are

    Detection rate by DBH quartile, at 1.5 m separation:

    | cloud | 15-22 cm | 22-26 cm | 26-29 cm | 29-36 cm |
    |---|---:|---:|---:|---:|
    | `Nadir_RGB` | 37 % | 72 % | 83 % | **95 %** |
    | `Oblique_RGB` | 26 % | 61 % | 78 % | **95 %** |
    | `Nadir_MS` | 32 % | 67 % | 72 % | **95 %** |
    | ALS | 26 % | 72 % | 78 % | **100 %** |
    | MLS | 21 % | 22 % | 61 % | 58 % |

    This accounts for the recall almost entirely. **The largest quartile is found nearly
    every time and the smallest is missed about two thirds of the time.** Those small
    stems are suppressed, under the canopy, and invisible to anything looking down. A
    recall of 0.72 against every surveyed stem is not the same as missing a quarter of
    the forest: it is finding almost all of the trees that form the canopy and none of
    the ones beneath it.

    Which is the honest framing for an inventory. If the question is basal area or stem
    count, these methods under-count and the bias is size-dependent. If the question is
    dominant height or canopy cover, they are close to complete.

    ### A species difference that is really a size difference

    Detection splits by species too, 82 % of pine against 55 % of spruce for
    `Nadir_RGB`, and the same direction for every other cloud. **That is not a species
    effect, or at least this plot cannot show one.** The spruce here are simply smaller:

    | | n | mean DBH | median DBH |
    |---|---:|---:|---:|
    | pine | 45 | 27.7 cm | 28.5 cm |
    | spruce | 29 | 22.9 cm | 21.9 cm |

    Of the 37 stems in the larger half by DBH, **32 are pine and 5 are spruce**. With
    that distribution the species split and the size split are the same split, and no
    amount of care in the detection separates them. Reporting it as a species effect
    would be reading a real size effect through a label.

    ### What this does not settle

    The reference is from 2011 and the data from 2021 onwards, so misses include any
    stem that died in between. The `min_distance` sweep picks its best value against
    the same reference it is scored on, which flatters every number in the table by
    roughly the spread across the sweep. A held-out plot would fix that, and plot 167
    is the only plot with this much coverage.
    """)
    return


if __name__ == "__main__":
    app.run()
