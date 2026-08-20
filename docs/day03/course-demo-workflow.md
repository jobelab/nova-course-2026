# Course demo: tree detection and segmentation (CloudCompare + PCT_demo)

Reference copy of the Day 3 demo instructions, *Computational Approaches for Tree
Detection and Segmentation* - CloudCompare v2.13.2 with PCT_demo.

Source: [published Google Doc](https://docs.google.com/document/d/e/2PACX-1vRNw-xE7l-sYjG515f5sMCPIhhnwzG04wBz3AXGun7NhGfnG59TpTfv0viCxtCs5Y8nPSNL596iXJc_/pub)

> **This is a structured transcription, not a verbatim copy.** It was produced by
> fetching and summarising the published document, so wording is paraphrased and
> anything the original left implicit may be missing. Treat the Google Doc as
> authoritative and this as a working index. Where the document says "adjust" or
> "play around with" a setting rather than giving a number, that is noted.

Data: `crsot_mixed_stand.laz`, `crsot_tree.laz`.

---

## Phase 1 - Ground classification and height normalisation

| step | menu path | settings |
| --- | --- | --- |
| Ground filter | select cloud → **CSF Filter** | cloth resolution **1.000**, classification threshold **0.300**, export cloth mesh ✓ |
| Distance to ground | **Tools > Distances > Cloud/Mesh Dist** | produces `C2M signed distances` |
| Normalise height | **Edit > Scalar Fields > Set SF as coordinates** | writes the distance into Z |

Note the normalisation route: height above ground is the **point-to-cloth-mesh
distance**, taken straight from the CSF cloth. No DTM raster is built at all.

## Phase 2 - Horizontal slice and stem filtering

| step | menu path | settings |
| --- | --- | --- |
| Slice | **Cross Section** tool | **1.2–1.4 m** above ground, thickness **20 cm**, export selection as new entity |
| Normals | **Edit > Normals > Compute** | surface model **Plane**, neighbour radius **0.015 m**, orientation by **minimum spanning tree** |
| Normals → SF | **Edit > Normals > Export normals to SF(s)** | gives the components used for verticality |
| Reflectance rescale | **Edit > Scalar Fields > Arithmetic** | see below |
| Select stems | **Edit > Scalar Fields > Filter by value** | export the subset |
| Clean | **Tools > Clean > Noise filter** | |

### The reflectance arithmetic

Applied in sequence, quoted intent from the document:

1. **Add 26** - "to make the range entirely positive"
2. **Divide by 31** - "to make it fit approximately 0–1 scale"
3. **Inverse** the scale
4. **log10** - convert to logarithmic values

The point of Phase 2 is that **two features are combined** - surface-normal
verticality and reflectance - to separate stems from branches and foliage.

## Phase 3 - Cross-section clustering and seed extraction

| step | menu path | settings |
| --- | --- | --- |
| Cluster | **Tools > Segmentation > Label Connected Components** | set a minimum cluster point count; colour randomly |
| Review | manual | inspect clusters, discard the bad ones |
| Stem centres | **Tools > Sand box > Create cloud from selected entries centres** | one point per stem |
| Give ids | **Edit > Scalar Fields > Add point indexes as SF(s)** | |
| Display | | stem centre point size **16** |

The document does not give an octree level or a specific minimum point count.

## Phase 4 - 3D Dijkstra region growing

| step | detail |
| --- | --- |
| Distances | cloud-to-cloud, stem centres against the full cloud |
| Tool | **PCT_demo.exe**, instance segmentation (first option) |
| Method | "3D Dijkstra Region Growing to label all points with corresponding treeIDs, based on seed-voxel connectivity paths" |
| Output | treeID stored in the **UserData** attribute |

## Phase 5 - Semantic segmentation and stem taper

Using PCT_demo's semantic segmentation tool on a single tree (`crsot_tree.laz`):

1. Load the segmented tree instance
2. Compute surface normals - neighbour count is left to the user to adjust
3. Visualise geometric and spectral features
4. Apply **weighted filtering** to separate stem from branches and foliage
5. **RANSAC cylinder** fitting from stem base to top, giving the taper curve
6. Export to the input file's folder

No RANSAC parameters are specified; the document says to experiment.

## Bonus

The document points to **TreeAIBox**, "a CloudCompare Python plugin for a suite of
LiDAR processing modules targeting forest and tree analysis". Installed here - see
[`TREEAIBOX.md`](../../TREEAIBOX.md).

---

## How this repo's pipeline compares

`novatrees` is an independent implementation of the same ideas, written by a course
participant rather than as a course deliverable. It does not follow the demo step for
step. It did converge on the identical method for Phase 4 before this document was
read - **3D Dijkstra region growing from stem seeds** - and differs as follows.

| phase | course demo | `novatrees` | note |
| --- | --- | --- | --- |
| 1 ground | CSF, cloth **1.000** | CSF, cloth **0.20** | ours is finer; both use threshold 0.30 |
| 1 normalise | distance to CSF **cloth mesh** | **DTM quantile 0.25** per 0.5 m cell | different route; ours validated at bias −0.002 m, RMSE 0.068 m vs the supplied `_hnorm` |
| 2 slice | **1.2–1.4 m** | 1.15–1.45 m | effectively the same slab |
| 2 filter | **verticality + reflectance** | `novatrees.features`, weighted and pre-screened | adopted after this doc was written; see below for what it was worth |
| 3 cluster | connected components + manual review | DBSCAN + circle fit + vertical continuity | ours is automatic, no manual step |
| 4 grow | PCT_demo Dijkstra | multi-source Dijkstra on a kNN graph | same method, independently arrived at |
| 5 taper | RANSAC cylinders | RANSAC circles per slice, `novatrees.taper` | implemented after this doc was written; adds Kozak / polynomial / spline fits and stem volume |

### The verticality + reflectance filter is worth adopting

Our pipeline clustered the raw slice, which merges stems that stand close together.
Concretely, predicted tree 12 merged three reference trees (98%, 96% and 40% of
refs 84, 79 and 70) because two of those stems are only **0.31 m apart** - closer
than the DBSCAN neighbourhood, so they formed one cluster and produced one seed.

Measured on the band 0.7–2.0 m of `crsot_mixed_stand_hnorm.laz`:

| | verticality | reflectance |
| --- | ---: | ---: |
| ref 84 (stem) | 0.904 | −0.50 dB |
| ref 79 (stem) | 0.933 | −0.46 dB |
| foliage | 0.817 | −9.78 dB |

Reflectance separates stem from foliage by about **9 dB** - a far stronger signal
than verticality alone, which is why the demo combines the two.

Full-plot instance scores against the reference `treeid`, 41 trees:

| slice filter | eps | seeds | matched | recall¹ | precision | mean IoU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| none (our previous default) | 0.08 | 60 | 24 | 0.63 | 0.67 | 0.799 |
| none | 0.04 | 80 | 27 | 0.71 | 0.59 | 0.804 |
| verticality > 0.85 | 0.08 | 43 | 26 | 0.68 | 0.70 | 0.802 |
| reflectance > −20 dB | 0.08 | 62 | 27 | 0.71 | 0.75 | 0.809 |
| **verticality > 0.85 AND reflectance > −20 dB** | **0.08** | 45 | **28** | **0.74** | 0.72 | **0.812** |

¹ These recalls are against the reference trees each run overlapped, which is how
`instance_scores` reported it at the time. Against all 41 trees the pre-screened run
scores **0.68** rather than 0.74. The comparison between rows still holds - they were
computed the same way - but see the corrected table in the README for absolute figures.

Shrinking `eps` to 0.04 reaches the same recall but costs precision (0.59), because
it also fragments single stems. Filtering on shape and reflectance first gets there
**without** that trade - the same recall at 0.72 precision and the best mean IoU.

Verticality here is computed as `1 - |n_z|` from local PCA over a 20-neighbour
patch, `n` being the smallest eigenvector. That is the same quantity CloudCompare
produces via *Compute normals → export to SF*, just calculated directly.
