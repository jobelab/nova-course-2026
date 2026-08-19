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


---

# TreeisoNet models and their parameters

## Models installed

Both live in `~/.local/share/CloudCompare/TreeAIBox/models/`, which is where the
plugin looks (`get_model_storage_dir()`), hardlinked to `models/` in this repo so
they cost disk once:

    treeisonet_tls_boreal_stemcls_esegformer3D_128_4cm(GPU3GB).pth    18 MB
    treeisonet_tls_boreal_treeloc_esegformer3D_128_10cm(GPU3GB).pth   20 MB

**Mind the filename.** The download URL strips the parentheses, the plugin's local
lookup keeps them. A file saved under the stripped name downloads fine and is then
invisible to the plugin. Verified from inside CloudCompare:

    models present: 2 of 22
      OK treeisonet_tls_boreal_stemcls_esegformer3D_128_4cm(GPU3GB)
      OK treeisonet_tls_boreal_treeloc_esegformer3D_128_10cm(GPU3GB)

## What is fixed by the model, and what you can tune

The distinction matters: half the numbers in the UI change results, and the other
half are baked into the trained weights.

**Fixed — changing these requires retraining.** From the config JSON beside each
model:

| model | voxel resolution (m) | block (voxels) | decoder dim | SR ratios |
| --- | --- | --- | ---: | --- |
| stemcls TLS 4 cm | 0.04 / 0.04 / 0.04 | 128³ | 128 | 4, 4, 2, 1 |
| stemcls TLS 10 cm | 0.10 / 0.10 / 0.10 | 128³ | 128 | 4, 4, 2, 1 |
| treeloc TLS 10 cm | 0.10 / 0.10 / 0.10 | 128³ | 64 | 8, 4, 2, 1 |
| treeloc TLS 8 cm | 0.08 / 0.08 / 0.08 | 128³ | 64 | 8, 4, 2, 1 |
| crownoff TLS 15 cm | 0.15 / 0.15 / **0.30** | 128³ | 64 | 8, 4, 2, 1 |

A 128³ block at 0.04 m spans 5.12 m; at 0.10 m it spans 12.8 m. That is the real
meaning of the resolution choice — how much of the plot the network sees at once,
against how fine a stem it can resolve. `treeLoc(custom_resolution=...)` will
override it, but the weights were trained at the config value and accuracy degrades
away from it.

Note the crownoff model is **anisotropic**: 0.15 m horizontally, 0.30 m vertically.
Crowns are wider than they are finely layered, so the vertical axis is coarser.

**Tunable at inference** — these are the ones worth sweeping. Defaults from the
plugin UI (`treeaibox_ui.html`) and the function signatures:

| parameter | default | what it does |
| --- | ---: | --- |
| `cutoff_thresh` | 0.3 | fraction of tree height kept for stem-mode treeLoc |
| `conf_thresh` | 0.3 | minimum confidence for a predicted tree top |
| `nms_thresh` | 0.5 (UI) / 0.3 (fn) | non-maximum suppression between candidate tops |
| `min_rad` | 0.2 m | smallest accepted tree radius in peak extraction |
| `max_gap` | 0.3 m | largest gap bridged when linking peaks |
| `min_res` | 0.06 m | decimation before shortest-path clustering |
| `max_isolated_distance` | 0.3 m | beyond this a cluster is dropped as an outlier |

The UI and the function disagree on `nms_thresh` (0.5 against 0.3); the UI value is
what the plugin actually passes.

## What the paper says about tuning

