# Analysis scripts

One source of truth for the computation.

`analysis.py` holds the analyses as cached functions. The scripts here call them and
print; the notebooks in `notebooks/project/` call the same functions and render. Nothing
heavy is duplicated between them, and because every function caches to `out/project/`,
the first caller pays the cost and everything after opens immediately.

    warm_cache.py     build every cached artefact once, then nothing recomputes
    _common.py        plot geometry, terrain, memory-safe readers
    analysis.py       detections(), crowns(), stems(), taper(), heights()

Run the scripts from the repository root:

    uv run python scripts/project/01_terrain.py
    uv run python scripts/project/02_detection.py
    uv run python scripts/project/03_crowns_species.py
    uv run python scripts/project/04_stems_dbh.py
    uv run python scripts/project/05_taper_volume.py

The first run of any of these builds what it needs and caches it. To pay that cost once
and up front instead:

    uv run python scripts/project/warm_cache.py

Delete a file in `out/project/` to force that step to recompute, or pass `rebuild=True`
to the function. `out/` is not versioned, so a fresh clone rebuilds from the clouds.

## Notebooks

`notebooks/project/` holds the interactive chapters, which import `analysis` and render
its output with live controls. `notebooks/project/narrative/` keeps read-only copies of
the four chapters that were originally written as narrative: they open in a second, need
no data at all, and are the right thing to hand someone who wants to read the findings
rather than rerun them.

## Data

The point clouds are not in the repository. `_common.py` looks for the field data and
the clipped drone clouds at the paths documented in `data/drone/README.md`, and both
can be overridden:

    NOVA_FIELD=/path/to/field NOVA_DRONE=/path/to/drone uv run python scripts/project/01_terrain.py

## Memory

This work ran on a machine with 15 GB of RAM, and two of these steps will exhaust it
if written naively. `_common.height_band` and `novatrees.io.read_sample` both thin
inside the chunk loop, with the keep probability worked out from the file header
before the loop starts. Collecting points first and thinning afterwards does not work
here: `Plot_167_TLS_GroundZero.laz` holds 290 million points in a 30 by 30 m box, and
the 20 m plot circle is larger than that box, so clipping to the plot discards almost
nothing.

`_common.voxel` caps density before anything neighbour-based. TLS records about
323,000 points per m², and an 8 cm DBSCAN neighbourhood at that density holds
thousands of points per query.

Running under a cap is a cheap way to make a mistake fail the script instead of the
session:

    (ulimit -v 9000000; uv run python scripts/project/05_taper_volume.py)
