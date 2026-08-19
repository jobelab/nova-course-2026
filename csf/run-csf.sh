#!/usr/bin/env bash
# Cloth Simulation Filter (CSF) ground/off-ground split for a point cloud.
#
#   ./run-csf.sh <input.laz> [outdir] [cloth_res] [class_threshold] [scene]
#
# CloudCompare's CLI writes results next to the *input* file, so the input is
# symlinked into outdir and the filter is run from there. Outputs:
#   <name>_ground_points.laz
#   <name>_offground_points.laz
#
# Defaults are tuned for the TLS plots used on Day 3 (crsot_*): an ~18 m plot
# with ~1 m of relief. For airborne (ALS) data use a coarser cloth, e.g. 0.5.
set -euo pipefail

IN=${1:?usage: run-csf.sh <input.laz> [outdir] [cloth_res] [class_threshold] [scene]}
OUTDIR=${2:-./csf_out}
CLOTH=${3:-0.2}
THRESH=${4:-0.3}
SCENE=${5:-RELIEF}          # SLOPE | RELIEF | FLAT

CC=/opt/cloudcompare-qt6-qpcl/bin/CloudCompare
[ -x "$CC" ] || { echo "CloudCompare not found at $CC" >&2; exit 1; }

IN=$(readlink -f "$IN")
mkdir -p "$OUTDIR"
OUTDIR=$(readlink -f "$OUTDIR")
ln -sfn "$IN" "$OUTDIR/$(basename "$IN")"

# PCL 1.15 is outside the default loader path; without this the PCL plugins
# fail to load (harmless for CSF itself, noisy in the log).
export LD_LIBRARY_PATH=/opt/pcl-qt6/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen}

cd "$OUTDIR"
"$CC" -SILENT \
  -C_EXPORT_FMT LAS -EXT laz \
  -O "$(basename "$IN")" \
  -CSF -SCENES "$SCENE" \
       -CLOTH_RESOLUTION "$CLOTH" \
       -CLASS_THRESHOLD "$THRESH" \
       -MAX_ITERATION 500 \
       -EXPORT_GROUND -EXPORT_OFFGROUND

rm -f "$OUTDIR/$(basename "$IN")"
echo "CSF done -> $OUTDIR"
