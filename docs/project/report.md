% How much of a forest measurement belongs to the forest
% José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
% NOVA 2026 individual project: point cloud processing for forestry

# Summary

Seven point cloud acquisitions cover a single 20 m forest plot at Remningstorp: four from
a drone, crossing nadir against oblique flight and an RGB against a multispectral camera,
plus terrestrial, mobile and helicopter laser scanning. Seventy-four stems on the plot
have been surveyed in the field. That makes it possible to ask, for one piece of forest,
how much of a measured attribute is a property of the trees and how much is a property of
the instrument that measured them.

The short answer is that it depends entirely on the attribute. Canopy height transfers
between acquisitions almost unchanged. Tree detection is a draw between a drone and a
helicopter but collapses for ground-based scanners unless the method changes with the
sensor. Stem diameter is available only from below, and colour separates the two species
present almost completely, from an uncalibrated consumer camera.

Two results were not what I expected. A vertical datum offset of 2.089 m between the
helicopter lidar and the mobile scanner would have made every drone-derived tree height
that much too tall, and nothing in the drone data could have revealed it. And the standard
argument that stem volume needs both viewpoints did not survive being tested.

# 1. Purpose and questions

Point cloud processing was used to derive canopy structure and canopy colour at plot and
tree level from several acquisitions of the same forest, and then to establish how far
those attributes are properties of the forest rather than of the acquisition. The 2 by 2
drone design separates flight geometry from band set, and the laser scanning and field
survey provide the reference.

The questions were set before the processing began.

**RQ1.** Does UAV flight geometry change canopy colour metrics over a fixed plot?
**RQ2.** Does the spectral band set decide how sensitive a greenness index is to
acquisition geometry, and how do the indices compare with what the laser scanners record?
**RQ3.** Can canopy greenness be derived from radiometrically uncalibrated clouds?
**RQ4.** How does flight geometry affect which canopy surface is reconstructed, and do
structural attributes follow?
**RQ5.** What can a photogrammetric cloud measure relative to co-located laser scanning
and the field tree list?

# 2. Data

The study plot is plot 167 (TRAKT 167) at Remningstorp in Västergötland, Sweden, centred
at E 420407.631, N 6481815.136 in SWEREF99 TM, with a surveyed ground elevation of
137.642 m in RH2000.

![**Figure 1.** Plot 167 in its stand, on the nadir RGB orthomosaic. The 20 m plot boundary is yellow and the five TLS and MLS scan positions are marked. The wider view is 260 m across and shows why a common footprint matters: the drone surveys reach well beyond the stand, across roads and open ground the plot does not contain.](figures/fig1_plot_context.png)

## 2.1 Drone photogrammetry

One archive holds eight products forming a 2 by 2 design, all produced in Agisoft
Metashape and delivered in SWEREF99 TM with RH2000 heights.

| product | points | format | orthomosaic GSD |
|---|---:|---|---:|
| `Nadir_RGB` | 46,347,917 | LAS 1.4 fmt 2 | 3.14 cm |
| `Oblique_RGB` | 170,060,798 | LAS 1.4 fmt 2 | |
| `Nadir_MS` | 15,641,772 | LAS 1.4 fmt 8 | 5.23 cm |
| `Oblique_MS` | 49,615,363 | LAS 1.4 fmt 8 | |

The camera is a DJI Mavic 3 Multispectral: green 550 nm, red 650 nm, red edge 730 nm and
near infrared 860 nm, with no blue band, alongside a 20 MP RGB camera. The flight dates
are not recorded anywhere in the data and have been requested from the course teachers.
The file dates, 2026-08-17 for the nadir products and 2026-08-20 for the oblique ones, are
when Metashape wrote them.

## 2.2 Laser scanning and field reference

| | instrument | points | delivered extent |
|---|---|---:|---|
| TLS | Riegl VZ-400i | 290,336,075 | 30 by 30 m on the plot centre |
| MLS | Faro Orbis | 61,020,343 | 30 by 30 m |
| ALS | helicopter, Riegl MiniVUX-1DL + VUX-1HA + VQ-840-G | 11,205,212 | 60 by 60 m |

All three carry plain intensity and no extra dimensions. The TLS is georeferenced in plan
but its heights arrive normalised to ground zero by an unrecorded constant.

**The TLS and MLS boxes are 900 m² and the plot is 1256 m², so 28 % of the plot has no
ground-based coverage at all**, and 24 of the 74 field stems fall outside it. Scoring
those instruments over the whole plot counts undelivered data as failure, and all figures
below score them over the box.

