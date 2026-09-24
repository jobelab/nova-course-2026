#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regenerate the report figures.

Figures 1 to 4 describe the data and are drawn from the clouds directly. Figures 5 to 8
are results and are drawn from the cached analyses, so they cannot drift away from the
numbers in the notebooks. Figure 6 in particular used to carry a hardcoded table, which
disagreed with a rerun by a few points on the smallest DBH quartile.

Output goes to docs/project/figures/.
"""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.optimize import linear_sum_assignment

import _common as C, analysis as A

F = C.ROOT / "docs" / "project" / "figures"
F.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.size": 7.5, "font.family": "DejaVu Sans", "axes.edgecolor": "#555",
                     "axes.labelcolor": "#222", "xtick.color": "#555", "ytick.color": "#555"})
INK = {"TLS": "#1f4e79", "MLS": "#2e8b57", "ALS": "#b8860b", "Nadir_RGB": "#c0392b",
       "Oblique_RGB": "#e8836f", "Nadir_MS": "#6a4c93", "Oblique_MS": "#a98bc9"}
ORDER = ["Nadir_RGB", "Oblique_RGB", "Nadir_MS", "ALS", "MLS"]

dtm, _ = C.terrain()
field = C.field_stems()
REF = field[["XCENT", "YCENT"]].to_numpy(float)
DBH = field.dbh.to_numpy()

# --- Figure 5: vertical distribution ------------------------------------------
prof = {}
for name, path, zoff in [("TLS", C.TLS, C.TLS_CONST), ("MLS", C.MLS, 0.0), ("ALS", C.ALS, 0.0)] + \
                        [(n, C.DRONE / f"{n}_plot167_20m.las", 0.0) for n in C.DRONE_CLOUDS]:
    prof[name] = C.normalised(path, dtm, zoff=zoff, target=600_000)[:, 2]

fig, ax = plt.subplots(1, 2, figsize=(6.8, 3.6), sharey=True)
bins = np.arange(-1, 31, 0.5)
for grp, a in ((("TLS", "MLS", "ALS"), ax[0]), (tuple(C.DRONE_CLOUDS), ax[1])):
    for n in grp:
        h, _ = np.histogram(prof[n], bins=bins)
        a.step(h / h.sum(), bins[:-1], where="post", color=INK[n], lw=1.3,
               label=n.replace("_", " "))
for a, t in zip(ax, ("Laser scanning", "Drone photogrammetry")):
    a.set_title(t, fontsize=8); a.set_xlabel("share of returns"); a.set_ylim(-1, 30)
    a.legend(frameon=False, fontsize=7); a.grid(axis="y", lw=0.3, alpha=0.4)
ax[0].set_ylabel("height above terrain (m)")
fig.tight_layout(pad=0.6); fig.savefig(F / "fig5_vertical_profiles.png", dpi=220,
                                       bbox_inches="tight", facecolor="w")
plt.close(fig); print("fig5")

# --- Figure 6: detection rate by DBH quartile, from the cache -------------------
# The ground scanners are scored only on the stems inside the 30 by 30 m box they
# cover. Scoring them over the whole plot counts 24 stems they never saw as misses
# (finding 18). The drone and ALS cover the whole plot and are scored on all 74 stems.
TOPS = A.detections()
qs = np.quantile(DBH, [0, .25, .5, .75, 1.0])
cls = np.clip(np.searchsorted(qs[1:-1], DBH, side="right"), 0, 3)
in_box = C.in_box(REF[:, 0], REF[:, 1])
rates = {}
for name in ORDER:
    q = TOPS[(TOPS.cloud == name) & (np.isclose(TOPS.sep, 1.5))][["x", "y"]].to_numpy()
    scored = in_box if name in ("TLS", "MLS") else np.ones(len(REF), bool)
    cost = np.linalg.norm(q[:, None, :] - REF[scored][None, :, :], axis=2)
    i, j = linear_sum_assignment(cost)
    ok = cost[i, j] <= 2.0
    hit = np.zeros(scored.sum(), bool); hit[j[ok]] = True
    c = cls[scored]
    rates[name] = [100 * hit[c == k].mean() for k in range(4)]

LABEL = {n: n.replace("_", " ") for n in ORDER}
LABEL["MLS"] = "MLS (its 30 by 30 m box)"
fig, a = plt.subplots(figsize=(5.4, 3.0))
w = 0.16
for i, (n, v) in enumerate(rates.items()):
    a.bar(np.arange(4) + i * w - 2 * w, v, w, color=INK[n], label=LABEL[n])
a.set_xticks(np.arange(4))
a.set_xticklabels([f"{qs[i]:.0f}-{qs[i+1]:.0f}" for i in range(4)])
a.set_xlabel("field DBH quartile (cm)"); a.set_ylabel("stems detected (%)")
a.set_ylim(0, 105); a.legend(frameon=False, fontsize=7, ncol=2); a.grid(axis="y", lw=0.3, alpha=0.4)
fig.tight_layout(pad=0.5); fig.savefig(F / "fig6_detection_by_dbh.png", dpi=220,
                                       bbox_inches="tight", facecolor="w")
plt.close(fig); print("fig6  " + "  ".join(f"{n} {['%.0f'%x for x in v]}" for n, v in rates.items()))

# --- Figure 7: species -----------------------------------------------------------
CT = A.crowns(); CS = CT[CT.species > 0]
fig, ax = plt.subplots(1, 3, figsize=(6.8, 3.0))
for a, (cl, col, t) in zip(ax, [("Nadir_RGB", "GCC", "GCC, nadir RGB"),
                                ("Nadir_MS", "NDVI", "NDVI, nadir MS"), (None, None, None)]):
    if cl is None:
        q = CS[CS.cloud == "Nadir_RGB"]
        for s, lab, cc in ((1, "pine", "#b8860b"), (2, "spruce", "#2e8b57")):
            g = q[q.species == s]
            a.scatter(g.dbh, g.GCC, s=16, color=cc, label=lab, alpha=0.85, lw=0)
        a.set_xlabel("field DBH (cm)"); a.set_ylabel("GCC")
        a.set_title("GCC against size", fontsize=8); a.legend(frameon=False, fontsize=7)
        a.grid(lw=0.3, alpha=0.4); continue
    q = CS[CS.cloud == cl]
    data = [q[q.species == 1][col].dropna(), q[q.species == 2][col].dropna()]
    bp = a.boxplot(data, tick_labels=["pine", "spruce"], widths=0.55, patch_artist=True,
                   medianprops=dict(color="#222", lw=1.2))
    for patch, cc in zip(bp["boxes"], ["#b8860b", "#2e8b57"]):
        patch.set_facecolor(cc); patch.set_alpha(0.55)
    for d, xx in zip(data, [1, 2]):
        a.scatter(np.random.default_rng(0).normal(xx, 0.05, len(d)), d, s=9,
                  color="#333", alpha=0.6, lw=0)
    a.set_title(t, fontsize=8); a.set_ylabel(col); a.grid(axis="y", lw=0.3, alpha=0.4)
fig.tight_layout(pad=0.6); fig.savefig(F / "fig7_species.png", dpi=220,
                                       bbox_inches="tight", facecolor="w")
plt.close(fig); print("fig7")

# --- Figure 8: diameter and form factor ------------------------------------------
ST = A.stems(); ST = ST[(ST.cloud == "TLS") & (ST.fit == "ransac")]
P = ST[["x", "y", "dbh"]].to_numpy()
TP = A.taper().dropna(subset=["form", "covered"])
fig, ax = plt.subplots(1, 2, figsize=(6.8, 3.2))
cur = C.current_dbh()
for reflab, rx, ry, rd, cc in (("2011 field survey", field.XCENT.to_numpy(), field.YCENT.to_numpy(),
                                DBH, "#b8860b"),
                               ("contemporaneous list", cur.X.to_numpy(), cur.Y.to_numpy(),
                                cur.DBH.to_numpy(), "#1f4e79")):
    keep = C.in_box(rx, ry)
    R = np.column_stack([rx[keep], ry[keep]])
    cost = np.linalg.norm(P[:, None, :2] - R[None, :, :], axis=2)
    i, j = linear_sum_assignment(cost); ok = cost[i, j] <= 2.0
    ax[0].scatter(rd[keep][j[ok]], P[i[ok], 2], s=20, color=cc, alpha=0.85, lw=0, label=reflab)
lim = [10, 45]
ax[0].plot(lim, lim, color="#888", lw=0.9, ls="--")
ax[0].set_xlim(lim); ax[0].set_ylim(lim); ax[0].set_aspect("equal")
ax[0].set_xlabel("reference DBH (cm)"); ax[0].set_ylabel("TLS DBH (cm)")
ax[0].set_title("Stem diameter", fontsize=8)
ax[0].legend(frameon=False, fontsize=7, loc="upper left"); ax[0].grid(lw=0.3, alpha=0.4)
ax[1].scatter(TP.covered, TP.form, s=20, color="#6a4c93", alpha=0.85, lw=0)
ax[1].axhspan(0.45, 0.50, color="#2e8b57", alpha=0.12)
ax[1].text(TP.covered.min() + 0.01, 0.487, "boreal conifer band", fontsize=6.5, color="#2e8b57")
ax[1].set_xlabel("fraction of tree height reconstructed"); ax[1].set_ylabel("form factor")
ax[1].set_title("Form factor follows coverage", fontsize=8); ax[1].grid(lw=0.3, alpha=0.4)
fig.tight_layout(pad=0.6); fig.savefig(F / "fig8_dbh_and_form.png", dpi=220,
                                       bbox_inches="tight", facecolor="w")
plt.close(fig); print("fig8")
