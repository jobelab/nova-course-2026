# Analysis scripts

These reproduce every number in the project notebooks and the report. The notebooks
carry the narrative and the recorded results; these scripts carry the computation.

Run them from the repository root:

    uv run python scripts/project/01_terrain.py
    uv run python scripts/project/02_detection.py
    uv run python scripts/project/03_crowns_species.py
    uv run python scripts/project/04_stems_dbh.py
    uv run python scripts/project/05_taper_volume.py

`01_terrain.py` builds the terrain model and caches it to `out/project/dtm.npz`;
the others load that cache, so run it first.

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
