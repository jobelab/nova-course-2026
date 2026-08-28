"""Individual project, step 1: chromatic coordinates on the drone RGB cloud.

The spectral chapter starts on the RGB products rather than the multispectral ones,
for two reasons that have nothing to do with convenience:

    1. `Nadir_RGB` and `Oblique_RGB` are LAS point format 2 with unambiguous R, G, B,
       so none of the band-identity inference in the project summary applies here.
    2. Chromatic coordinates are ratios over the band sum, so they are invariant to
       exposure, gain and illumination scaling. They are valid on raw DN. Whether
       these products are calibrated reflectance is the one open question the missing
       Metashape report could not be worked around - and GCC does not care.

GCC is also the standard phenocam greenness index, so a crown-level GCC from a drone
measures the same quantity a tower phenocam does. It is not the same *number*: a
phenocam fixes camera, settings and viewpoint, while drone RGB passes through
per-flight white balance and Metashape's per-chunk colour adjustment. Comparing them
numerically needs cross-calibration.

SPDX-License-Identifier: GPL-3.0-or-later
Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University

Run:  uv run marimo edit notebooks/project/00_rgb_chromatic_coordinates.py --watch
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
    # Greenness without calibration

    Four drone products over plot 167, crossing flight geometry with camera:

    | | RGB | multispectral |
    |---|---|---|
    | **nadir** | 46.3 M pts, 177 /m2 | 15.6 M pts, 71 /m2 |
    | **oblique** | 170.1 M pts, 182 /m2 | 49.6 M pts, 77 /m2 |

    All from Agisoft Metashape, SWEREF99 TM + RH2000, single-return photogrammetric
    surface points - no intensity, no returns, no classification. Colour is carried
    **per point**, so it survives filtering, normalisation and segmentation untouched.

    This notebook takes the RGB clouds and computes, for every point,

    $$\mathrm{GCC} = \frac{G}{R+G+B} \qquad
      \mathrm{RCC} = \frac{R}{R+G+B} \qquad
      \mathrm{BCC} = \frac{B}{R+G+B}$$

    Because each is a ratio over the band sum, multiplying all three channels by any
    constant leaves them unchanged. That is the whole argument for starting here.
    """)
    return


@app.cell
def _():
    from pathlib import Path

    import numpy as np

    from novatrees import spectral as sp

    # One constant, resolved relative to the repo, so the next data reorganisation is a
    # one-line change rather than a hunt through every notebook.
    DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "drone"

    CLOUDS = {
        "nadir_rgb": DATA_ROOT / "Nadir_RGB_PointCloud.las",
        "oblique_rgb": DATA_ROOT / "Oblique_RGB_PointCloud.las",
        "nadir_ms": DATA_ROOT / "Nadir_MS_PointCloud.las",
        "oblique_ms": DATA_ROOT / "Oblique_MS_PointCloud.las",
    }
    available = {k: v for k, v in CLOUDS.items() if v.exists()}
    return CLOUDS, DATA_ROOT, Path, available, np, sp


@app.cell(hide_code=True)
def _(CLOUDS, DATA_ROOT, available, mo):
    mo.md(
        f"""
        ### Data

        `DATA_ROOT` = `{DATA_ROOT}`

        Found **{len(available)} of {len(CLOUDS)}** clouds:
        {", ".join(f"`{k}`" for k in available) or "_none - unpack the archive first_"}

        The delivered archive is `archives/data/Nadir_MS_orthomosaic.zip`; the four
        `.las` files live inside it. They are large (12.4 GB unpacked), so they are
        staged outside the synced drive and outside git.
        """
    )
    return


@app.cell
def _(np, sp):
    import laspy

    def chromatic_summary(path, order=sp.RGB, resolve=False, chunk=4_000_000, bins=200):
        """Stream a cloud and return per-channel chromatic-coordinate statistics.

        Streaming rather than `laspy.read`: the oblique RGB cloud is 170 M points, and
        holding it whole buys nothing when every statistic here is additive. A
        histogram over fixed [0, 1] bins gives the percentiles without a second pass.
        """
        edges = np.linspace(0.0, 1.0, bins + 1)
        hist = np.zeros((len(order), bins), dtype=np.int64)
        tot = np.zeros(len(order))
        tot2 = np.zeros(len(order))
        n = 0
        dropped = 0
        with laspy.open(str(path)) as f:
            for pts in f.chunk_iterator(chunk):
                colour = {
                    s: np.asarray(getattr(pts, s), float) for s in ("red", "green", "blue")
                }
                if resolve:
                    colour = sp.resolve_ms(colour)
                cc, _ = sp.chromatic_coordinates(sp.colour_array(colour, order))
                ok = np.isfinite(cc).all(axis=1)
                dropped += int((~ok).sum())
                n += cc.shape[0]
                v = cc[ok]
                for i in range(len(order)):
                    hist[i] += np.histogram(v[:, i], bins=edges)[0]
                tot += v.sum(axis=0)
                tot2 += (v**2).sum(axis=0)
        m = n - dropped
        mean = tot / m
        return {
            "n": n,
            "dropped": dropped,
            "mean": mean,
            "sd": np.sqrt(np.maximum(tot2 / m - mean**2, 0.0)),
            "hist": hist,
            "edges": edges,
            "order": order,
        }

    def percentiles(stat, i, qs=(0.05, 0.5, 0.95)):
        h = stat["hist"][i]
        c = h.cumsum() / h.sum()
        mid = 0.5 * (stat["edges"][:-1] + stat["edges"][1:])
        return [float(mid[np.searchsorted(c, q)]) for q in qs]

    return chromatic_summary, laspy, percentiles


