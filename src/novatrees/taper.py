# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""Stem taper reconstruction: RANSAC circles per slice, then a smoothed curve.

Step up the stem, fit a circle to each horizontal slice, throw away the fits that
disagree with their neighbours, and smooth what survives into a taper curve
`d(z)`. From that fall DBH, merchantable heights and volume.

**Volume is the one that needs care.** The integral runs between the first and last
*accepted* slice, not the ground and the tip, and returns thin with height until
slices stop passing `min_points`. Measured here, the strict thresholds span 16 to 44
per cent of tree height, so the integral is a partial stem volume that nothing in its
formula announces. `volume_variants` reports it beside a relaxed-threshold version and
a Kozak fit integrated to the tip, each with its cover fraction and form factor. Read
the form factor first: a boreal conifer holds 0.45 to 0.50, so 0.25 means a short
integral rather than a thin tree.

Defaults follow the PCT demo's Phase 5. Each parameter trades detail against
robustness, and the docstring on `TaperParams` says which way.

Two choices worth knowing about:

**RANSAC rather than least squares.** A plain circle fit is dragged off the stem
by branch stubs and by far-side returns arriving through gaps in the bark. The
consensus step matters more here than the refinement does - the refinement is
just a Taubin fit on the inliers.

**Tolerances compare against the last *accepted* slice, not the previous one.**
Otherwise a single bad fit becomes the new reference and walks the whole chain
off the stem. Rejected slices are recorded, so you can see where and why.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .dataset import xyz as _xyz

__all__ = [
    "TaperParams",
    "TaperResult",
    "principal_axis",
    "align_to_axis",
    "ransac_circle",
    "slice_fits",
    "taper_curve",
    "fit_taper_model",
    "volume_variants",
    "VOLUME_COLUMNS",
]

SMOOTHERS = ("cubic spline", "moving median", "monotonic", "none")
MODELS = ("kozak", "polynomial", "spline", "none")


@dataclass
class TaperParams:
    slice_thickness: float = 0.10  # thinner = more detail, fewer points per fit
    vertical_step: float = 0.08  # smaller = more detail
    min_points: int = 100  # lower = accepts noisier slices
    smoothing: float = 0.50  # lower = relaxes smoothing
    ransac_iterations: int = 2000  # higher = more reproducible
    distance_threshold: float = 0.04  # lower = accepts noise as inliers
    radius_tolerance: float = 0.03  # higher = accepts noise between slices
    centre_tolerance: float = 0.06  # higher = accepts a wandering axis
    method: str = "cubic spline"  # see SMOOTHERS
    min_radius: float = 0.01
    max_radius: float = 1.50
    seed: int = 0  # fixed so reruns are reproducible

    # A leaning stem's centre moves with height by construction, so the
    # centre_tolerance test rejects nearly every slice on a tilted tree no matter
    # how it is tuned -- the horizontal slice is cutting an ellipse through a
    # cylinder that is not vertical. Rotating into the stem's own principal frame
    # first makes the slices perpendicular to the axis and the centre roughly
    # stationary again. It does NOT rescue a curved (sweeping) stem, where no
    # single axis fits.
    align_axis: bool = False
    model: str = "none"  # fit an analytic taper function: see MODELS
    poly_degree: int = 4

    # Per-slice quality. Occupancy is the fraction of the circumference with points
    # behind it; a circle fitted to a narrow arc is a guess. Axis ratio is how far
    # the slice is from round, and is a flag only: on this plot it is dominated by
    # stem ovality, not by lean, so it cannot measure tilt (see novatrees.stemgeom).
    min_occupancy: float = 0.0  # 0 disables; 0.5 is a reasonable filter
    min_axis_ratio: float = 0.0  # 0 disables; 0.6 rejects badly non-round slices

    def relaxed(self) -> "TaperParams":
        """The same settings, loosened so the reconstruction reaches further up.

        The defaults are PCT's, and PCT is a TLS tool: 100 points in a 0.10 m slice
        is easy at 300,000 points per square metre and impossible on MLS returns
        eight metres up. That threshold, not the tree, is what ends most
        reconstructions early, so this trades per-slice precision for reach:
        thicker slices gather more points, a lower floor accepts them, and wider
        tolerances let the chain continue past one thin band.

        Diameters from here are noisier. Use it to see how much stem the strict
        settings were missing, not as a replacement for them.
        """
        from dataclasses import replace

        return replace(
            self,
            slice_thickness=max(self.slice_thickness * 2, 0.20),
            vertical_step=max(self.vertical_step * 2.5, 0.20),
            min_points=max(int(self.min_points * 0.15), 15),
            distance_threshold=self.distance_threshold * 1.5,
            radius_tolerance=self.radius_tolerance * 3,
            centre_tolerance=self.centre_tolerance * 2.5,
        )


