# Findings so far

**NOVA 2026 individual project, plot 167, Remningstorp**
José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
Running record, last updated 2026-09-15.

This is the working log of what has actually been established, with the evidence for
each item and an honest note on what it does not settle. The research questions and
methods are in `NOVA2026_IndividualProject_ResearchQuestions.pdf`. The code and the
executable versions of all of this are in `nova-course-2026` on `main`, under
`notebooks/project/`.

---

## 1. The delivered drone data is four acquisitions, not one

`Nadir_MS_orthomosaic.zip` holds eight products forming a 2 by 2 design, flight geometry
crossed with camera, all from Agisoft Metashape in SWEREF99 TM with RH2000 heights.

| product | points | format | channels |
|---|---:|---|---|
| `Nadir_RGB` | 46,347,917 | LAS 1.4 fmt 2 | R, G, B |
| `Oblique_RGB` | 170,060,798 | LAS 1.4 fmt 2 | R, G, B |
| `Nadir_MS` | 15,641,772 | LAS 1.4 fmt 8 | 4 bands |
| `Oblique_MS` | 49,615,363 | LAS 1.4 fmt 8 | 4 bands |

Orthomosaic GSD is 3.14 cm for RGB and 5.23 cm for multispectral. The camera is a **DJI
Mavic 3 Multispectral**: green 550 nm, red 650 nm, red edge 730 nm, near infrared 860 nm,
no blue band, alongside a 20 MP RGB camera.

**Not settled:** the flight dates. The file dates are when Metashape wrote the products.

## 2. The raster and the point cloud order their bands differently

Neither product records what its channels are. Three routes agree on the mapping:

| | ch 1 | ch 2 | ch 3 | ch 4 |
|---|---|---|---|---|
| orthomosaic | green | red | red edge | NIR |
| point cloud LAS slot | red | green | red edge | NIR |

So in the LAS, `red` is red and `green` is green, but the slot named `blue` carries **red
edge**. Sampling the orthomosaic and joining it to the cloud without accounting for this
silently swaps red and green, and nothing looks wrong because both are plausible visible
bands.

**Evidence.** A gain-independent correlation against the unambiguous RGB orthomosaic gives
`corr[b1/(b1+b2), G/(G+R)] = +0.663` over 1.77 M pixels, identifying the visible pair.
Sampling the orthomosaic at each cloud point, keeping the highest point per pixel and
correlating chromatic coordinates over 2.56 M pairs recovers the whole permutation, every
channel winning by a margin of +0.21 to +0.50. Brightness has to be divided out first or
shading dominates and nothing separates. The camera settles red edge against NIR, which
the data could not.

**Not settled by measurement:** which of bands 3 and 4 is red edge. That rests on the
instrument's fixed band order, so it would need rechecking for any other survey.

## 3. Greenness can be computed without radiometric calibration

Chromatic coordinates are ratios over the band sum, so any constant scaling of all
channels cancels. They are valid on raw digital numbers, which matters because whether
these products are calibrated reflectance is unknown and unanswerable from the files.

Measured over all four clouds, unclipped:

| cloud | points | R | **G** | B or RE |
|---|---:|---:|---:|---:|
| `Nadir_RGB` (R+G+B) | 46,347,917 | 0.3664 | **0.4278** | 0.2058 |
| `Oblique_RGB` (R+G+B) | 170,060,798 | 0.3390 | **0.4112** | 0.2499 |
| `Nadir_MS` (G+R+RE) | 15,641,772 | 0.2310 | 0.3449 | 0.4241 |
| `Oblique_MS` (G+R+RE) | 49,615,363 | 0.2335 | 0.3458 | 0.4207 |

A summer GCC in the low 0.4s is what a closed conifer canopy should give, and green above
red above blue is the vegetation signature. 282 million points, no calibration involved.

**Caution.** A normalised difference from uncalibrated digital numbers is not comparable
with published reflectance values. Scene-mean NDVI here is about +0.27 where
reflectance-based forest NDVI runs 0.7 to 0.9. These indices rank and compare within this
dataset and nothing more.

## 4. The two flight geometries differ, and it is not land cover

Clipping both to the same 20 m plot removes land cover as an explanation:

| ΔBCC, nadir to oblique | value |
|---|---:|
| full footprint | +0.0441 |
| clipped to plot 167 | **+0.0435** |