@app.cell
def _(available, chromatic_summary, sp):
    rgb_stats = {
        k: chromatic_summary(p) for k, p in available.items() if k.endswith("_rgb")
    }
    ms_stats = {
        k: chromatic_summary(p, order=sp.MS_VISIBLE, resolve=True)
        for k, p in available.items()
        if k.endswith("_ms")
    }
    return ms_stats, rgb_stats


@app.cell(hide_code=True)
def _(mo, ms_stats, percentiles, rgb_stats):
    def table(stats, denom):
        rows = ["| cloud | channel | mean | sd | p05 | median | p95 |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
        for name, st in stats.items():
            for i, ch in enumerate(st["order"]):
                p = percentiles(st, i)
                rows.append(
                    f"| `{name}` | {ch}/({denom}) | {st['mean'][i]:.4f} | "
                    f"{st['sd'][i]:.4f} | {p[0]:.3f} | {p[1]:.3f} | {p[2]:.3f} |"
                )
        return "\n".join(rows)

    mo.md(
        "### Chromatic coordinates\n\n"
        + table(rgb_stats, "R+G+B")
        + "\n\n**On the multispectral band set** - the same arithmetic, a different "
        "denominator. These are *not* phenocam GCC: there is no blue band, so name "
        "them by their denominator and never compare the numbers directly with the "
        "table above.\n\n"
        + table(ms_stats, "G+R+RE")
    )
    return (table,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Results as measured

    All four clouds, so the notebook reads without executing anything.

    **RGB clouds**: chromatic coordinates over R+G+B

    | cloud | points | dropped | RCC | **GCC** | BCC |
    |---|---:|---:|---:|---:|---:|
    | `Nadir_RGB` | 46,347,917 | 0 | 0.3664 | **0.4278** | 0.2058 |
    | `Oblique_RGB` | 170,060,798 | 17 | 0.3390 | **0.4112** | 0.2499 |

    A summer GCC in the low 0.4s is what a closed conifer canopy should give, and green
    above red above blue is the vegetation signature. Nothing here is calibrated and
    nothing needed to be. The 17 dropped points are pure black, zero in all three
    channels, and come back as `nan` rather than a silent zero.

    **Multispectral clouds**: the same arithmetic over G+R+RE

    | cloud | points | G | R | RE |
    |---|---:|---:|---:|---:|
    | `Nadir_MS` | 15,641,772 | 0.3449 | 0.2310 | 0.4241 |
    | `Oblique_MS` | 49,615,363 | 0.3458 | 0.2335 | 0.4207 |

    Green above red, red edge above both, which is the shape a vegetation spectrum has to have.
    That is weak but real confirmation of the band reading in
    `novatrees.spectral.MS_SLOTS`, reached independently of the band statistics that
    produced the mapping.

    ### The one difference worth noticing

    **The multispectral clouds barely move between nadir and oblique** (G 0.3449 →
    0.3458, R 0.2310 → 0.2335, RE 0.4241 → 0.4207, all third-decimal changes). **The RGB
    clouds move, and it is almost all blue**: BCC 0.2058 → 0.2499, +0.044, while GCC
    falls 0.017.

    A blue-heavy shift off-nadir is what shadowed and obliquely-viewed surfaces look
    like: they are lit by diffuse skylight rather than direct sun, and the longer
    atmospheric path off-nadir scatters blue preferentially. The MS band set has **no
    blue band**, so it is structurally blind to the effect, and that is why it stays put.

    Two readings, and they are not yet separable:

    - **view angle**, the interesting one; or
    - **land cover**, the boring one: the oblique footprint is 93.3 ha against the
      nadir's 26.2 ha, so it contains roads, edges and open ground the nadir never saw.

    Nothing can be concluded until both are clipped to a common footprint. That is the
    next notebook, and it is the reason the flight-geometry comparison is worth running
    at all: the effect is there, it is measurable, and it is currently confounded.

    ### What this does not yet do

    Every number above is over **all** points, canopy and ground together, on an
    unfiltered cloud. Before any of it means something about trees it needs the rest
    of the chain: outlier removal (the oblique clouds carry blunders tens of metres
    off), ground filtering, height normalisation, a common-footprint clip against the
    field plot polygons, and crown segmentation. GCC per *crown* is the number worth
    reporting; GCC per *cloud* is only evidence that the arithmetic is sound.
    """)
    return


if __name__ == "__main__":
    app.run()
