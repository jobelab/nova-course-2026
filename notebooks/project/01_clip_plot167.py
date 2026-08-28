"""Individual project, step 2: clip every drone cloud to the field plot.

Step 1 found a nadir-to-oblique difference in the RGB chromatic coordinates that was
almost entirely blue, and could not say whether it was **view angle** or **land
cover** - the oblique footprint is 93.3 ha against the nadir's 26.2 ha, so the two
were not looking at the same ground. This notebook removes that difference by
clipping all four clouds to the same 20 m circle and re-running the arithmetic.

SPDX-License-Identifier: GPL-3.0-or-later
Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University

Run:  uv run marimo edit notebooks/project/01_clip_plot167.py --watch
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
    # One plot, four acquisitions

    ## Choosing the polygon

    The field GIS offers several candidates, and they are not interchangeable:

    | layer | geometry | what it is |
    |---|---|---|
    | `plot10m` / `plot10mR` | 50 points / 10 m buffers | every plot in the tract |
    | `PlotlistC` / `PlotlistC10m` | 5 points / 10 m buffers | the five TLS-MLS scan positions |
    | `plot20m` / `plot20mR` | 1 point / 20 m buffer | **TRAKT 167**, the field plot |

    `plot20mR` is the right one, for three reasons:

    1. Its attributes name it: `TRAKT = 167`, centre **(420407.631, 6481815.136)**,
       ground **Z = 137.642 m**. It is the plot the whole project is about.
    2. The field reference is defined on it. The tree list is
       `treedataRemningstorp2011_final_only_within20m_trslg.txt`, *within 20 m*. Clip
       to anything else and the drone measurements stop being comparable with the
       measured stems.
    3. It is the only layer here carrying a `.prj`, so its CRS is documented rather
       than assumed: **SWEREF99 TM**, the same frame the drone clouds are in.

    Checked rather than trusted: 121 vertices, radius 20.000 m to the millimetre,
    area 1256.1 m² against $\pi r^2 = 1256.6$. Converted once with `ogr2ogr` and
    committed as GeoJSON, so the boundary lives in the repository as readable text and
    needs no GDAL at read time.

    The five TLS-MLS positions sit inside it (`PlotlistC` ID 16 is 0.09 m from this
    centre), so a later comparison against the ground sensors uses the same circle.
    """)
    return


@app.cell
def _():
    from pathlib import Path

    import numpy as np

    from novatrees import spectral as sp
    from novatrees.clip import clip_cloud, point_in_rings, read_geojson_rings

    ROOT = Path(__file__).resolve().parents[2]
    PLOT = ROOT / "data" / "field" / "plot167_20m.geojson"
    DRONE = ROOT / "data" / "drone"

    rings = read_geojson_rings(PLOT)
    ring = rings[0]
    centre = np.array([420407.631019, 6481815.135773])
    radius = np.hypot(*(ring - centre).T)
    return (
        DRONE, PLOT, Path, ROOT, centre, clip_cloud, np,
        point_in_rings, radius, ring, rings, sp,
    )


@app.cell(hide_code=True)
def _(mo, radius, ring):
    mo.md(
        f"""
        ### The polygon as read

        {len(ring)} vertices, radius **{radius.min():.3f} – {radius.max():.3f} m**,
        so it is a circle to the millimetre and the clip is unambiguous at the edge.
        """
    )
    return


