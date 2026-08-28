# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Per-point colour indices for photogrammetric clouds.

Two families, kept apart on purpose because they carry different risk.

**Chromatic coordinates** (`gcc`, `rcc`, `bcc`) divide one channel by the sum of
the three. Being ratios over the band sum they are invariant to exposure, gain and
any illumination scaling that hits all channels alike, so they are valid on raw DN
and need no radiometric calibration. For the drone RGB clouds - LAS point format 2,
unambiguous R/G/B - that means an index that no missing processing report can
invalidate. `gcc` is the standard phenocam greenness index, which makes a
crown-level GCC from a drone directly comparable with a tower phenocam.

**Normalised differences** (`normalised_difference`) are the NDVI/NDRE/GNDVI form.
They also survive uncalibrated DN as long as the two bands share a gain, but on the
multispectral clouds they depend on knowing which band is which - and the LAS
channel *names* are not that knowledge. See `MS_SLOTS`.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "MS_ORTHO_BANDS",
    "MS_SLOTS",
    "MS_VISIBLE",
    "RGB",
    "chromatic_coordinates",
    "colour_array",
    "normalised_difference",
    "read_colour",
    "resolve_ms",
]

#: What the LAS colour slots actually hold on the 4-band multispectral clouds.
#:
#: The payload is a 4-band **G / R / RedEdge / NIR** camera - no blue. Metashape maps
#: those into the R/G/B/NIR slots of LAS point format 8 **by name where a name fits**,
#: so red is red and green is green; only the ``blue`` slot is a stand-in, and it
#: carries **red edge**.
#:
#: Established from per-slot means over the whole cloud: the ``red`` slot is the
#: darkest (10,605) and the ``green`` slot is half again as bright (15,910), which is
#: chlorophyll absorption and only holds if the slot names are honest. Under any
#: swapped reading the red band would be brighter than green, which no vegetation is.
MS_SLOTS = {"red": "red", "green": "green", "blue": "red_edge", "nir": "nir"}

#: Band order **in the orthomosaic**, which is *not* the LAS slot order.
#:
#: The raster carries the camera's native band order, G first and R second; the LAS
#: puts red first. Bands 1 and 2 are therefore swapped between the two products
#: (raster band means 11,055 / 7,333 / 13,706 / 12,373 - band 2 darkest, so band 2 is
#: red - against cloud slot means 10,605 / 15,910 / 19,198 / 17,740). Sampling the
#: orthomosaic and joining it to the cloud without this mapping silently swaps red
#: and green.
MS_ORTHO_BANDS = ("green", "red", "red_edge", "nir")

#: Channel order for RGB chromatic coordinates - the columns are RCC, GCC, BCC.
RGB = ("red", "green", "blue")

#: Channel order for chromatic coordinates on the multispectral band set, i.e.
#: ``G / (G + R + RE)`` and its two siblings. These are **not** phenocam GCC: there
#: is no blue band, so the denominator differs and the numbers are not comparable
#: with an RGB-derived GCC. Report them by their denominator, not as "GCC".
MS_VISIBLE = ("green", "red", "red_edge")


def resolve_ms(colour: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Rename LAS colour slots to the bands they actually carry, via `MS_SLOTS`.

    Use this immediately after `read_colour` on a multispectral cloud, so that every
    line downstream names a real band and no index is silently built on the wrong one.
    """
    return {MS_SLOTS[k]: v for k, v in colour.items() if k in MS_SLOTS}


def read_colour(path, slots=("red", "green", "blue")) -> dict[str, np.ndarray]:
    """Read named colour channels from a LAS/LAZ file as float arrays.

    Channels come back as stored - 16-bit unsigned in LAS - without rescaling, since
    every index here is a ratio and a common scale factor cancels out.
    """
    import laspy

    f = laspy.read(str(path))
    return {s: np.asarray(getattr(f, s), dtype=np.float64) for s in slots}


def colour_array(colour: dict[str, np.ndarray], order) -> np.ndarray:
    """Stack a channel dict into an (n, k) array in the given channel order."""
    return np.column_stack([colour[name] for name in order])


def chromatic_coordinates(
    channels: np.ndarray, eps: float = 1e-9
) -> tuple[np.ndarray, np.ndarray]:
    """Chromatic coordinates of an (n, k) channel array, and the band sum.

    Returns ``(cc, total)`` where ``cc[:, i] = channels[:, i] / total`` and ``total``
    is the row sum. Rows summing to zero - unlit or masked points - give ``nan``
    rather than a silent zero, so they can be counted and excluded rather than
    quietly biasing a mean towards the origin.

    With ``channels`` as R, G, B the columns are RCC, GCC, BCC and they sum to 1.
    The function does not care how many channels there are, but note that
    chromatic coordinates over a non-RGB band set are **not** phenocam GCC: name the
    denominator explicitly when reporting them.
    """
    x = np.asarray(channels, dtype=np.float64)
    total = x.sum(axis=1)
    good = total > eps
    cc = np.full(x.shape, np.nan, dtype=np.float64)
    cc[good] = x[good] / total[good, None]
    return cc, total


def normalised_difference(a: np.ndarray, b: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    """``(a - b) / (a + b)``, with a zero denominator giving ``nan``.

    NDVI is ``normalised_difference(nir, red)``, NDRE is
    ``normalised_difference(nir, red_edge)``, GNDVI is
    ``normalised_difference(nir, green)``. On the multispectral clouds, resolve the
    band names through `MS_SLOTS` first.
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    denom = a + b
    out = np.full(a.shape, np.nan, dtype=np.float64)
    good = np.abs(denom) > eps
    out[good] = (a[good] - b[good]) / denom[good]
    return out