@dataclass
class TaperResult:
    fits: object  # DataFrame: every slice attempted, with ok/why
    curve: object  # DataFrame: accepted slices, smoothed
    dbh: float  # diameter at 1.3 m, from the smoothed curve
    volume: float  # alias of volume_measured, kept for older callers
    stats: dict = field(default_factory=dict)

    # Three answers to "what is the stem volume", which are not the same number.
    volume_measured: float = float("nan")  # integrated over the reconstructed range only
    volume_model: float = float("nan")  # analytic taper extrapolated to full height
    volume_cylinder: float = float("nan")  # pi r^2 H, the upper bound a stem never reaches
    covered_fraction: float = float("nan")  # how much of the tree the reconstruction spans

    @property
    def form_factor_measured(self) -> float:
        """Measured volume over the DBH-by-height cylinder.

        A boreal conifer stem normally lands near 0.45 to 0.50. A much lower value
        does not mean a thin tree, it means the reconstruction did not reach the top.
        """
        return self.volume_measured / self.volume_cylinder if self.volume_cylinder else float("nan")

    @property
    def form_factor_model(self) -> float:
        return self.volume_model / self.volume_cylinder if self.volume_cylinder else float("nan")


def ransac_circle(P: np.ndarray, iterations: int, distance_threshold: float, rng, params=None):
    """Fit a circle to 2D points by RANSAC. Returns (xc, yc, r, sigma, n_inliers) or None."""
    import circle_fit

    p = params or TaperParams()
    n = len(P)
    if n < 3:
        return None

    best_mask, best_count = None, -1
    tri_idx = rng.integers(0, n, size=(int(iterations), 3))
    for tri in tri_idx:
        a, b, c = P[tri]
        d = 2.0 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
        if abs(d) < 1e-12:  # collinear sample
            continue
        ux = ((a @ a) * (b[1] - c[1]) + (b @ b) * (c[1] - a[1]) + (c @ c) * (a[1] - b[1])) / d
        uy = ((a @ a) * (c[0] - b[0]) + (b @ b) * (a[0] - c[0]) + (c @ c) * (b[0] - a[0])) / d
        r = float(np.hypot(a[0] - ux, a[1] - uy))
        if not (p.min_radius <= r <= p.max_radius):
            continue
        resid = np.abs(np.hypot(P[:, 0] - ux, P[:, 1] - uy) - r)
        mask = resid <= distance_threshold
        count = int(mask.sum())
        if count > best_count:
            best_count, best_mask = count, mask

    if best_mask is None or best_count < 3:
        return None
    try:
        xc, yc, r, sigma = circle_fit.taubinSVD(P[best_mask])
    except Exception:
        return None
    return float(xc), float(yc), float(r), float(sigma), int(best_count)


