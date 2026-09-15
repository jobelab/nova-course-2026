#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Wide variants of the cross-section figures, for the 16:9 slides.

The report figures are drawn for a portrait A4 page, so the stacked cross-sections come
out taller than they are wide. Dropped into a 16:9 slide they hit the height limit
before they fill the width, leaving a third of the slide used and labels too small to
read from the back of a room.

These variants lay the same panels out for a landscape frame and set type large enough
to project. Output goes to docs/project/figures/slide/.
"""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import numpy as np, laspy, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import _common as C

F = C.ROOT / "docs" / "project" / "figures" / "slide"
F.mkdir(parents=True, exist_ok=True)
SLAB = 3.0          # half-width of the cross-section slab, m
plt.rcParams.update({"font.size": 10, "font.family": "DejaVu Sans",
                     "axes.labelcolor": "#222", "xtick.color": "#444", "ytick.color": "#444",
                     "xtick.labelsize": 9, "ytick.labelsize": 9})

dtm, _ = C.terrain()


def drone_slab(name):
    f = laspy.read(str(C.DRONE / f"{name}_plot167_20m.las"))
    x, y = np.asarray(f.x), np.asarray(f.y)
    h = np.asarray(f.z) - dtm.sample(x, y)
    m = np.abs(y - C.CY) <= SLAB
    col = np.column_stack([np.asarray(f.red)[m], np.asarray(f.green)[m],
                           np.asarray(f.blue)[m]]).astype(float)
    return x[m] - C.CX, h[m], col


def lidar_slab(path, zoff, target=400_000, chunk=2_000_000):
    rng = np.random.default_rng(0)
    xs, hs, iv = [], [], []
    with laspy.open(str(path)) as fh:
        p = min(1.0, target / max(fh.header.point_count * 0.2, 1))
        for pts in fh.chunk_iterator(chunk):
            x, y = np.asarray(pts.x), np.asarray(pts.y)
            z = np.asarray(pts.z) + zoff
            m = ((x - C.CX) ** 2 + (y - C.CY) ** 2 <= C.PLOT_R ** 2) & (np.abs(y - C.CY) <= SLAB)
            k = m & (rng.random(len(x)) < p)
            if k.any():
                xs.append(x[k] - C.CX)
                hs.append(z[k] - dtm.sample(x[k], y[k]))
                iv.append(np.asarray(pts.intensity)[k].astype(float))
            del x, y, z, m, k
    return np.concatenate(xs), np.concatenate(hs), np.concatenate(iv)


def stretch(c):
    out = np.empty_like(c)
    for i in range(c.shape[1]):
        lo, hi = np.percentile(c[:, i], (2, 98))
        out[:, i] = np.clip((c[:, i] - lo) / max(hi - lo, 1e-9), 0, 1)
    return out


# --- drone cross-sections, 2 by 2 so the panels are wide ------------------------
TITLES = {"Nadir_RGB": "Nadir, RGB", "Oblique_RGB": "Oblique, RGB",
          "Nadir_MS": "Nadir, multispectral", "Oblique_MS": "Oblique, multispectral"}
fig, ax = plt.subplots(2, 2, figsize=(12.0, 5.8), sharex=True, sharey=True)
for a, name in zip(ax.ravel(), TITLES):
    x, h, col = drone_slab(name)
    a.scatter(x, h, c=stretch(col), s=1.1, marker=".", linewidths=0, rasterized=True)
    a.set_facecolor("#111")
    a.text(0.012, 0.93, TITLES[name], transform=a.transAxes, color="w", fontsize=10, va="top")
    a.set_ylim(-6, 31); a.set_xlim(-21, 21)
    a.axhline(0, color="#e8b", lw=0.7, ls=":", alpha=0.85)
for a in ax[:, 0]:
    a.set_ylabel("height (m)")
for a in ax[1]:
    a.set_xlabel("metres east of plot centre")
fig.tight_layout(pad=0.5, h_pad=0.4, w_pad=0.6)
fig.savefig(F / "fig3_drone_cross_sections.png", dpi=200, bbox_inches="tight", facecolor="w")
plt.close(fig); print("slide fig3")

# --- laser scanning cross-sections, three wide panels ---------------------------
LID = (("TLS", C.TLS, C.TLS_CONST, "TLS, Riegl VZ-400i, from the ground"),
       ("MLS", C.MLS, 0.0, "MLS, Faro Orbis, walked"),
       ("ALS", C.ALS, 0.0, "ALS, helicopter"))
fig, ax = plt.subplots(3, 1, figsize=(12.0, 6.0), sharex=True, sharey=True)
for a, (nm, path, zoff, label) in zip(ax, LID):
    x, h, i = lidar_slab(path, zoff)
    lo, hi = np.percentile(i, (2, 98))
    g = 0.25 + 0.75 * np.clip((i - lo) / max(hi - lo, 1e-9), 0, 1)
    a.scatter(x, h, c=g, cmap="gray", vmin=0, vmax=1, s=1.1, marker=".",
              linewidths=0, rasterized=True)
    a.set_facecolor("#0d0d0d")
    a.text(0.010, 0.93, label, transform=a.transAxes, color="w", fontsize=10, va="top")
    a.set_ylabel("height (m)"); a.set_ylim(-6, 31); a.set_xlim(-21, 21)
    a.axhline(0, color="#e8b", lw=0.7, ls=":", alpha=0.85)
ax[-1].set_xlabel("metres east of plot centre")
fig.tight_layout(pad=0.5, h_pad=0.4)
fig.savefig(F / "fig4_lidar_cross_sections.png", dpi=200, bbox_inches="tight", facecolor="w")
plt.close(fig); print("slide fig4")

for p in sorted(F.glob("*.png")):
    from PIL import Image
    w, h = Image.open(p).size
    print(f"  {p.name:<34} {w}x{h}  aspect {w/h:.2f}")
