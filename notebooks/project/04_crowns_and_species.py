"""Individual project, step 5: crown level aggregation, and what colour says about species.

Everything so far has been per point or per plot. This notebook aggregates to the crown,
which is the unit an inventory actually reports, and then asks two questions the earlier
stages could not answer.

First, does flight geometry change an index on the *same tree*? Comparing plot means
confounds the acquisition with which surfaces each one happened to sample. Pairing crowns
between acquisitions removes that.

Second, do crown level indices separate Scots pine from Norway spruce, and does the
multispectral camera do it better than plain RGB?

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


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # From points to trees

    Crowns come from the watershed segmentation of the previous notebook, keeping any
    crown with at least 30 points. Each one carries its area from the labelled raster,
    its height as the 95th percentile of its points, and the median of every colour index
    over its points. A median rather than a mean, because a crown edge picks up
    background and a single bright pixel should not move the tree.

    Crowns are then paired between acquisitions by position, one-to-one at 1.5 m, and
    joined to the 74 field stems at 2.0 m.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Results as measured

    ### Crowns delineated

    | cloud | crowns | median area | median h95 |
    |---|---:|---:|---:|
    | `Nadir_RGB` | 56 | 16.7 m² | 22.50 m |
    | `Oblique_RGB` | 49 | 22.0 m² | 22.44 m |
    | `Nadir_MS` | 53 | 19.6 m² | 22.30 m |
    | `Oblique_MS` | 46 | 24.2 m² | 22.86 m |

    **Oblique crowns come out about a third larger and there are fewer of them.** That is
    the mechanism behind the detection result in the previous notebook: off-nadir views
    smear the crown apex, neighbouring crowns merge rather than separate, and the
    watershed returns fewer, fatter basins. It is the blur visible in the plan views,
    now with a number on it.

    ### The same tree, seen twice

    Paired crowns, nadir minus oblique:

    | pair | crowns | G share | h95 | crown area |
    |---|---:|---:|---:|---:|
    | RGB | 48 | **+0.0106** [+0.0073, +0.0147] | +0.10 m [-0.05, +0.22] | -1.8 m² [-4.1, +0.2] |
    | multispectral | 42 | **-0.0051** [-0.0067, -0.0032] | -0.16 m [-0.31, -0.04] | -2.0 m² [-5.7, +1.1] |

    Median with the interquartile range in brackets.

    **The RGB difference survives the pairing.** At plot level the clipped nadir minus
    oblique difference in GCC was +0.0140; per crown it is +0.0106, with an
    interquartile range that never crosses zero. So roughly three quarters of the
    plot level difference is a property of how each acquisition sees a given tree, and
    only the remainder was composition. This is the tightest version of the RQ1 result
    the data can give.

    **The multispectral difference is small and points the other way**, -0.0051 against
    +0.0106, on the same trees over the same three days. A band set without blue is not
    merely less sensitive to flight geometry here; it does not track the RGB effect at
    all.

    **Height barely moves**, 0.10 and 0.16 m on trees of 22 m. Canopy height transfers
    between flight geometries. Detection and crown area do not.

    ### Crown metrics against field DBH

    53 crowns joined to surveyed stems:

    | | Pearson r with DBH |
    |---|---:|
    | crown area | **+0.686** |
    | crown h95 | +0.497 |

    Crown area is the better predictor of stem diameter, which is worth knowing given
    that area is also the metric most disturbed by flight geometry.

    ### Species separation

    AUC is the probability that a randomly chosen spruce scores above a randomly chosen
    pine. 0.5 is no information, 1.0 is perfect separation, and values below 0.5 mean
    the index separates just as well with the sign reversed. It is scale free, so
    indices with different ranges compare directly. "Band" restricts to the middle two
    DBH quartiles, which is the size control.

    | cloud | index | AUC | n | AUC in band | n |
    |---|---|---:|---:|---:|---:|
    | `Nadir_RGB` | **GCC** | **0.978** | 53 | **0.954** | 27 |
    | `Nadir_RGB` | RCC | 0.684 | 53 | 0.638 | 27 |
    | `Nadir_RGB` | BCC | 0.042 | 53 | 0.092 | 27 |
    | `Oblique_RGB` | **GCC** | **0.996** | 48 | **0.981** | 24 |
    | `Oblique_RGB` | RCC | 0.430 | 48 | 0.537 | 24 |
    | `Oblique_RGB` | BCC | 0.062 | 48 | 0.009 | 24 |
    | `Nadir_MS` | NDVI | 0.932 | 49 | 0.897 | 25 |
    | `Nadir_MS` | NDRE | 0.862 | 49 | 0.801 | 25 |
    | `Nadir_MS` | GNDVI | 0.852 | 49 | 0.757 | 25 |
    | `Nadir_MS` | G/(G+R+RE) | 0.723 | 49 | 0.868 | 25 |
    | `Oblique_MS` | NDVI | 0.963 | 45 | 0.956 | 23 |
    | `Oblique_MS` | **NDRE** | **0.973** | 45 | **0.989** | 23 |
    | `Oblique_MS` | GNDVI | 0.929 | 45 | 0.939 | 23 |
    | `Oblique_MS` | G/(G+R+RE) | 0.610 | 45 | 0.844 | 23 |

    **Spruce crowns are greener than pine crowns, and the separation is close to
    complete.** Spruce sits higher in GCC, NDVI, NDRE and GNDVI, and lower in BCC, in
    every acquisition.

    **It is not a size effect.** Greenness does correlate with size, negatively: GCC
    against DBH is r = -0.345 and against h95 is r = -0.409, and the spruce on this plot
    are smaller. But restricting to the middle DBH quartiles, where pine and spruce
    medians are 28.2 and 26.0 cm, the separation holds at AUC 0.954 and the difference is
    if anything cleaner. That is the opposite of the detection result in the previous
    notebook, where the apparent species effect vanished under the same control.

    **The plain RGB camera does this at least as well as the multispectral one.** GCC
    reaches 0.954 and 0.981 in band, against 0.897 for nadir NDVI and 0.989 for oblique
    NDRE. A 20 MP RGB camera with an uncalibrated ratio index matches a four band
    multispectral payload at separating these two species. An earlier reading here was
    wrong and worth recording: comparing GCC against the multispectral `G/(G+R+RE)` made
    the multispectral camera look far worse, but that index ignores NIR, which is the
    band the camera exists for. Tested on NDVI and NDRE it is competitive.

    **BCC is the mirror of GCC**, AUC 0.042 and 0.062, which is 0.958 and 0.938 with the
    sign reversed. Pine crowns are bluer. That is the expected difference between the
    grey green needles of Scots pine and the darker, denser foliage of Norway spruce, and
    it is also a reminder that GCC and BCC are not independent evidence: they come from
    the same three channels and one is largely the complement of the other.

    ### What this does not settle

    Two species, one plot, about 50 crowns, and a two class problem is the easiest
    separation there is. The spruce are the minority class in every split and number
    only 8 to 10 within the DBH band. There is no held out plot, so nothing here is
    validated outside the data it was measured on, and an AUC near 1.0 on a sample this
    size should be read as "these two species are clearly different here", not as an
    expected accuracy for a classifier. The species labels are from the 2011 survey.
    Illumination and view angle effects are uncorrected, and although both species are
    mixed through the plot rather than segregated, that has not been tested.
    """)
    return


if __name__ == "__main__":
    app.run()
