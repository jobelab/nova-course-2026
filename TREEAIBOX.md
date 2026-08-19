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

## It runs on CPU

Every bundled config is labelled `(GPU3GB)`–`(GPU12GB)`, but the models run on CPU.
Measured on a 6 x 6 m clip of `crsot_mixed_stand_hnorm.laz`, 965 k points, 8 threads:

| stage | time |
| --- | ---: |
| stem classification | 50.7 s |
| tree location | 2.2 s |
| shortest-path clustering | 0.1 s |

About a minute per million points, essentially all of it the stem classifier. The full
15.6 M-point plot is therefore ~13 minutes — batch work, not interactive, but perfectly
usable. Weights are ~20 MB each and download on demand.

## Two traps

**Feed the tree detector stem points only.** `treeLoc` is trained on stem points; give
it the whole cloud and it silently finds far fewer trees (5 instead of 7 on the clip).
The GUI does `pcd_abg = pcd_abg[stemcls > 1]` before calling it, and so must you.

**Pass `if_stem=True`.** The released `treeloc` weights carry a `linear_pred` head,
which the model only builds when `if_stem=True`. Without it, `load_state_dict` fails on
missing `linear_confidence` / `linear_radius` keys — the detection-head variant those
weights are not.

## Results on the clip

9 reference trees, scored by IoU >= 0.5 against the `treeid` field:

| method | trees | matched | recall | precision | mean IoU |
| --- | ---: | ---: | ---: | ---: | ---: |
| TreeAIBox, native stem clustering | 5 | 2 | 0.40 | 0.40 | 0.671 |
| B  cross-section seeds + Dijkstra | 7 | 4 | 0.44 | 0.57 | 0.722 |
| C  TreeAIBox seeds + Dijkstra | 5 | 4 | 0.44 | **0.80** | 0.720 |

Read carefully: **9 trees is a small sample** and these differences are within noise of
each other. What it does suggest is a real difference in character — the learned
detector is *conservative*. It proposed 7 seeds where the cross-section found 13, and
almost all of them were right (precision 0.80 against 0.57) at identical recall. Fewer
spurious stems, and no advantage in finding the ones both miss.

Also note the native TreeAIBox clustering labels **stem points only**, so its instances
cover a fraction of each tree and its IoU is penalised accordingly. Row C is the fairer
comparison of the seeding.

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