The field reference is 74 stems surveyed in 2011, with stem centres, diameter and species:
45 Scots pine and 29 Norway spruce, DBH 15.0 to 36.4 cm, mean spacing 4.12 m. The survey
is fifteen years older than the scans, which matters and is used below.

# 3. Methods

All processing is in Python 3.13 in a `uv`-locked environment, written as a library
(`novatrees`). Six marimo notebooks carry the narrative and the recorded results, and
five scripts under `scripts/project/` carry the computation and reproduce every number in
this report. The terrain model is cached so the later steps do not rebuild it.

**Clipping.** Every acquisition was clipped to `plot20mR`, the 20 m plot polygon for
TRAKT 167, chosen because the field tree list is defined on it and because it is the only
plot layer carrying a documented coordinate system.

**Terrain.** A photogrammetric cloud reconstructs only surfaces the cameras saw, and under
closed canopy the ground is not one of them, so the terrain came from lidar. A DTM was
built from ALS ground returns and tied to MLS ground control.

**Colour indices.** Chromatic coordinates were the primary index because each is a ratio
over the band sum, so any constant scaling of all channels cancels and the index is valid
on uncalibrated digital numbers.

**Detection and segmentation.** Treetops by marker-controlled watershed on a canopy height
model, scored against the field stems by optimal one-to-one assignment at a 2.0 m
tolerance, under half the mean stem spacing.

**Stems.** Breast-height cross-sections clustered and fitted by RANSAC, gated on roundness,
arc coverage and vertical continuity, then each stem tracked upward and its taper
integrated.

# 4. Results

## 4.1 Reading the multispectral bands

Nothing in the delivered files records which channel is which. Three routes agree. A
gain-independent correlation against the unambiguous RGB orthomosaic identified the
visible pair. Sampling the orthomosaic at each cloud point and correlating chromatic
coordinates over 2.56 million pairs recovered the whole permutation, each channel winning
by a margin of 0.21 to 0.50. The camera settled red edge against near infrared, which the
data could not.

| | channel 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| orthomosaic | green | red | red edge | NIR |
| point cloud LAS slot | red | green | red edge | NIR |

The two products order their first two bands differently. Sampling the orthomosaic and
joining it to the cloud without accounting for this silently swaps red and green, and
nothing looks wrong because both are plausible visible bands.

## 4.2 What each instrument sees

![**Figure 2.** The four drone acquisitions from above, clipped to the plot. The RGB clouds are true colour; the multispectral clouds have no blue band and are rendered from red, green and red edge. Crowns separate cleanly in nadir and blur in oblique.](figures/fig2_drone_from_above.png)

![**Figure 3.** The same four acquisitions in cross-section, a 6 m slab through the plot centre. Every cloud is a shell over the canopy, with almost nothing below 15 m and no ground surface at all.](figures/fig3_drone_cross_sections.png)

![**Figure 4.** The same slab recorded by the three laser scanners, shaded by intensity. TLS and MLS see stems from the ground up and the ground itself; the helicopter sees canopy and ground but almost no stem. The TLS and MLS panels stop at 15 m because those clouds are delivered as a 30 by 30 m box.](figures/fig4_lidar_cross_sections.png)

Figures 3 and 4 are the argument for the whole project in two images. Measured in a 5 m
circle at the plot centre, the drone clouds put their first percentile about 14 m above
the ground: there is no ground in them to find.

![**Figure 5.** Vertical distribution of returns above the terrain model. The same stand gives a median return height of 1.29 m from TLS, 5.94 m from MLS, 17.50 m from ALS and about 20 m from every drone cloud.](figures/fig5_vertical_profiles.png)

Nearly half the TLS returns fall within 0.5 m of the ground against 1 to 6 % of the drone
returns. On the upper canopy, however, the drone matches the helicopter: p95 is 23.6 to
23.8 m for every drone cloud against 23.77 m for the ALS.

## 4.3 A vertical datum offset that nothing else would have caught

Building the terrain from the ALS and checking it against 513,390 MLS ground control
points:

| MLS ground minus ALS terrain | median | RMSE | p05 | p95 |
|---|---:|---:|---:|---:|
| before correction | +2.089 m | 2.100 m | +1.987 | +2.242 |
| after one constant offset | +0.000 m | **0.079 m** | -0.103 | +0.153 |

The 5th and 95th percentiles lie 0.25 m apart before correction, so this is a constant
shift and not scattered error, and 8 cm RMSE after a single constant says the ALS terrain
had the right shape and the wrong datum. **Uncaught, it would have made every
drone-derived tree height 2.089 m too tall**, and nothing in the drone data could have
revealed it, because those clouds hold no ground of their own to disagree with.