def slice_fits(points, p: TaperParams = TaperParams()):
    """Fit one circle per horizontal slice. Returns a DataFrame of every attempt."""
    import pandas as pd

    from .stemgeom import axis_ratio, sector_occupancy

    P = _xyz(points)
    if p.align_axis and len(P) >= 3:
        P, _c, _R, _tilt = align_to_axis(P)
    rng = np.random.default_rng(p.seed)
    rows = []
    if len(P) < p.min_points:
        return pd.DataFrame(
            columns=["z", "x", "y", "r", "d", "sigma", "n", "inliers",
                     "occupancy", "axis_ratio", "ok", "why"]
        )

    z0, z1 = P[:, 2].min(), P[:, 2].max()
    last_ok = None
    for zc in np.arange(z0 + p.slice_thickness / 2, z1, p.vertical_step):
        sl = P[np.abs(P[:, 2] - zc) <= p.slice_thickness / 2]
        if len(sl) < p.min_points:
            continue
        fit = ransac_circle(sl[:, :2], p.ransac_iterations, p.distance_threshold, rng, p)
        if fit is None:
            continue
        xc, yc, r, sigma, n_in = fit
        occ = sector_occupancy(sl[:, :2], xc, yc)
        ratio = axis_ratio(sl[:, :2])

        ok, why = True, ""
        if p.min_occupancy > 0 and occ < p.min_occupancy:
            ok, why = False, "arc too narrow"
        elif p.min_axis_ratio > 0 and np.isfinite(ratio) and ratio < p.min_axis_ratio:
            ok, why = False, "not round"
        elif last_ok is not None:
            if abs(r - last_ok[2]) > p.radius_tolerance:
                ok, why = False, "radius jump"
            elif np.hypot(xc - last_ok[0], yc - last_ok[1]) > p.centre_tolerance:
                ok, why = False, "centre jump"

        rows.append(
            dict(z=float(zc), x=xc, y=yc, r=r, d=2 * r, sigma=sigma,
                 n=len(sl), inliers=n_in, occupancy=occ, axis_ratio=ratio,
                 ok=ok, why=why)
        )
        if ok:
            last_ok = (xc, yc, r)

    return pd.DataFrame(rows)


def _smooth(z: np.ndarray, d: np.ndarray, p: TaperParams) -> np.ndarray:
    if p.method == "cubic spline":
        from scipy.interpolate import UnivariateSpline

        # `s` bounds the summed squared residual, so higher smoothing = larger s,
        # matching the demo's "decrease to relax smoothing". This is NOT MATLAB
        # csaps' p, which runs the other way (p=1 interpolates).
        s = float(p.smoothing) * len(z) * (0.02**2)
        return UnivariateSpline(z, d, s=s, k=3)(z)
    if p.method == "moving median":
        from scipy.ndimage import median_filter

        width = max(3, int(round(0.5 / max(p.vertical_step, 1e-6))) | 1)
        return median_filter(d, size=min(width, len(d) | 1), mode="nearest")
    if p.method == "monotonic":
        from sklearn.isotonic import IsotonicRegression

        # A stem cannot widen with height; isotonic imposes exactly that.
        return IsotonicRegression(increasing=False).fit(z, d).predict(z)
    return d