The shift survives essentially unchanged. The multispectral clouds move by less than 0.008
over the same contrast, and they have no blue band, so they are structurally blind to
whatever is driving it.

**Not settled, and this is the important part.** Land cover is the only explanation the
comparison eliminates. **View geometry**, **illumination** (the products were written three
days apart and the flight dates are unrecorded) and **radiometric processing** (per-flight
white balance and per-chunk colour adjustment) remain confounded. The honest claim is that
the acquisitions differ, not why.

## 5. Photogrammetry reconstructs the canopy and nothing beneath it

In a 5 m circle at the plot centre the drone clouds put their first percentile about 14 m
above the ground. Across the plot, 1 to 6 % of drone returns fall below 0.5 m, against
47.3 % for TLS and 28.3 % for MLS. The cross-sections show it plainly: each drone cloud is
a shell over the canopy with no ground surface at all.

**Consequence for the methods.** A DTM cannot come from the drone clouds. Normalising them
against their own lowest points would subtract canopy and shorten every tree.

## 6. The ALS and the MLS are not on the same vertical datum

This is the most consequential finding so far.

| MLS ground minus ALS terrain | median | RMSE | p05 | p95 |
|---|---:|---:|---:|---:|
| before correction | +2.089 m | 2.100 m | +1.987 | +2.242 |
| after one constant offset | +0.000 m | **0.079 m** | -0.103 | +0.153 |

513,390 MLS ground control points. The 5th and 95th percentiles sit 0.25 m apart before
correction, so this is a constant shift and not scattered error, and 8 cm RMSE after a
single constant confirms the ALS terrain had the right shape and the wrong datum.

**Why it matters.** Uncaught, it would have made every drone-derived tree height **2.089 m
too tall**, and nothing in the drone data could have revealed it, because those clouds
contain no ground of their own to argue with.

**Not settled.** Which cloud carries the error. The offset is measured against MLS ground
control and inherits whatever the MLS is worth. Resolving it needs the georeferencing
method and the flight metadata.

## 7. The TLS normalisation constant is not the surveyed elevation

`Plot_167_TLS_GroundZero.laz` arrives already normalised, with the constant unrecorded.
Matching its ground returns to the corrected terrain recovers **138.124 m**. The obvious
guess, the surveyed plot-centre elevation of 137.642 m, is wrong by 0.482 m, and an earlier
draft of this project made exactly that guess.

## 8. The sensors do not sample the same forest

Height above the corrected terrain:

| cloud | points | p50 | p95 | p99 | max | below 0.5 m |
|---|---:|---:|---:|---:|---:|---:|
| `Nadir_RGB` | 745,114 | 20.07 | 23.76 | 24.91 | 27.40 | 4.8 % |
| `Oblique_RGB` | 1,017,198 | 19.87 | 23.68 | 24.93 | 27.68 | 6.1 % |
| `Nadir_MS` | 295,497 | 20.15 | 23.61 | 24.81 | 27.72 | 1.1 % |
| `Oblique_MS` | 372,359 | 20.24 | 23.83 | 25.03 | 27.76 | 2.4 % |
| TLS | 1,500,363 | 1.29 | 20.08 | 22.75 | 29.48 | 47.3 % |
| MLS | 1,999,773 | 5.94 | 20.85 | 23.41 | 29.39 | 28.3 % |
| ALS | 1,134,909 | 17.50 | 23.77 | 25.42 | 28.56 | 25.8 % |

Median height moves from 1.29 m to 20.24 m across instruments looking at the same trees.

**On the upper canopy the drone matches the helicopter**: p95 is 23.6 to 23.8 m for every
drone cloud against 23.77 m for the ALS, and p99 is 24.8 to 25.0 against 25.4. That is the
first quantitative sign a drone can stand in for airborne lidar on canopy height.

**Maxima should not be reported.** TLS and MLS reach 29.4 m where the drone stops near
27.7 m, and a maximum is one point. Upper percentiles are the statistic.

## 9. Tree detection: precision is high, recall is size-limited

Treetops by marker-controlled watershed on a canopy height model, every acquisition
normalised against the corrected terrain, scored one-to-one against the 74 field stems at
a 2.0 m tolerance.