Xi, Z. & Degenhardt, D. (2025), *A new unified framework for supervised 3D crown
segmentation (TreeisoNet) using deep neural networks across airborne, UAV-borne, and
terrestrial laser scans*, ISPRS Open Journal of Photogrammetry and Remote Sensing —
[S266739322500002X](https://www.sciencedirect.com/science/article/pii/S266739322500002X).
Canadian Forest Service, Natural Resources Canada.

### Most hyperparameters do not matter. Two do.

> "Accuracy result from our test was insensitive to the choice of hyperparameters
> except for some key parameters like **voxel resolution and decoder dimension**."

Larger blocks, more depth, wider decoders or more channels all help accuracy, but the
authors deliberately stopped short: the models are meant to be "sufficiently accurate
… more lightweight and intervenable" rather than maximally tuned. So there is little
to gain from fiddling with attention heads or SR ratios, and a lot to lose from using
the wrong resolution.

### Resolution has an optimum per module, and it is a bell curve

Fig. 7 sweeps input point resolution for each module. Accuracy rises to a peak and
falls away, with a **broad stable plateau** around the peak — which is what makes the
models usable on data of varying quality. The optima:

| module | optimal resolution | sensitivity |
| --- | --- | --- |
| **stem point classification** (StemCls) | **4 cm** | **most sensitive** — steepest accuracy fluctuations |
| stem base detection (TreeBase / treeloc) | **10 cm** | moderate |
| crown and stem segmentation (TreeOff2D, CrownOff3D) | **30 cm or greater** | most stable |

> "Among these modules, the stem classification step is most sensitive to changes in
> input resolution … The optimal accuracies for different modules were found at
> distinct resolutions: 4 cm for stem point classification, 10 cm for stem base
> detection, and 30 cm or greater for crown and stem segmentation."

**The two models installed here are the paper's optima**: stemcls at 4 cm, treeloc at
10 cm. There is a 10 cm stemcls model in the zoo as well; on this evidence it should
be the second choice for TLS, not the first.

### Reported accuracy

Averages across the benchmark: **mIoU 0.77 for StemCls**, **F1 0.96 for TreeBase**,
**mIoU 0.98 for TreeOff2D**, **mIoU 0.85 for CrownOff3D**. Per-sensor headline mIoU is
0.81 UAV, 0.76 TLS, 0.59 ALS. StemCls held above 0.7 even on densely crowned,
irregular plots.

Two caveats the paper raises that bear on our plot. Crown detection at IoU > 0.5 is
called "an arbitrary criterion that can be problematic with complex stem points" —
the same threshold our `instance_scores` uses, so our numbers inherit that objection.
And the plot with the worst accuracy (TUWIEN_2) is the one with "more **stem tilting**
and crown overlap", which is exactly the failure mode we hit.

### Transferability

Cross-sensor use costs surprisingly little: CrownOff3D reaches mIoU 0.80 applying the
**TLS model to UAV** data, and 0.84 applying the **UAV model to TLS**.

### One discrepancy worth noting

Table 4 in the paper lists StemCls at 112³ input voxels, SR ratios 4,2,2,1 and 128
decoders. The config shipped with the released 4 cm TLS weights says 128³ and SR
4,4,2,1. The table is captioned "Example TreeisoNet DL network settings", so the
released models are not identical to the published example. **Trust the JSON beside
the weights**, not the paper table, when driving these models.

## Practical note

The two stages must be run in order and TLS stem-mode treeLoc must be fed **stem
points only** — see the trap documented earlier. On this machine, CPU inference over
the full 15.6 M-point plot took 164.6 s for stemcls and 4.4 s for treeloc.


---

# StemCls at 4 cm vs 10 cm, measured

The paper names 4 cm as the optimum for stem classification and calls that module the
most resolution-sensitive of the four. Both TLS models were run end to end on
`crsot_mixed_stand_hnorm.laz` (15.6 M points, 41 reference trees), each feeding the
same 10 cm treeloc and the same Dijkstra growing.

| | 4 cm | 10 cm |
| --- | ---: | ---: |
| stemcls, CPU | 191.2 s | **46.6 s** |
| stem points | 2,337,980 (15.0%) | 2,420,054 (15.5%) |
| tree locations | 34 | 26 |
| matched of 41 | **22** | 21 |
| recall (all 41 refs) | **0.54** | 0.51 |
| precision | 0.79 | **0.84** |
| mean IoU | **0.805** | 0.789 |
| under-segmented | 5 | **2** |
| height RMSE | 0.950 m | 0.952 m |

**The two classifications are nearly the same.** The stem masks agree at IoU 0.834,
have near-identical height profiles, and both put 98.2% of their stem points on
labelled reference trees. Whatever the 4 cm model resolves that the 10 cm one does
not, it is not changing which points get called stem at this plot's density.

**Downstream they are within noise of each other** — 22 matched trees against 21, mIoU
0.805 against 0.789 — while 10 cm runs **four times faster**. On this evidence 10 cm
is the better default for a TLS plot of this size, and 4 cm is worth the wait only if
something later depends on fine stem detail.

This does **not** contradict the paper. It measures StemCls by point-level mIoU
against stem/non-stem reference labels; we have no such labels, so we measured the
only thing we could — whether the resulting stem set produces better trees. Different
question, and the paper's answer still stands on its own metric.

## A metric artefact worth knowing about

The first version of this comparison showed 10 cm with *better* recall (0.66 against
0.58). That was an artefact. `instance_scores` was computing recall against the
reference trees a prediction happened to overlap, and the 10 cm run covered less of
the plot, so its denominator shrank from 38 to 32 — **coverage falling made recall
rise**. Against all 41 reference trees the ranking reverses to 0.54 against 0.51.

`instance_scores` now also returns `n_ref_total` and `recall_total`. Use
`recall_total` whenever the methods being compared cover different amounts of the
plot. The degenerate case makes the point: one perfectly segmented tree and nothing
else scores `recall` 1.00 and `recall_total` 0.02.