def taper_curve(
    points, p: TaperParams = TaperParams(), total_height: float | None = None
) -> TaperResult:
    """Full reconstruction: slice fits, consistency filter, smoothing, metrics.

    `points` should be the stem-classified points. `total_height` is the whole
    tree's height including crown - pass it when you have it, since the stem
    points alone only reach as far as the stem was reconstructed, and the taper
    model's relative-height terms need the true total.
    """
    import pandas as pd

    P0 = _xyz(points)
    tilt = principal_axis(P0)[2] if len(P0) >= 3 else float("nan")

    fits = slice_fits(points, p)
    good = fits[fits.ok] if len(fits) else fits

    if len(good) < 4:
        return TaperResult(
            fits=fits,
            curve=pd.DataFrame(columns=["z", "d", "d_raw"]),
            dbh=float("nan"),
            volume=float("nan"),
            stats={"n_slices": int(len(fits)), "n_accepted": int(len(good)),
                   "tilt_deg": tilt, "aligned": bool(p.align_axis)},
        )

    z = good.z.to_numpy()
    d_raw = good.d.to_numpy()
    d = _smooth(z, d_raw, p)
    curve = pd.DataFrame({"z": z, "d": d, "d_raw": d_raw})

    # Optional analytic taper function on top of the smoothed points. When one is
    # fitted it supersedes the smoother for DBH and volume, because it extrapolates
    # to 1.3 m even when no slice landed there.
    height_stem = float(P0[:, 2].max() - P0[:, 2].min()) if len(P0) else float(z.max())
    height = float(total_height) if total_height else height_stem
    model_info = {"model": p.model, "ok": False}
    predict = None
    if p.model in ("kozak", "polynomial", "spline"):
        predict, model_info = fit_taper_model(z, d_raw, max(height, 1.4), p)
        if predict is not None:
            curve["d_model"] = predict(z)

    # 1. MEASURED: integrate only where slices were actually accepted. This is the
    #    honest number, and it is a *partial* stem volume whenever the reconstruction
    #    stops below the crown, which on thinning returns is most of the time.
    if predict is not None:
        grid = np.linspace(z.min(), z.max(), max(len(z) * 4, 50))
        dm = np.clip(predict(grid), 0, None)
        dbh = float(predict(np.array([1.3]))[0]) if height > 1.4 else float("nan")
        volume_measured = float(np.trapezoid(np.pi * (dm / 2) ** 2, grid))
    else:
        dbh = float(np.interp(1.3, z, d)) if z.min() <= 1.3 <= z.max() else float("nan")
        volume_measured = float(np.trapezoid(np.pi * (d / 2) ** 2, z))

    # 2. MODEL: extrapolate the analytic taper over the whole tree. Kozak's form goes
    #    to zero diameter at the tip by construction, so the integral is well posed.
    #    It is still extrapolation: on a stem reconstructed to a third of its height,
    #    two thirds of this number was never measured. covered_fraction says how much.
    volume_model = float("nan")
    model_capped = float("nan")
    if predict is not None and height > 1.4 and np.isfinite(dbh) and dbh > 0:
        # Extrapolate upward from the lowest accepted slice, never downward past it.
        # Kozak's exponent carries a log term, so as relative height goes to zero the
        # predicted diameter can run away by orders of magnitude. Below the lowest
        # slice the honest assumption is a cylinder at the diameter last measured,
        # which understates butt swell slightly and cannot explode.
        z0 = float(z.min())
        full = np.linspace(z0, height * 0.999, 400)
        dfull = np.nan_to_num(predict(full), nan=0.0, posinf=0.0, neginf=0.0)
        cap = 2.5 * dbh  # no stem is two and a half times its own DBH
        model_capped = float(np.mean(dfull > cap))
        dfull = np.clip(dfull, 0.0, cap)
        # A stem cannot widen with height. Imposing it kills the residual runaway
        # and costs nothing on a fit that was already behaving.
        dfull = np.minimum.accumulate(dfull)
        if model_capped <= 0.10:
            volume_model = float(np.trapezoid(np.pi * (dfull / 2) ** 2, full))
            volume_model += float(np.pi * (dfull[0] / 2) ** 2 * z0)  # stump section

    # 3. CYLINDER: pi r^2 H at DBH. Not an estimate of the stem, but the yardstick
    #    the forestry form factor is defined against, so it makes the other two
    #    readable at a glance.
    volume_cylinder = (
        float(np.pi * (dbh / 2) ** 2 * height) if np.isfinite(dbh) and height > 0 else float("nan")
    )
    covered = float((z.max() - z.min()) / height) if height > 0 else float("nan")
    volume = volume_measured

    return TaperResult(
        fits=fits,
        curve=curve,
        dbh=dbh,
        volume=volume,
        volume_measured=volume_measured,
        volume_model=volume_model,
        volume_cylinder=volume_cylinder,
        covered_fraction=covered,
        stats={
            "n_slices": int(len(fits)),
            "n_accepted": int(len(good)),
            "n_rejected": int((~fits.ok).sum()) if len(fits) else 0,
            "z_min": float(z.min()),
            "z_max": float(z.max()),
            "method": p.method,
            "volume_measured": volume_measured,
            "volume_model": volume_model,
            "volume_cylinder": volume_cylinder,
            "covered_fraction": covered,
            "model_capped_fraction": model_capped,
            "dbh_extrapolated": bool(not (z.min() <= 1.3 <= z.max())),
            "height_total": height,
            "height_stem": float(z.max() - z.min()),
            "stem_top": float(z.max()),
            "volume_stem": volume,
            "tilt_deg": tilt,
            "aligned": bool(p.align_axis),
            **{f"model_{k}": v for k, v in model_info.items()},
        },
    )