| cloud | tops | matched | recall | precision | F1 | offset |
|---|---:|---:|---:|---:|---:|---:|
| `Nadir_RGB` | 56 | 53 | 0.716 | 0.946 | **0.815** | 0.55 m |
| `Oblique_RGB` | 49 | 48 | 0.649 | 0.980 | 0.780 | 0.63 m |
| `Nadir_MS` | 53 | 49 | 0.662 | 0.925 | 0.772 | 0.69 m |
| `Oblique_MS` | 46 | 45 | 0.608 | 0.978 | 0.750 | 0.74 m |
| ALS | 52 | 50 | 0.676 | 0.962 | 0.794 | 0.65 m |
| MLS | 32 | 30 | 0.405 | 0.938 | 0.566 | 0.81 m |
| TLS | 32 | 30 | 0.405 | 0.938 | 0.566 | 0.74 m |

**Nadir beats oblique for both cameras**, 0.815 against 0.780 in RGB and 0.772 against
0.750 in multispectral. The oblique surveys deliver 26 to 45 % more points over the same
ground and detect fewer trees, which settles the caution recorded in finding 4: more
points are not more information.

**The drone is competitive with the helicopter**, 0.815 against 0.794.

**CHM detection is the wrong method for the ground-based clouds.** TLS and MLS reach only
0.566, not because they see less but because a canopy height model discards what they are
good at. Stem detection in the point cloud is their route.

**Recall is limited by tree size, not by sensor quality.** Detection rate by DBH quartile
for `Nadir_RGB`: 37 %, 72 %, 83 %, 95 %. The largest quartile is found nearly every time
and the smallest is missed about two thirds of the time, because those stems are
suppressed and invisible from above. So a recall of 0.72 means finding almost all of the
canopy trees and none of the ones beneath, which is a size-dependent under-count for stem
number or basal area and close to complete for dominant height or cover.

**An apparent species effect is a size effect.** Detection splits 82 % pine against 55 %
spruce, in the same direction for every cloud, but the spruce on this plot are smaller
(median 21.9 against 28.5 cm) and only 5 of the 37 larger-half stems are spruce. The
species split and the size split are the same split here, so no species claim is made.

**Not settled.** The reference is from 2011 and the data from 2021 onwards, so misses
include stems that died in between. The separation parameter is tuned against the same
reference it is scored on, which flatters every figure by roughly the spread across the
sweep, and plot 167 is the only plot with enough coverage to hold one out.

## 10. A scoring method that overstated recall, now replaced

`pipeline.match_reference` asks each side for its nearest neighbour independently, so one
detection can satisfy several references. With a 3 m tolerance on a plot whose stems are
4.12 m apart, **49 detections scored a recall of 0.865 against 74 stems**, meaning 64
stems matched by 49 tops. `evaluate.match_positions` solves the assignment instead, so a
detection is spent once. Every figure in finding 9 uses it.

## 11. Flight geometry changes an index on the same tree

Pairing crowns between acquisitions removes composition, which plot means cannot.

| pair | crowns | G share, nadir minus oblique | h95 | crown area |
|---|---:|---:|---:|---:|
| RGB | 48 | **+0.0106** [+0.0073, +0.0147] | +0.10 m | -1.8 m² |
| multispectral | 42 | **-0.0051** [-0.0067, -0.0032] | -0.16 m | -2.0 m² |

Median, interquartile range in brackets. At plot level the clipped difference in GCC was
+0.0140; per crown it is +0.0106 with an interquartile range that never crosses zero, so
about three quarters of the plot level difference is how each acquisition sees a given
tree and the rest was composition. The multispectral difference is smaller and points the
other way, on the same trees.

**Height transfers between flight geometries and crown area does not.** h95 moves by 0.10
to 0.16 m on 22 m trees, while oblique crowns come out about a third larger, 22.0 against
16.7 m² median. That larger, blurrier crown is the mechanism behind the lower oblique
detection rate in finding 9: apexes smear, neighbouring crowns merge, and the watershed
returns fewer and fatter basins.

**Crown area predicts DBH better than height does**, r = +0.686 against +0.497 over 53
crowns joined to surveyed stems. Which is awkward, because area is also the metric most
disturbed by flight geometry.

## 12. Crown colour separates pine from spruce, and RGB does it as well as multispectral

AUC is the probability a random spruce scores above a random pine. "Band" restricts to the
middle two DBH quartiles as a size control.

