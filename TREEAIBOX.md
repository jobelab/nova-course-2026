# TreeAIBox as a third method

[TreeAIBox](https://github.com/NRCan/TreeAIBox) (NRCan) ships as a CloudCompare GUI
plugin, but its `modules/` are ordinary Python and torch, so the models can be driven
directly from a notebook. `novatrees.treeaibox` wraps the TLS boreal chain.

## What it does, and where it differs from us

    TreeAIBox   learned stem classification -> learned tree location -> shortest path
    novatrees   cross-section circle fits   -> stem seeds            -> 3D Dijkstra

The last step is the same idea in both — geodesic growing from seeds — which makes the
comparison a narrow and fair one: **only the seeding differs**. Hold the growing
constant and you are measuring a trained detector against fitted circles.

## It runs on CPU, and faster than point counts suggest

Every bundled config is labelled `(GPU3GB)`–`(GPU12GB)`, but the models run on CPU.
Measured on `crsot_mixed_stand_hnorm.laz`, 8 threads:

| stage | 6 x 6 m clip (965 k pts) | full plot (15.6 M pts) |
| --- | ---: | ---: |
| stem classification | 50.7 s | 164.6 s |
| tree location | 2.2 s | 4.4 s |

**Do not extrapolate per point.** 16x the points cost only 3.2x the time, because the
network runs over *occupied voxel blocks*, not points — a denser cloud largely fills
blocks it was already visiting. Scaling the clip timing linearly predicted ~13 minutes
for the full plot; it actually took **under 3 minutes**. Weights are ~20 MB each and
download on demand.

## Two traps

**Feed the tree detector stem points only.** `treeLoc` is trained on stem points; give
it the whole cloud and it silently finds far fewer trees (5 instead of 7 on the clip).
The GUI does `pcd_abg = pcd_abg[stemcls > 1]` before calling it, and so must you.

**Pass `if_stem=True`.** The released `treeloc` weights carry a `linear_pred` head,
which the model only builds when `if_stem=True`. Without it, `load_state_dict` fails on
missing `linear_confidence` / `linear_radius` keys — the detection-head variant those
weights are not.

## Results on the full plot

All 15.6 M points, 41 reference trees, IoU >= 0.5 against the `treeid` field:

| method | trees | matched | recall | precision | mean IoU | missed | over | under |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A  CHM watershed (PCT) | 13 | 6 | 0.15 | 0.46 | 0.735 | 26 | 6 | 7 |
| B  cross-section seeds + Dijkstra | 30 | 20 | 0.51 | 0.67 | 0.778 | 12 | 1 | 6 |
| C  TreeAIBox seeds + Dijkstra | 28 | 21 | **0.54** | **0.75** | **0.808** | **11** | 1 | **5** |

Tree-level attribute errors over the matched instances:

| method | height bias | height RMSE | XY RMSE |
| --- | ---: | ---: | ---: |
| A  CHM watershed (PCT) | +1.125 m | 1.987 m | 0.537 m |
| B  cross-section seeds + Dijkstra | -0.492 m | 0.973 m | 0.249 m |
| C  TreeAIBox seeds + Dijkstra | **-0.481 m** | **0.948 m** | **0.222 m** |

**C wins on every measure.** The learned detector proposed 34 locations against the
cross-section's 38, and turned more of them into correct trees — 21 matched from 28
surviving instances against 20 from 30. Same growing, same scoring, so the difference
is entirely in the seeding.

The character seen on a 9-tree clip held up: the detector is *conservative*, proposing
fewer seeds and wasting fewer. What the clip got wrong was the trade-off. At clip scale
the extra precision looked like it cost nothing and gained nothing in recall; at full
scale the learned seeds are better on **both** (recall 0.54 vs 0.51, precision 0.75 vs
0.67). Nine trees was too small a sample to see that, which is the argument for running
the whole plot before drawing conclusions.

A's positive height bias of +1.13 m is its merging failure showing up as a number: when
a suppressed tree is absorbed into a dominant neighbour, the reported instance is taller
than the reference tree it matched.

## Usage

    from novatrees import read_cloud, grow_instances
    from novatrees.treeaibox import treeaibox_seeds

    ds = read_cloud("plot_hnorm.laz")
    seeds, stem_mask, timings = treeaibox_seeds(ds)   # slow step lives here
    result = grow_instances(ds, seeds)                # identical growing to method B

or from the shell:

    uv run nova-trees plot_hnorm.laz --seeds-from treeaibox --extract

Requires the TreeAIBox checkout at `/home/sites/organizations/slu/courses/TreeAIBox`
and its virtualenv (torch, timm, numpy_indexed, numpy_groupies). See that repo's
`SETUP-LINUX.md`.