# --------------------------------------------------------------------------- #
# Tilted stems: work in the stem's own frame
# --------------------------------------------------------------------------- #


def principal_axis(points) -> tuple[np.ndarray, np.ndarray, float]:
    """Dominant direction of a point set. Returns (centroid, unit direction, tilt°).

    Tilt is measured from vertical. Above roughly 5° the horizontal-slice
    assumption starts costing accepted slices.
    """
    P = _xyz(points)
    c = P.mean(axis=0)
    _, _, vt = np.linalg.svd(P - c, full_matrices=False)
    d = vt[0]
    if d[2] < 0:
        d = -d
    tilt = float(np.degrees(np.arccos(np.clip(abs(d[2]), -1.0, 1.0))))
    return c, d, tilt


def align_to_axis(points):
    """Rotate so the stem's principal axis is vertical.

    Returns (aligned points, centroid, rotation matrix, tilt°). Heights in the
    aligned frame are distances *along the stem*, so a taper built from them is a
    true perpendicular taper rather than an oblique cut.
    """
    P = _xyz(points)
    c, d, tilt = principal_axis(P)
    z = np.array([0.0, 0.0, 1.0])
    v = np.cross(d, z)
    s, co = np.linalg.norm(v), float(np.dot(d, z))
    if s < 1e-9:
        R = np.eye(3)
    else:
        vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        R = np.eye(3) + vx + vx @ vx * ((1 - co) / s**2)
    return (P - c) @ R.T + c, c, R, tilt


# --------------------------------------------------------------------------- #
# Analytic taper functions
# --------------------------------------------------------------------------- #


def _kozak(h, H, D, b1, b2, b3, b4):
    """Kozak-style variable-exponent taper, reduced for single-tree fitting.

    The published Kozak (2004) form carries nine coefficients and is fitted across
    a population, not one stem. This keeps its shape -- a power of X whose exponent
    varies with relative height -- with four free coefficients, which is what ~30-70
    slices from one tree can actually support.
    """
    z = np.clip(np.asarray(h, float) / H, 1e-6, 0.999999)
    p = 1.3 / H
    X = (1.0 - np.sqrt(z)) / (1.0 - np.sqrt(p))
    expo = b1 * z**2 + b2 * np.log(z + 0.001) + b3 * np.sqrt(z) + b4 * np.exp(z)
    return D * np.power(np.clip(X, 1e-9, None), expo)


def fit_taper_model(z: np.ndarray, d: np.ndarray, H: float, p: TaperParams):
    """Fit an analytic taper function. Returns (predict callable, params dict).

    `H` is total tree height, which anchors the relative-height terms; the fit uses
    only the slices that survived the consistency checks.
    """
    from scipy.optimize import curve_fit

    if p.model == "kozak" and len(z) >= 6:
        D0 = float(np.interp(1.3, z, d)) if z.min() <= 1.3 <= z.max() else float(d.max())

        def f(hh, D, b1, b2, b3, b4):
            return _kozak(hh, H, D, b1, b2, b3, b4)

        try:
            popt, _ = curve_fit(
                f, z, d, p0=[D0, 0.5, 0.1, 0.4, 0.1], maxfev=20000,
                bounds=([1e-3, -5, -5, -5, -5], [3.0, 5, 5, 5, 5]),
            )
        except Exception:
            return None, {"model": "kozak", "ok": False}
        pred = lambda hh: f(np.asarray(hh, float), *popt)  # noqa: E731
        rmse = float(np.sqrt(np.mean((pred(z) - d) ** 2)))
        return pred, {"model": "kozak", "ok": True, "rmse": rmse,
                      "D": float(popt[0]), "b": [float(v) for v in popt[1:]]}

    if p.model == "polynomial" and len(z) >= p.poly_degree + 2:
        zz = np.clip(z / H, 0, 1)
        co = np.polyfit(zz, d, p.poly_degree)
        pred = lambda hh: np.polyval(co, np.clip(np.asarray(hh, float) / H, 0, 1))  # noqa: E731
        rmse = float(np.sqrt(np.mean((pred(z) - d) ** 2)))
        return pred, {"model": "polynomial", "ok": True, "rmse": rmse,
                      "degree": p.poly_degree, "coeffs": [float(c) for c in co]}

    if p.model == "spline" and len(z) >= 4:
        from scipy.interpolate import UnivariateSpline

        s = float(p.smoothing) * len(z) * (0.02**2)
        sp = UnivariateSpline(z, d, s=s, k=3)
        rmse = float(np.sqrt(np.mean((sp(z) - d) ** 2)))
        return (lambda hh: sp(np.asarray(hh, float))), {
            "model": "spline", "ok": True, "rmse": rmse}

    return None, {"model": p.model, "ok": False}