The same control recovered the TLS normalisation constant as 138.124 m. The obvious guess,
the surveyed plot-centre elevation of 137.642 m, is wrong by 0.482 m.

## 4.4 Flight geometry (RQ1, RQ4)

Chromatic coordinates were computed for 282 million points with no calibration. Summer GCC
in the low 0.4s with green above red above blue is what a closed conifer canopy should
give.

Nadir and oblique differ, and the difference is almost entirely blue: BCC moves from
0.2058 to 0.2499 while GCC falls 0.017. Clipping both to the plot leaves that shift
unchanged, +0.0441 becoming +0.0435, which eliminates land cover as the explanation.

Pairing the same crown between acquisitions is the stronger test, because it removes
composition entirely:

| pair | crowns | G share, nadir minus oblique | h95 | crown area |
|---|---:|---:|---:|---:|
| RGB | 48 | **+0.0106** [+0.0073, +0.0147] | +0.10 m | -1.8 m² |
| multispectral | 42 | **-0.0051** [-0.0067, -0.0032] | -0.16 m | -2.0 m² |

About three quarters of the plot-level difference is how each acquisition sees a given
tree. The multispectral band set, which has no blue, moves less and in the other
direction.

**Height transfers between flight geometries and crown area does not.** h95 moves 0.10 to
0.16 m on 22 m trees, while oblique crowns come out about a third larger, 22.0 against
16.7 m² median.

## 4.5 Detection (RQ4, RQ5)

| cloud | tops | recall | precision | F1 |
|---|---:|---:|---:|---:|
| `Nadir_RGB` | 56 | 0.716 | 0.946 | **0.815** |
| `Oblique_RGB` | 49 | 0.649 | 0.980 | 0.780 |
| `Nadir_MS` | 53 | 0.662 | 0.925 | 0.772 |
| `Oblique_MS` | 46 | 0.608 | 0.978 | 0.750 |
| ALS | 52 | 0.676 | 0.962 | 0.794 |
| TLS, canopy height model | 32 | 0.405 | 0.938 | 0.566 |
| **TLS, stem cross-section** | 35 | 0.680 | 0.971 | **0.800** |
| **MLS, stem cross-section** | 33 | 0.660 | 1.000 | **0.795** |

**Nadir beats oblique for both cameras**, which runs against the point counts: the oblique
surveys deliver 26 to 45 % more points over the same ground and find fewer trees. The
larger, blurrier crowns are the mechanism.

**The method has to change with the sensor.** The same TLS cloud scores 0.566 through a
canopy height model and 0.800 through a stem cross-section. A CHM discards everything a
ground-based scanner is good at.

![**Figure 6.** Detection rate by field DBH quartile. The largest quartile is found nearly every time and the smallest is missed about two thirds of the time.](figures/fig6_detection_by_dbh.png)

Precision is 0.93 to 1.00 everywhere and recall is the limit. Figure 6 explains it: the
misses are suppressed stems that never reach the canopy. A recall of 0.72 is not missing a
quarter of the forest, it is finding almost all of the canopy trees and none of the ones
beneath them. For stem count or basal area that is a size-dependent under-count; for
dominant height or cover it is close to complete.

## 4.6 Species (RQ2, RQ3)

![**Figure 7.** Crown-level separation of the two species. Left and centre: pine against spruce for GCC from the nadir RGB cloud and NDVI from the nadir multispectral cloud. Right: GCC against field DBH, showing that greenness also falls with size.](figures/fig7_species.png)

AUC is the probability a randomly chosen spruce scores above a randomly chosen pine.
"Band" restricts to the middle two DBH quartiles as a size control.

| cloud | index | AUC | AUC in band |
|---|---|---:|---:|
| `Nadir_RGB` | **GCC** | 0.978 | **0.954** |
| `Oblique_RGB` | **GCC** | 0.996 | **0.981** |
| `Nadir_RGB` | BCC | 0.042 | 0.092 |
| `Nadir_MS` | NDVI | 0.932 | 0.897 |
| `Oblique_MS` | NDRE | 0.973 | 0.989 |
| `Nadir_MS` | G/(G+R+RE) | 0.723 | 0.868 |

Spruce crowns are greener and pine crowns bluer, in every acquisition. Greenness does fall
with size (GCC against DBH r = -0.345), and the spruce here are smaller, but restricting
to comparable diameters leaves the separation intact.

**An uncalibrated 20 MP RGB camera matches the four-band multispectral payload at
separating these two species.** Given the cost difference between the payloads, that is
the practically interesting result.

## 4.7 Stems, diameter and volume (RQ5)