| cloud | index | AUC | AUC in band |
|---|---|---:|---:|
| `Nadir_RGB` | **GCC** | 0.978 | **0.954** |
| `Oblique_RGB` | **GCC** | 0.996 | **0.981** |
| `Nadir_RGB` | BCC | 0.042 | 0.092 |
| `Nadir_MS` | NDVI | 0.932 | 0.897 |
| `Oblique_MS` | NDRE | 0.973 | **0.989** |
| `Oblique_MS` | NDVI | 0.963 | 0.956 |
| `Nadir_MS` | G/(G+R+RE) | 0.723 | 0.868 |

Spruce crowns are greener in GCC, NDVI, NDRE and GNDVI and bluer in BCC, in every
acquisition.

**This is not the size effect that killed the species claim in finding 9.** Greenness does
correlate with size negatively, GCC against DBH r = -0.345 and against h95 r = -0.409, and
the spruce here are smaller. But within the middle DBH quartiles, where the medians are
28.2 and 26.0 cm, separation holds at AUC 0.954 and is if anything cleaner.

**An uncalibrated 20 MP RGB camera matches the four band multispectral payload.** GCC
reaches 0.954 and 0.981 in band against 0.897 for nadir NDVI and 0.989 for oblique NDRE.
Given the cost difference between the payloads, that is the practically interesting part.

**A wrong reading, corrected.** Comparing GCC against the multispectral `G/(G+R+RE)` made
the multispectral camera look far worse at species separation. That index ignores NIR,
which is the band the camera exists for. Tested on NDVI and NDRE it is competitive, and
the first comparison was simply unfair.

**Not settled.** Two species, one plot, about 50 crowns, spruce the minority class with 8
to 10 in the band, no held out plot, species labels from 2011, and no correction for
illumination or view angle. An AUC near 1.0 on a sample this size says these two species
are clearly different here, not that a classifier would perform this well elsewhere. GCC
and BCC are near mirrors of each other and are not independent evidence.

## 13. Stems and diameter, which only the ground sensors provide

Two corrections were needed before the comparison meant anything.

**TLS and MLS were being scored over ground they were never given.** Both are delivered as
a 30 by 30 m box on the plot centre, 900 m², while the plot is a 20 m circle of 1256 m².
**28 % of the plot was never scanned**, and 24 of the 74 field stems fall outside the box.
This also depresses the TLS and MLS figures in finding 9.

**The circle fit had no robustness.** `pipeline.detect_seeds` fits a Taubin circle over
every point in a cluster. `stems.detect_stems` fits by RANSAC and gates on roundness, arc
coverage and vertical continuity.

| cloud | fit | DBH bias | DBH RMSE | r |
|---|---|---:|---:|---:|
| TLS | Taubin | +7.26 cm | 10.91 cm | +0.117 |
| TLS | **RANSAC + gates** | +3.58 cm | **3.88 cm** | **+0.972** |
| MLS | Taubin | +11.44 cm | 18.11 cm | -0.070 |
| MLS | **RANSAC + gates** | +4.76 cm | **4.98 cm** | **+0.970** |

The loose fit produced diameters with no relationship to the field measurement at all.
That is not a precision problem; it is measuring the cluster instead of the stem.

Scored over the box, the stem route reaches **F1 0.800 for TLS and 0.795 for MLS**,
against 0.566 for the canopy height model on the same clouds. The method has to change
with the sensor, which is the Day 3 result reappearing from the other side. Recall near
0.68 is occlusion, which no fit improves.

**The diameter bias was the forest growing.** Median plot DBH was 25.8 cm in 2011 and is
31.3 cm now, +5.5 cm in fifteen years, and the measured bias against the 2011 survey is
+3.7 and +4.8 cm. Against a contemporaneous list the bias is -1.26 cm (TLS, RMSE 1.30,
r 0.999) and -0.14 cm (MLS, RMSE 0.34, r 0.999). **That second comparison is a check on
the implementation, not validation:** the current list carries millimetre heights for 441
trees, so it is almost certainly derived from this same laser scanning, and agreement at
r = 0.999 says the pipeline reproduces another processing of the same data.

## 14. The RQ5 boundary falls exactly where the line of sight does

| attribute | from above | from below |
|---|---|---|
| tree detection | F1 0.815 drone, 0.794 ALS | F1 0.800 TLS, 0.795 MLS |
| canopy height | p95 transfers between geometries | poorly, canopy under-sampled |
| crown area | r = +0.686 with DBH | no |
| **stem diameter** | **not at all** | **RMSE 1.3 cm** |