@app.cell
def _(DRONE, clip_cloud, rings):
    CLOUDS = ("Nadir_RGB", "Nadir_MS", "Oblique_RGB", "Oblique_MS")
    AREA = 1256.1  # m2, the polygon's own area

    def clipped_path(name):
        return DRONE / "clip" / f"{name}_plot167_20m.las"

    def ensure_clipped(name):
        """Clip on demand; skip the work when the output is already there."""
        src, dst = DRONE / f"{name}_PointCloud.las", clipped_path(name)
        if not dst.exists() and src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            clip_cloud(src, dst, rings)
        return dst

    clipped = {n: ensure_clipped(n) for n in CLOUDS}
    have = {n: p for n, p in clipped.items() if p.exists()}
    return AREA, CLOUDS, clipped, clipped_path, ensure_clipped, have


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Results as measured

    ### What the clip kept

    | cloud | footprint | in plot | density in plot | footprint mean |
    |---|---:|---:|---:|---:|
    | `Nadir_RGB` | 46,347,917 | 745,114 | 593 /m² | 177 /m² |
    | `Nadir_MS` | 15,641,772 | 295,497 | 235 /m² | 71 /m² |
    | `Oblique_RGB` | 170,060,798 | 1,079,832 | 860 /m² | 182 /m² |
    | `Oblique_MS` | 49,615,363 | 372,359 | 296 /m² | 77 /m² |

    Two things fall out immediately.

    **Density in the plot is three times the footprint average.** The footprint figure
    divides by a bounding box that is mostly empty corner; the plot sits in the
    high-overlap core, and a forest canopy generates far more reconstructed surface
    than flat ground does. Quote the plot density, not the footprint one.

    **Oblique yields more points than nadir over the same ground**: 45 % more in RGB,
    26 % more in MS. That is not the same as reconstructing more canopy: an oblique
    survey images each ground location from more directions, which raises point density
    on surfaces that were already reconstructed. Whether it resolves genuinely more
    canopy needs a voxel-occupancy comparison, not a point count.

    **The blunders were outside the plot.** The full oblique clouds reach 216.83 m and
    drop to 77.68 m, tens of metres off any real surface. Inside the plot every cloud
    now spans 133.1 – 164.4 m, against a surveyed plot-centre ground of 137.64 m. The
    TLS cloud, delivered already normalised, reaches **27.85 m above ground**, so a canopy top near 164 m is the right order, but a maximum is an outlier statistic in
    a photogrammetric cloud and an upper percentile after normalisation is the number
    to report. The clip removed the *far-field* blunders; it is not a filter, and
    points wrong by a few metres inside the plot would survive it.

    ### The confound, resolved

    Chromatic coordinates before and after the clip, nadir → oblique:

    | | full footprint | | clipped to plot 167 | |
    |---|---:|---:|---:|---:|
    | | nadir | oblique | nadir | oblique |
    | RCC | 0.3664 | 0.3390 | 0.3721 | 0.3426 |
    | GCC | 0.4278 | 0.4112 | 0.4182 | 0.4042 |
    | **BCC** | **0.2058** | **0.2499** | **0.2097** | **0.2532** |
    | ΔBCC | **+0.0441** | | **+0.0435** | |

    **The blue shift survives the clip essentially untouched: +0.0441 becomes
    +0.0435.** That eliminates **land cover**, since both numbers now come from the same
    1,256 m² of forest, and it is the only explanation this comparison can eliminate.

    Three candidates remain, and they are *not* separable with the data in hand:

    - **view geometry**, the effect of interest: obliquely-viewed and shadowed
      surfaces are lit by diffuse skylight rather than direct sun, and a longer
      atmospheric path scatters blue preferentially;
    - **illumination**: the two products were written three days apart, and the
      flight dates, times and sky conditions are not recorded in the data;
    - **radiometric processing**: camera white balance and Metashape's per-chunk
      colour adjustment are applied independently to each acquisition.

    So the honest statement is that **the two acquisitions differ**, and that the
    difference is not a land-cover artefact. Calling it a view-angle effect needs the
    flight metadata, or an invariant target visible in both scenes.

    ### And the multispectral clouds still barely move

    | | full footprint | | clipped | |
    |---|---:|---:|---:|---:|
    | | nadir | oblique | nadir | oblique |
    | G/(G+R+RE) | 0.3449 | 0.3458 | 0.3386 | 0.3427 |
    | R/(G+R+RE) | 0.2310 | 0.2335 | 0.2391 | 0.2428 |
    | RE/(G+R+RE) | 0.4241 | 0.4207 | 0.4223 | 0.4145 |

    Every clipped change is under 0.008, five to six times smaller than the RGB blue
    shift, and the two visible channels move the *same* way rather than trading
    against each other. The multispectral band set has **no blue band**, so it is
    structurally blind to the effect that dominates the RGB comparison.

    **This is a result, not a curiosity.** If greenness is to be compared across
    flights, the band set decides how much the flight plan matters: a G/R/RE/NIR index
    is far more robust to view angle than an RGB one. It also means GCC from an RGB drone cloud is **not** directly comparable with GCC
    from a differently-flown survey. Nor is it numerically comparable with tower
    phenocam GCC: a phenocam holds camera, settings and viewpoint fixed, whereas drone
    RGB passes through per-flight white balance and per-chunk colour adjustment. The
    two are the same *quantity*, not the same *number*, without cross-calibration.

    ### What this still does not do

    Every number is over all points in the cylinder: canopy, understorey and ground
    together, with no height normalisation and no crown segmentation. GCC per *crown*
    is the number worth reporting. The next step is ground filtering and normalisation
    inside the plot, then segmentation, then the same indices per tree, at which point they can be set against the field tree list this polygon was drawn for.
    """)
    return


if __name__ == "__main__":
    app.run()
