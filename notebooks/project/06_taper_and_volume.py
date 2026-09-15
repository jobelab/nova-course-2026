"""Individual project, step 7: stem taper and volume, and a fusion that mattered less than expected.

Stem volume is the attribute that most needs more than one sensor, or so the argument
goes: diameter can only be measured from below and the top of the tree can only be seen
from above. This notebook reconstructs the taper of every TLS-detected stem, integrates
it, and then tests that argument by reconstructing the same stems twice, once with the
drone supplying the total height and once without.

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


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Taper, volume, and three answers to one question

    Each TLS stem is followed upward from breast height by `extract.track_stem_axis`,
    which searches near the previous centre rather than assuming a vertical line, so a
    leaning stem stays tracked and a branch does not steal it. `taper.taper_curve` then
    fits a RANSAC circle to every slice, filters for consistency, smooths, and
    integrates.

    Stem neighbourhoods are pulled from the TLS at full detail within 0.8 m of each
    detected stem, thinned to a 1 cm voxel, giving a median of about 334,000 points per
    stem.

    `taper` deliberately returns three volumes, because they answer different questions:
    the integrated volume over the range actually reconstructed, an analytic taper model
    extrapolated to the full height, and the cylinder that a stem never reaches. The
    ratio of the first to the third is the form factor.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Results as measured

    ### Taper reconstruction, 35 stems

    | | median | p25 | p75 |
    |---|---:|---:|---:|
    | covered fraction of tree height | 0.85 | 0.80 | 0.89 |
    | form factor | **0.454** | 0.431 | 0.481 |
    | stem volume | 0.765 m³ | | |

    Diameter at breast height from the full taper curve agrees with the independent
    cross-section fit at **r = +0.995**, which is a consistency check on two different
    routes through the same cloud rather than an accuracy claim.

    **The form factor lands where a boreal conifer should.** A median of 0.454 sits
    inside the 0.45 to 0.50 band that `taper.form_factor_measured` documents. That is
    the strongest single sign that the whole chain, terrain to stem to integration, is
    producing a physically sensible tree and not a plausible-looking number.

    ### But the form factor is partly a measurement artefact

    Form factor against covered fraction gives **r = +0.803**. A stem whose
    reconstruction stops lower has a smaller measured volume over the same cylinder, so
    its form factor falls. The spread from 0.431 to 0.481 across these stems is
    therefore not a spread in tree shape; a good part of it is a spread in how much of
    each tree the scanner could see.

    This is the same effect recorded in the Day 4 work, and it is a caution against
    reading a form factor as a property of the forest when it is partly a property of
    the occlusion.

    ### The fusion argument, tested

    The same 21 stems, reconstructed with and without the drone height:

    | | with drone height | without |
    |---|---:|---:|
    | form factor | 0.462 | 0.452 |
    | covered fraction | 0.861 | 0.828 |
    | measured volume | 0.847 m³ | 0.847 m³ |

    **The volume is identical, and the form factor moves by 0.010.** That is much less
    than expected, and it is worth stating plainly rather than quietly dropping.

    The reason is straightforward once seen: the TLS already reconstructs about 86 % of
    these trees, so its own upper extent is a close proxy for the top, and supplying a
    better total height only adjusts the denominator of the form factor. The measured
    volume never depended on the drone at all, because it is an integral over what was
    reconstructed.

    So the multi-sensor argument for volume, as usually stated, does not hold on this
    plot. **What the drone does contribute is coverage, not the top of a stem.** The TLS
    and MLS cover 900 m² of a 1256 m² plot, and the drone covers all of it, plus the
    28 % that has no ground-based data at all. That is a real and large contribution,
    but it is an argument about where the instrument was, not about what it could see
    from there.

    Whether the fusion matters more on trees the TLS sees badly is a fair question this
    cannot answer: the 21 stems in this comparison are the ones reconstructed well
    enough to pair, which selects for good coverage.

    ### Plot level

    25.4 m³ over 34 stems within the 900 m² the TLS covers works out at **282 m³ per
    hectare from detected stems alone**. Stem detection recall over that area is 0.68,
    so the true figure is higher, though by less than the missing third, since the
    undetected stems are the small ones.

    Reporting a stand volume from this would need the detection bias corrected rather
    than ignored, which is the size-dependent under-count established earlier. That is
    the honest limit of what this plot supports.

    ### What this does not settle

    Volume has no field reference here. The only check available is internal
    consistency and the form factor landing in a plausible band, neither of which is
    validation. The taper parameters were left at their documented defaults apart from
    the occupancy filter and axis alignment, and were not tuned per stem.
    """)
    return


if __name__ == "__main__":
    app.run()
