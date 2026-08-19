# NOVA course 2026 — point cloud tooling

Working notes and tooling for the NOVA 2026 course, on WSL2 / Ubuntu 24.04.

**No data is tracked here.** Point clouds (`*.laz`), course slides and the
`PCT_demo` bundle are deliberately excluded by `.gitignore` — see the global
convention of keeping git to source, docs and configuration. Re-fetch the course
material from the organisers; regenerate derived products with the scripts here.

## Layout

    setup/      how CloudCompare + its plugins were built and wired on this machine
    csf/        Cloth Simulation Filter ground/off-ground split

## Quick start

    ./csf/run-csf.sh Day03_ToumasYrttima/crsot_mixed_stand.laz DEMO

CloudCompare itself launches with `cloudcompare` (the wrapper in `setup/bin`,
installed to `~/.local/bin`). It carries the CSF, PCL and Python plugins.

## State of the tooling, 2026-08-19

| Component | Status |
| --- | --- |
| CloudCompare | built from source, `v2.13.1-372-g0d385434`, installed to `/opt/cloudcompare-qt6-qpcl` |
| qCSF (Cloth Simulation Filter) | built and loading |
| qPCL / PCD I/O | loading, once `/opt/pcl-qt6/lib` is on the loader path |
| PythonRuntime (`pycc`) | built and loading, one local patch |
| TreeAIBox | installed, imports cleanly, **CPU-only** |

TreeAIBox runs but this machine has no NVIDIA GPU, while every bundled model
config is labelled for 3–12 GB of VRAM. Expect slow inference and test on a
small clip first.

Full detail, including the two version traps that cost the most time, is in
[`setup/cloudcompare-linux.md`](setup/cloudcompare-linux.md).

## Reference results

CSF on `crsot_mixed_stand.laz` (TLS, 18.0 × 18.8 m, 15,595,864 points) with
`-SCENES RELIEF -CLOTH_RESOLUTION 0.2 -CLASS_THRESHOLD 0.3`:

| subset | points | share | Z range |
| --- | ---: | ---: | --- |
| ground | 3,830,441 | 24.6 % | 148.05 – 149.08 m |
| off-ground | 11,765,423 | 75.4 % | 148.06 – 171.29 m |

The two subsets sum exactly to the input. Ground spans only ~1.03 m across the
plot, so `-SCENES FLAT` is worth comparing against if the DTM matters.