![**Figure 8.** Left: TLS stem diameter against two references. The offset against the 2011 survey is fifteen years of growth; against a contemporaneous list the bias is -1.26 cm with RMSE 1.30 cm. Right: form factor against the fraction of tree height reconstructed, with the boreal conifer band shaded.](figures/fig8_dbh_and_form.png)

Fitting the breast-height cross-section robustly rather than with a plain Taubin circle
changed diameter from useless to excellent: r rose from +0.117 to +0.972 on the same
clusters. Arc coverage is the gate that matters, because a scanner sees one side of a stem
and a circle through a short arc is nearly unconstrained.

| cloud | reference | n | bias | RMSE | r |
|---|---|---:|---:|---:|---:|
| TLS | 2011 survey | 34 | +3.65 cm | 3.93 cm | +0.972 |
| TLS | contemporaneous list | 35 | -1.26 cm | 1.30 cm | +0.999 |
| MLS | contemporaneous list | 33 | -0.14 cm | 0.34 cm | +0.999 |

**The bias against the field survey is the forest growing.** Median plot DBH was 25.8 cm
in 2011 and is 31.3 cm now, +5.5 cm in fifteen years, against a measured bias of +3.7 cm.
The near-perfect agreement with the contemporaneous list is a check on the implementation
rather than validation, because that list carries millimetre heights for 441 trees and is
almost certainly derived from this same laser scanning.

Taper reconstructed for 35 stems gave a covered fraction of 0.85, a form factor of 0.454,
inside the 0.45 to 0.50 band expected of a boreal conifer, and a median stem volume of
0.765 m³. But form factor correlates with covered fraction at r = +0.803, so part of its
spread is occlusion rather than tree shape.

**The usual multi-sensor argument for volume did not survive testing.** Reconstructing the
same 21 stems with and without the drone supplying total height gave an identical measured
volume of 0.847 m³ and a form factor moving only from 0.452 to 0.462. The TLS already
reconstructs 86 % of these trees, so its own upper extent is a close proxy for the top.

# 5. Discussion

**The boundary between instruments falls where the line of sight does.**

| attribute | from above | from below |
|---|---|---|
| tree detection | F1 0.815 drone, 0.794 ALS | F1 0.800 TLS, 0.795 MLS |
| canopy height | transfers between geometries | poor, canopy under-sampled |
| crown area | r = +0.686 with DBH | no |
| stem diameter | not at all | RMSE 1.3 cm |

Detection is a draw. Everything else splits by viewpoint, and not by quality: the drone
cannot measure a diameter because it never sees a stem, and the TLS cannot give a canopy
height because it barely sees the top.

**Where fusion actually helps is coverage, not attributes.** The expected argument, that
volume needs a diameter from below and a top from above, was measurably wrong here. What
the drone contributes is that it sees the whole plot, including the 28 % with no
ground-based data. That is an argument about where the instrument was, not what it could
see from there.

**More points are not more information.** The oblique surveys carry 26 to 45 % more points
over the same ground and detect fewer trees, because off-nadir views smear the crown apex.
Point density is a poor proxy for information content.

**The most dangerous errors were the ones the data could not reveal.** A 2.089 m vertical
datum offset and a wrongly assumed TLS constant would both have propagated silently into
every derived height. Neither is visible without a second instrument to disagree.

# 6. Limitations

The field reference is from 2011 and the scans from 2021 onwards, so misses include stems
that died in between. Detection parameters were tuned against the same reference they are
scored on. Species separation rests on two species, one plot and about 50 crowns, with
spruce the minority class, and an AUC near 1.0 on that sample says these two species are
clearly different here, not that a classifier would generalise. Stem volume has no field
reference at all. Flight dates, radiometric calibration and georeferencing method are
unknown, so view geometry, illumination and per-flight processing remain confounded in
every comparison between the two drone acquisitions.

# 7. Conclusions

1. Canopy height is robust to acquisition; crown area, detection and colour are not.
2. Detection is limited by tree size rather than sensor quality, and the bias is
   size-dependent.
3. Uncalibrated RGB chromatic coordinates separate the two species at crown level as well
   as a multispectral payload does.
4. Stem diameter is measurable to about 1.3 cm RMSE from below and not at all from above.
5. Cross-instrument checks are not optional. The largest error found in this project was
   invisible within any single dataset.

# 8. Code and data

Code, notebooks, analysis scripts, figures and the plot polygon:
`github.com/jobelab/nova-course-2026`, GPL-3.0-or-later. The point clouds are excluded from
version control by design and their location and provenance are documented in the
repository instead.

The scripts run from the repository root and take the data paths from the environment, so
the analysis is portable to another machine that holds the same clouds. Two of the steps
will exhaust a 15 GB machine if written naively, and `scripts/project/README.md` says
which and why.
