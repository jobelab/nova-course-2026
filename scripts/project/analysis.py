# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later

"""The project analyses, as cached functions.

One source of truth for the computation. The scripts in this directory call these and
print; the notebooks in `notebooks/project/` call the same functions and render. Nothing
heavy is duplicated between them, and because every function caches to `out/project/`,
the first caller pays the cost and the rest open immediately.

Delete a file in `out/project/` to force that step to recompute, or pass `rebuild=True`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import _common as C


def detections(rebuild: bool = False) -> pd.DataFrame:
    """Treetops for every cloud at every separation. Columns: cloud, sep, x, y, h."""
    from novatrees.chm_watershed import ChmParams, chm_segment

    def build():
        dtm, _ = C.terrain()
        sources = [(n, C.DRONE / f"{n}_plot167_20m.las", 0.0) for n in C.DRONE_CLOUDS]
        sources += [("ALS", C.ALS, 0.0), ("MLS", C.MLS, 0.0), ("TLS", C.TLS, C.TLS_CONST)]
        rows = []
        for name, path, zoff in sources:
            H = C.normalised(path, dtm, zoff=zoff, target=2_000_000)
            for sep in (1.5, 2.0, 2.5, 3.0, 3.5):
                r = chm_segment(H, ChmParams(pixel_size=0.20, min_distance=sep,
                                             min_tree_height=5.0, min_crown_area=3.0))
                for x, y, h in r["tops"]:
                    rows.append(dict(cloud=name, sep=sep, x=x, y=y, h=h))
        return pd.DataFrame(rows)

    return C.cache("detections", build, rebuild=rebuild)


def crowns(rebuild: bool = False) -> pd.DataFrame:
    """Crown level metrics and colour indices for the four drone clouds.

    One row per crown, joined to the field survey where a stem is within 2 m.
    """
    import laspy
    from scipy.optimize import linear_sum_assignment

    from novatrees import spectral as sp
    from novatrees.chm_watershed import ChmParams, chm_segment
    from novatrees.terrain import normalize_against

    def build():
        dtm, _ = C.terrain()
        field = C.field_stems()
        REF = field[["XCENT", "YCENT"]].to_numpy(float)
        out = []
        for name in C.DRONE_CLOUDS:
            f = laspy.read(str(C.DRONE / f"{name}_plot167_20m.las"))
            xyz = np.column_stack([f.x, f.y, f.z])
            H = np.column_stack([xyz[:, 0], xyz[:, 1], normalize_against(xyz, dtm)])
            raw = {k: np.asarray(getattr(f, k), float) for k in ("red", "green", "blue")}
            if name.endswith("MS"):
                c = sp.resolve_ms(raw)
                c["nir"] = np.asarray(f.nir, float)
                idx = {"NDVI": sp.normalised_difference(c["nir"], c["red"]),
                       "NDRE": sp.normalised_difference(c["nir"], c["red_edge"]),
                       "GNDVI": sp.normalised_difference(c["nir"], c["green"]),
                       "G": sp.chromatic_coordinates(sp.colour_array(c, sp.MS_VISIBLE))[0][:, 0]}
            else:
                cc, _ = sp.chromatic_coordinates(sp.colour_array(raw, sp.RGB))
                idx = {"GCC": cc[:, 1], "RCC": cc[:, 0], "BCC": cc[:, 2], "G": cc[:, 1]}
            r = chm_segment(H, ChmParams(pixel_size=0.20, min_distance=1.5,
                                         min_tree_height=5.0, min_crown_area=3.0))
            lab, tops = r["labels"], r["tops"]
            area = np.bincount(r["labels2d"].ravel())[1:] * r["pixel_size"] ** 2
            rows = []
            for k in range(len(tops)):
                m = lab == k
                if m.sum() < 30:
                    continue
                row = dict(cloud=name, x=tops[k, 0], y=tops[k, 1], n=int(m.sum()),
                           h95=float(np.percentile(H[m, 2], 95)),
                           area=float(area[k]) if k < len(area) else np.nan)
                for nm, v in idx.items():
                    row[nm] = float(np.nanmedian(v[m]))
                rows.append(row)
            T = pd.DataFrame(rows)
            cost = np.linalg.norm(T[["x", "y"]].to_numpy()[:, None, :] - REF[None, :, :], axis=2)
            i, j = linear_sum_assignment(cost)
            ok = cost[i, j] <= 2.0
            T["dbh"] = np.nan
            T["species"] = 0
            T.loc[i[ok], "dbh"] = field.dbh.to_numpy()[j[ok]]
            T.loc[i[ok], "species"] = field.SPECIES.to_numpy()[j[ok]]
            out.append(T)
        return pd.concat(out, ignore_index=True)

    return C.cache("crowns", build, rebuild=rebuild)


def stems(rebuild: bool = False) -> pd.DataFrame:
    """Stems from the breast-height cross-section of TLS and MLS, both fits.

    Columns: cloud, fit, x, y, dbh (cm), plus the quality fields for the robust fit.
    """
    from novatrees.pipeline import SeedParams, detect_seeds
    from novatrees.stems import StemParams, detect_stems

    def build():
        dtm, _ = C.terrain()
        rows = []
        for name, path, zoff in (("TLS", C.TLS, C.TLS_CONST), ("MLS", C.MLS, 0.0)):
            B = C.height_band(path, dtm, zoff=zoff)
            st = detect_stems(B, StemParams())
            for r in st:
                rows.append(dict(cloud=name, fit="ransac", x=r["x"], y=r["y"],
                                 dbh=r["dbh"] * 100, sigma=r["sigma"], arc=r["arc"],
                                 inlier_frac=r["inlier_frac"], n=r["n"]))
            for x, y, d in detect_seeds(B, SeedParams()):
                rows.append(dict(cloud=name, fit="taubin", x=x, y=y, dbh=d * 100,
                                 sigma=np.nan, arc=np.nan, inlier_frac=np.nan, n=0))
        return pd.DataFrame(rows)

    return C.cache("stems", build, rebuild=rebuild)


def taper(rebuild: bool = False) -> pd.DataFrame:
    """Taper and volume per TLS stem, with and without a drone-supplied total height."""
    import warnings

    import laspy
    from scipy.optimize import linear_sum_assignment
    from scipy.spatial import cKDTree

    from novatrees.chm_watershed import ChmParams, chm_segment
    from novatrees.extract import StemTrackParams, track_stem_axis
    from novatrees.taper import TaperParams, taper_curve
    from novatrees.terrain import normalize_against

    def build():
        warnings.filterwarnings("ignore")
        dtm, _ = C.terrain()
        S = stems()
        S = S[(S.cloud == "TLS") & (S.fit == "ransac")].reset_index(drop=True)
        centres = S[["x", "y"]].to_numpy()

        f = laspy.read(str(C.DRONE / "Nadir_RGB_plot167_20m.las"))
        xyz = np.column_stack([f.x, f.y, f.z])
        H = np.column_stack([xyz[:, 0], xyz[:, 1], normalize_against(xyz, dtm)])
        seg = chm_segment(H, ChmParams(pixel_size=0.20, min_distance=1.5,
                                       min_tree_height=5.0, min_crown_area=3.0))
        lab, tops = seg["labels"], seg["tops"]
        ch = np.array([np.percentile(H[lab == k, 2], 95) if (lab == k).sum() > 30 else np.nan
                       for k in range(len(tops))])
        cost = np.linalg.norm(centres[:, None, :] - tops[None, :, :2], axis=2)
        i, j = linear_sum_assignment(cost)
        ok = cost[i, j] <= 3.0
        h_of = np.full(len(S), np.nan)
        h_of[i[ok]] = ch[j[ok]]

        tree = cKDTree(centres)
        buckets = [[] for _ in centres]
        with laspy.open(str(C.TLS)) as fh:
            for pts in fh.chunk_iterator(2_000_000):
                x, y = np.asarray(pts.x), np.asarray(pts.y)
                z = np.asarray(pts.z) + C.TLS_CONST
                dm, k = tree.query(np.column_stack([x, y]), distance_upper_bound=0.8)
                m = np.isfinite(dm)
                if not m.any():
                    continue
                h = z[m] - dtm.sample(x[m], y[m])
                good = (h >= 0.2) & (h <= 35)
                P = np.column_stack([x[m][good], y[m][good], h[good]])
                kk = k[m][good]
                for t in np.unique(kk):
                    buckets[t].append(P[kk == t])
                del x, y, z, dm, k, m, h, P, kk

        tp = TaperParams()
        tp.ransac_iterations, tp.min_occupancy, tp.align_axis = 600, 0.5, True
        rows = []
        for n, (chunks, h) in enumerate(zip(buckets, h_of)):
            if not chunks:
                continue
            P = C.voxel(np.vstack(chunks), 0.01)
            if len(P) < 2000:
                continue
            try:
                _, mask = track_stem_axis(
                    P, np.array([S.x[n], S.y[n], 1.30]), StemTrackParams())
                Q = P[mask]
                if len(Q) < 500:
                    continue
                a = taper_curve(Q, tp, total_height=(None if np.isnan(h) else float(h)))
                row = dict(x=S.x[n], y=S.y[n], dbh_slice=S.dbh[n], dbh_taper=a.dbh * 100,
                           height=h, volume=a.volume_measured, covered=a.covered_fraction,
                           form=a.form_factor_measured,
                           volume_no_h=np.nan, form_no_h=np.nan, covered_no_h=np.nan)
                if not np.isnan(h):
                    b = taper_curve(Q, tp, total_height=None)
                    row.update(volume_no_h=b.volume_measured, form_no_h=b.form_factor_measured,
                               covered_no_h=b.covered_fraction)
                rows.append(row)
            except Exception:
                continue
        return pd.DataFrame(rows)

    return C.cache("taper", build, rebuild=rebuild)


def heights(rebuild: bool = False) -> pd.DataFrame:
    """Height percentiles above the corrected terrain, one row per acquisition."""
    def build():
        dtm, _ = C.terrain()
        src = [(n, C.DRONE / f"{n}_plot167_20m.las", 0.0) for n in C.DRONE_CLOUDS]
        src += [("TLS", C.TLS, C.TLS_CONST), ("MLS", C.MLS, 0.0), ("ALS", C.ALS, 0.0)]
        rows = []
        for name, path, zoff in src:
            h = C.normalised(path, dtm, zoff=zoff, target=800_000)[:, 2]
            rows.append(dict(cloud=name, n=len(h), p50=np.percentile(h, 50),
                             p95=np.percentile(h, 95), p99=np.percentile(h, 99),
                             max=h.max(), below_half=100 * (h < 0.5).mean()))
        return pd.DataFrame(rows)

    return C.cache("heights", build, rebuild=rebuild)