# --------------------------------------------------------------------------- #
# The three ways to answer "what is the stem volume"
# --------------------------------------------------------------------------- #

# Column order for the per-tree volume table. Kept here so the notebook, the CLI
# and the Day 4 script all produce the same frame.
VOLUME_COLUMNS = [
    "tree_id", "n_points", "height_m", "dbh_strict_m", "dbh_relaxed_m",
    "vol_measured_strict_m3", "cover_strict", "z_top_strict_m",
    "vol_measured_relaxed_m3", "cover_relaxed", "z_top_relaxed_m",
    "vol_model_strict_m3", "vol_model_relaxed_m3",
    "vol_cylinder_m3", "ff_measured_strict", "ff_measured_relaxed",
    "ff_model_strict", "ff_model_relaxed",
]


def volume_variants(points, total_height: float, p: TaperParams | None = None,
                    tree_id: int | None = None) -> dict:
    """Reconstruct one stem three ways and return every number side by side.

    There is no single stem volume to report here, because the reconstruction never
    reaches the top of the tree and the three honest responses to that disagree:

    1. **measured, strict** - integrate only where slices were accepted, at PCT's
       TLS settings. Nothing extrapolated, and a *partial* volume: read it with
       `cover_strict`, the fraction of tree height it spans.
    2. **measured, relaxed** - the same integral after `TaperParams.relaxed()`
       loosens the thresholds that were ending the chain early. Reaches higher,
       fits are noisier, still partial.
    3. **model** - the fitted Kozak curve integrated from the ground to the tip.
       Complete by construction, and extrapolated over whatever the measurement
       did not cover, so it is a prediction rather than a measurement.

    The cylinder pi r^2 H and the four form factors are the yardstick that makes
    them comparable: a boreal conifer stem sits near 0.45 to 0.50, so a form factor
    near 0.25 is the signature of a reconstruction that stopped halfway, and one
    above 0.55 is a model that has extrapolated itself too fat.
    """
    base = p or TaperParams()
    if base.model == "none":
        from dataclasses import replace

        base = replace(base, model="kozak")

    P = _xyz(points)
    row = {c: float("nan") for c in VOLUME_COLUMNS}
    row["tree_id"] = tree_id
    row["n_points"] = int(len(P))
    row["height_m"] = float(total_height)

    for tag, params in (("strict", base), ("relaxed", base.relaxed())):
        try:
            r = taper_curve(P, params, total_height=total_height)
        except Exception:
            continue
        if not len(r.curve):
            continue
        row[f"dbh_{tag}_m"] = r.dbh
        row[f"vol_measured_{tag}_m3"] = r.volume_measured
        row[f"vol_model_{tag}_m3"] = r.volume_model
        row[f"cover_{tag}"] = r.covered_fraction
        row[f"z_top_{tag}_m"] = r.stats.get("stem_top", float("nan"))
        row[f"ff_measured_{tag}"] = r.form_factor_measured
        row[f"ff_model_{tag}"] = r.form_factor_model
        if tag == "strict":
            row["vol_cylinder_m3"] = r.volume_cylinder
    return row
