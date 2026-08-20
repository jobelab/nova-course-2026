# 3DFin - third-party forest inventory

[3DFin](https://github.com/3DFin/3DFin) ("3D Forest inventory") and its algorithmic
core [dendromatics](https://github.com/3DFin/dendromatics) are installed here. They
matter for two reasons: an independent implementation to check ours against, and a
better-founded approach to the tilted-stem problem.

**Nothing in `novatrees` imports either of them.** No result in this repository was
produced with 3DFin, and it is not declared in `pyproject.toml`, so a fresh checkout
will not have it. What it contributed is an idea rather than code: tracking the stem
axis section by section instead of assuming one direction, which
`novatrees.extract.track_stem_axis` reimplements, and sector occupancy, which
`novatrees.stemgeom` reimplements. The comparison below was run once, with 3DFin
barely tuned, and is not evidence that either is better.

## Installed in two places, deliberately

| environment | why |
| --- | --- |
| `NOVA_course2026/.venv` | importable from the marimo notebooks |
| `TreeAIBox/.venv` | the env CloudCompare's PythonRuntime uses |

The second one is what makes it a **CloudCompare plugin**. 3DFin declares a
`cloudcompare.plugins` entry point, and CloudCompare-PythonRuntime auto-discovers
any package that does. Verified inside CloudCompare:

    Plugin found: Python Plugin (libPythonRuntime.so)
    CC python plugins discoverable: ['3DFin']

Nothing had to be copied into a plugins folder. If it stops appearing, check that
`EnvPath` in `~/.config/CCCorp/'CloudCompare:PythonRuntime.Settings.conf'` still
points at the venv 3DFin is installed in.

## Why its approach to tilted stems is better founded

Our taper reconstruction slices horizontally and rejects a slice whose centre moves
too far from the last accepted one. On a leaning stem the centre *must* move, so the
test rejects nearly everything. A single PCA axis rotation was tried and **does not
reliably fix it** (see the commit that added `align_axis`): tree 11 improved from 3
to 7 accepted slices, tree 15 got worse from 7 to 1. It also cannot help a curved
stem, where no single axis exists.

dendromatics does the thing that actually works: **track the axis locally**, section
by section, rather than assuming one direction for the whole stem. The relevant
functions are `compute_axes_approximate`, `compute_axes_exact`, `tilt_detection`
and `compute_sections`, the last of which also checks *sector occupancy* - how much
of each circle's circumference actually has points behind it, which is the honest
way to reject a fit made from one visible arc.

## Two gotchas found while wiring it up

**It wants raw elevation in Z and normalised height in Z0.** Passing the normalised
height as both makes `compute_axes_approximate` fail with
`need at least one array to concatenate` - no cluster produces a valid axis. Build
the input as `[X, Y, raw_Z, normalised_Z]`.

**`verticality_clustering(n_points=...)` is a hard floor on cluster size**, and the
default of 1000 starves it on a plot this size:

| settings | clusters |
| --- | ---: |
| `vert > 0.7, n_points = 1000` | 22 |
| `vert > 0.7, n_points = 200` | 45 |
| `vert > 0.5, n_points = 200` | 57 |
| `vert > 0.6, n_points = 100` | 80 |

45 at `vert > 0.7, n_points = 200` is closest to the 41 reference trees.

## Wired in as a method: `novatrees.dfin_bridge`

`run_dendromatics` drives the five steps in the order 3DFin's own
`abstract_processing.py` calls them, and returns per-tree measurements, per-point
instance labels and every fitted section, so the result is scored by the same
`novatrees.evaluate` functions as everything else.

    from novatrees.dfin_bridge import prepare, run_dendromatics, section_volumes

    coords = prepare(read_cloud("crsot_mixed_stand-2.laz"))   # raw Z, normalised Z0
    r = run_dendromatics(coords)
    r.trees, r.labels, r.sections

**Parameters stay at 3DFin's shipped defaults**, with one deviation: `n_points` is
200 rather than 1000, because 1000 is a hard floor on cluster size and starves on a
plot this small. Retuning someone else's software until it agrees with yours proves
nothing.

## Measured, scored the same way as everything else

On `crsot_mixed_stand`, against the 41 reference instances, ground excluded from the
labels because dendromatics assigns every point in the cloud and we never label
ground:

| method | instances | matched of 41 | recall | precision | mean IoU | h RMSE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A  CHM watershed (PCT port) | 13 | 6 | 0.15 | 0.46 | 0.735 | 1.99 m |
| **D  3DFin / dendromatics** | **23** | **16** | **0.39** | **0.70** | **0.673** | **1.96 m** |
| B  cross-section seeds | 32 | 24 | 0.59 | 0.75 | 0.790 | 0.87 m |
| C  TreeAIBox learned seeds | 28 | 22 | 0.54 | 0.79 | 0.805 | 0.95 m |
| B+ pre-screened | 36 | 28 | 0.68 | 0.78 | 0.805 | 0.82 m |

3DFin lands between the top-down method and ours: clearly better than a CHM on a
stand where half the stems are suppressed, clearly behind cross-section seeding here.
Its 51 verticality clusters became 23 trees, so most of the loss is in
individualisation rather than in finding stems.

**Do not read that as ours being better.** 3DFin is built for plot-scale multi-scan
TLS and exposes a large parameter set through its own GUI, essentially none of which
was tuned here; ours has been tuned against this exact plot for a full session, which
is a form of overfitting. Its `maximum_height` default of 25 m and its stripe limits
are survey conventions, not physics. The useful comparison would tune both.

## Where it agrees with us, which matters more

`section_volumes` integrates the dendromatics sections the same way our measured
column does. On this plot it returns 18 usable stems with a **median cover of 0.24
and a median form factor of 0.21**.

Ours, on the Day 4 MLS, was cover 0.30 and form factor 0.24 before the fitted taper
was added. **Two independent implementations produce the same pathology**, which is
the strongest evidence available that a partial stem volume is a property of these
clouds rather than a defect in our slice acceptance. It also means 3DFin's stem
volumes carry the same caveat, and reading its output as whole-stem volume would make
the same mistake.

One difference worth noting: 3DFin is far stricter per section. It accepted 192
sections across 23 trees, roughly 8 each out of 124 attempted, because a circle is
rejected unless the inner circle is nearly empty, which is a genuinely better test for
"is this bark or foliage" than a minimum point count.

## Usage

    import dendromatics as dm

    cloud = np.c_[x, y, raw_z, normalised_z]
    stripe = cloud[(cloud[:, 3] > 0.7) & (cloud[:, 3] < 2.5)]
    clust = dm.verticality_clustering(stripe, scale=0.1, vert_threshold=0.7,
                                      n_points=200, n_iter=2)
    assigned, tree_vector, tree_heights = dm.individualize_trees(cloud, clust, ...)

`tree_vector` columns 4 and 5 are the stem X and Y; `tree_heights` carries X, Y, Z
and height per tree.

In CloudCompare: **Plugins > Python**, then 3DFin from the plugin list.