Detection is a draw across viewpoints. Everything else splits by what the instrument can
see, and the split is not about quality: the drone cannot measure a diameter because it
never sees a stem, and the TLS cannot give a canopy height because it barely sees the top.

## 15. Taper and volume, and a fusion argument that did not survive testing

Taper reconstructed for 35 TLS stems, each followed upward from breast height and
integrated slice by slice.

| | median | p25 | p75 |
|---|---:|---:|---:|
| covered fraction of tree height | 0.85 | 0.80 | 0.89 |
| form factor | **0.454** | 0.431 | 0.481 |
| stem volume | 0.765 m³ | | |

DBH from the full taper curve agrees with the independent cross-section fit at
**r = +0.995**. The form factor sits inside the 0.45 to 0.50 band expected of a boreal
conifer, which is the strongest sign that terrain, stem tracking and integration together
produce a physically sensible tree.

**The form factor is partly a measurement artefact.** Against covered fraction it gives
r = +0.803, so a good part of the 0.431 to 0.481 spread is how much of each tree the
scanner could see rather than how the trees are shaped. Reading a form factor as a
property of the forest is a mistake when it is partly a property of the occlusion.

**The usual multi-sensor argument for volume does not hold here.** Diameter only from
below and the treetop only from above suggests volume needs both. Reconstructing the same
21 stems with and without the drone height:

| | with drone height | without |
|---|---:|---:|
| form factor | 0.462 | 0.452 |
| covered fraction | 0.861 | 0.828 |
| measured volume | 0.847 m³ | 0.847 m³ |

The volume is identical and the form factor moves by 0.010. The TLS already reconstructs
about 86 % of these trees, so its own upper extent is a close proxy for the top, and the
measured volume is an integral over what was reconstructed and never depended on the drone.

**What the drone contributes is coverage, not the top of a stem.** It sees the whole
1256 m² plot including the 28 % with no ground-based data at all. That is a real and large
contribution, but it is an argument about where the instrument was, not about what it
could see from there. Whether fusion matters more on badly-seen trees is not answerable
here, because the 21 stems compared are the ones reconstructed well enough to pair.

**Plot level.** 25.4 m³ over 34 stems in the 900 m² scanned area is 282 m³ per hectare
from detected stems alone. Detection recall over that area is 0.68, so the true figure is
higher, by less than the missing third since the undetected stems are the small ones. A
stand volume from this would need the size-dependent detection bias corrected rather than
ignored.

**Not settled.** Volume has no field reference. Internal consistency and a plausible form
factor are not validation.

## 16. Corrections to earlier readings, kept deliberately

Three claims in this project were wrong and were caught:

- **"The TLS clouds are not georeferenced."** Taken from a course README. They are
  georeferenced in plan and normalised in height, so the co-registration problem is
  vertical, not planimetric.
- **"Only the TLS carries Amplitude, Reflectance and Deviation."** Also from the README.
  All three plot 167 clouds are LAS point format 3 with plain intensity and no extra
  dimensions. Those Riegl fields are on the day 1 exercise cloud, a different site about
  300 km north.
- **The multispectral band order.** An early reading had red and green swapped in the LAS,
  argued from band means compared across bands, which is invalid when per-band gains are
  unknown. Caught by computing `G/(G+R+RE)` and getting red brighter than green.
- **A recall of 0.865 that was really many-to-one matching.** See finding 10.
- **"RGB separates species better than multispectral."** True only against the
  multispectral visible-only index, which ignores NIR. See finding 12.
- **TLS and MLS scored over the whole plot.** They cover only 72 % of it. The figures in
  finding 9 are depressed for that reason. See finding 13.

The pattern is the same each time: a claim taken from documentation rather than from the
files. Everything in this document is measured from the data.

---

## Open questions put to the course teachers

1. **When were the two UAV flights flown?** Decides whether the difference in finding 4
   can be read as view geometry or stays confounded with illumination.
2. Is the multispectral orthomosaic raw digital numbers or calibrated reflectance?
3. Flight height, overlap, and oblique camera tilt.
4. Georeferencing method and its accuracy, which bears directly on finding 6.
5. Is the Metashape processing report available?

## Next

Outlier filtering, the canopy height model, tree detection and crown segmentation, crown
level aggregation, then the RQ4 and RQ5 comparisons against the field tree list.
