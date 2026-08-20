# 3DFin - third-party forest inventory

[3DFin](https://github.com/3DFin/3DFin) ("3D Forest inventory") and its algorithmic
core [dendromatics](https://github.com/3DFin/dendromatics) are installed here. They
matter for two reasons: an independent implementation to check ours against, and a
better answer than ours to the tilted-stem problem.

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

## Why it is the better answer for tilted stems

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

## First run, and why it is not a fair comparison

With lightly-tuned parameters on `crsot_mixed_stand`:

| | trees | reference hit | recall |
| --- | ---: | ---: | ---: |
| 3DFin / dendromatics | 14 | 17 of 36 | 0.47 |
| `novatrees` with the weighted pre-screen | 37 | 33 of 36 | **0.92** |

**Do not read that as ours being better.** 3DFin is built for plot-scale multi-scan
TLS and exposes a large parameter set through its own GUI, almost none of which was
tuned here; ours has been tuned against this exact plot for a full session, which is
a form of overfitting. The useful comparison would tune both, and would be worth
doing before trusting either on a new plot.

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
