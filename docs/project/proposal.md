% Individual project: research questions and methods
% José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
% NOVA 2026: Point cloud processing for forestry

# 1. Study site and plot

The study plot is plot 167 (TRAKT 167) at **Remningstorp**, a research forest estate in
Västergötland, Sweden, with a long record of field measurement. Its centre is at
**E 420407.631, N 6481815.136** in SWEREF99 TM (EPSG:3006), and the surveyed ground
elevation there is **137.642 m** in RH2000.

The plot is worth building a project on because of how much data covers it. The same
piece of forest has been flown four times by UAV, scanned from the ground and from the
air, and measured tree by tree in the field. That combination is unusual, and it is what
makes the comparisons in section 4 possible at all.

![**Figure 1.** Plot 167 in its stand, on the nadir RGB orthomosaic. The 20 m plot
boundary is yellow, and the five TLS and MLS scan positions are marked C, N, E, S and W.
The wider view is 260 m across and shows why a common footprint matters: the drone surveys
reach well beyond the stand, across roads and open ground the plot itself does not
contain.](figures/fig1_plot_context.png)



# 2. Data sources

## 2.1 UAV photogrammetry

A single archive (`Nadir_MS_orthomosaic.zip`) holds **eight products**, not one. They form
a **2 × 2 design** crossing flight geometry with camera. All were produced in **Agisoft
Metashape** and delivered in SWEREF99 TM with RH2000 heights (compound EPSG:5845).

| | RGB camera | multispectral camera |
|---|---|---|
| **nadir** (written 2026-08-17) | `Nadir_RGB_PointCloud.las` + orthomosaic | `Nadir_MS_PointCloud.las` + orthomosaic |
| **oblique** (written 2026-08-20) | `Oblique_RGB_PointCloud.las` + orthomosaic | `Oblique_MS_PointCloud.las` + orthomosaic |

| product | points | LAS format | channels |
|---|---:|---|---|
| `Nadir_RGB_PointCloud.las` | 46,347,917 | 1.4, fmt 2 | R, G, B |
| `Oblique_RGB_PointCloud.las` | 170,060,798 | 1.4, fmt 2 | R, G, B |
| `Nadir_MS_PointCloud.las` | 15,641,772 | 1.4, fmt 8 | 4 bands + NIR slot |
| `Oblique_MS_PointCloud.las` | 49,615,363 | 1.4, fmt 8 | 4 bands + NIR slot |

Those two dates are file-creation dates from the LAS headers, so they say when the
products were written, not when the aircraft flew. **The flight dates are not recorded
anywhere in the data**, and there is nothing left in the files to recover them from. The
headers, the archive and the orthomosaics have all been checked.

This matters, so I am asking about it directly in section 6. If nadir and oblique were
flown on different days, then sun angle and sky conditions differ between them, and a
difference between the two acquisitions cannot be attributed to view geometry. If they
were flown on the same day, that comparison becomes much stronger. The answer changes what
RQ1 and RQ2 can conclude, not merely how precisely they can be stated, and section 5.8
explains why.

Ground sampling distance is **3.14 cm** for the RGB orthomosaic (3 bands, 8-bit) and
**5.23 cm** for the multispectral one (4 bands, 16-bit). Every cloud carries colour and
per-point surface normals. None carries intensity, multiple returns, GPS time or
classification, which is the signature of photogrammetry rather than lidar: these are
single-return surface points. Usefully, the colour sits on the points themselves rather
than being draped from a raster, so it will survive filtering, normalisation and
segmentation untouched.

The multispectral products were flown with a **DJI Mavic 3 Multispectral**, which carries
four single-band cameras alongside a 20 MP RGB camera. Its bands are fixed by the
instrument:

| band | centre wavelength |
|---|---|
| green | 550 nm ± 16 nm |
| red | 650 nm ± 16 nm |
| red edge | 730 nm ± 16 nm |
| near infrared | 860 nm ± 26 nm |

**There is no blue band**, which rules out any index that needs one and makes red edge
available instead. That is a good trade for forestry, because NDVI saturates in dense
conifer canopy and NDRE does not.

None of this is recorded in the delivered files. The raster declares no colour
interpretation, and the LAS colour slots are named by the file format rather than by the
data in them, so the slot called blue is not blue. Tying the file channels to the four
bands above is therefore a preprocessing step in its own right, and section 5.2 describes
the check. It matters more than it sounds, because the raster and the point cloud do not
order the bands the same way.

Three things are missing: the individual images, the Metashape processing report, and the
flight logs. Without the images these products cannot be reprocessed from source, so the
project will treat them as primary data rather than as something that can be regenerated.
The rest of what is missing is listed in section 6.


![**Figure 2.** The four drone acquisitions seen from above, clipped to the plot. Every
point inside the boundary is drawn, coloured by the channels stored on it. The RGB clouds
are true colour. The multispectral clouds have no blue band, so they are rendered as false
colour from red, green and red edge. Crowns separate cleanly in the nadir views and blur
in the oblique ones.](figures/fig2_drone_from_above.png)

![**Figure 3.** The same four acquisitions in cross-section, a 6 m slab through the plot
centre. Heights are relative to the surveyed ground at the plot centre, 137.642 m in
RH2000. Every cloud is a shell over the canopy. Below roughly 15 m there is almost
nothing, and no ground surface at all. This is photogrammetry doing what it does: it
reconstructs the surface the cameras could see, and under a closed canopy that surface is
the canopy. It is also why the terrain model has to come from lidar, as section 5.5
explains. The scattered points near -3 m sit at about the height of the ALS ground return
in Figure 4, so they are most likely ground glimpsed through gaps rather than
error.](figures/fig3_drone_cross_sections.png)

## 2.2 Laser scanning over the same plot

| | instrument | points | delivered extent | Z |
|---|---|---:|---|---|
| TLS | Riegl VZ-400i | 290,336,075 | 30 × 30 m on plot centre | **normalised**, −2.47 to 27.85 m |
| MLS | Faro Orbis | 61,020,343 | 30 × 30 m on plot centre | absolute, 135.61 to 166.16 m |
| ULS / ALS | Riegl MiniVUX-1DL + VUX-1HA + VQ-840-G (helicopter) | 11,205,212 | 60 × 60 m on plot centre | absolute, 132.85 to 163.69 m |
| ALS | Remningstorp 2021 survey, plots 165 + 167 | 2 tiles, 6.8 GB | landscape | absolute |

Five further TLS clouds and five MLS subplots are also available at 15 m radius around
each of the five scan positions. All three plot 167 clouds are LAS point format 3 and
carry **plain intensity only**, with no extra dimensions. The Riegl `Amplitude`,
`Reflectance` and `Deviation` fields do exist in the course material, but on the day 1
exercise TLS cloud, which is a different site about 300 km further north, so they are not
available for this plot.

One detail shapes the methods. The TLS clouds sit correctly in plan, in SWEREF99 TM and
centred on the plot, but their **heights have already been normalised to ground zero**
instead of being referred to RH2000. So the work of putting them on the same footing as
the UAV and airborne data is vertical, not horizontal, and section 5.3 says how it will be
handled.


![**Figure 4.** The same slab recorded by the three laser scanners, shaded by intensity.
TLS and MLS see stems from the ground up, and the ground itself. The helicopter ALS sees
the canopy and the ground but almost no stem. Set against Figure 3, this is the argument
for using more than one sensor: stem attributes can only be measured from below, and
area-wide coverage only exists from above. The TLS and MLS panels stop at 15 m because
those clouds are delivered as a 30 by 30 m box.](figures/fig4_lidar_cross_sections.png)

## 2.3 Field reference

The field data for this plot includes plot polygons at 10 m and 20 m, POSTEX and
NFI-corrected tree lists, DBH for every tree, surveyed target positions
(`target_positions_167C.txt`) and a QGIS project. The tree list itself is
`treedataRemningstorp2011_final_only_within20m_trslg.txt`.

## 2.4 The clipping polygon

Clipping will use **`plot20mR`**, the 20 m circular plot polygon for TRAKT 167 from the
field GIS. There are other candidates: `plot10m` and `plot10mR` give 50 plots at 10 m, and
`PlotlistC` with `PlotlistC10m` gives the five scan positions at 10 m. The 20 m polygon is
the right one for three reasons.

1. Its attributes identify it as plot 167 and carry the surveyed centre and ground height.
2. The field tree list is defined on it, *only within 20 m*. Any other radius would break
   comparability with the measured stems, which is the whole point of having them.
3. It is the only plot layer with a `.prj` file, so its coordinate system is documented
   rather than guessed, and it matches the frame the UAV clouds are already in.

The polygon is a 20 m radius circle covering about 1256 m². All five TLS and MLS scan
positions fall inside it, the outermost sitting close to the rim at roughly 19.9 m from
the centre, so the ground sensors and the UAV acquisitions will share a single boundary.
It will be converted once with `ogr2ogr` and stored in the project repository as
`data/field/plot167_20m.geojson`, so the plot boundary stays versioned and readable.

# 3. Purpose

The processing will derive forest attributes, both canopy structure and canopy colour, at
plot and tree level from several different acquisitions of the same forest, and then ask
**how much of each attribute belongs to the forest and how much belongs to the way it was
measured**. The 2 × 2 UAV design allows flight geometry to be separated from band set, and
the laser scanning and field measurements give something to check the UAV products
against.

# 4. Research questions

**RQ1. Flight geometry.** Does the flight geometry of a UAV survey change the canopy
colour metrics derived from its point cloud, over a fixed forest plot?

  a. How do the nadir and oblique acquisitions differ once land cover is held constant by
     clipping both to the same plot polygon?
  b. Is any difference spread evenly across the colour channels, or carried by one or two
     of them?

**RQ2. Band set.** Does the choice of spectral bands decide how sensitive a greenness
index is to acquisition geometry?

  a. How does an RGB index behave compared with a multispectral one (G, R, red edge, NIR)
     over the same plot and the same flights?
  b. How do the UAV colour indices compare with what the laser scanners record over the
     same crowns? TLS, MLS and the helicopter ALS all carry intensity, and intensity
     depends on range and incidence angle much as passive colour depends on view and sun
     angle, so this sets two geometry-dependent radiometries against each other rather
     than testing one against a truth.

**RQ3. Calibration.** Can canopy greenness be derived from photogrammetric point clouds
that were never radiometrically calibrated?

  a. Are ratio-form indices, meaning chromatic coordinates and normalised differences,
     enough when absolute reflectance is not available?
  b. Does computing an index per point give the same answer as sampling it from the
     orthomosaic?

**RQ4. Reconstructed surface.** How does flight geometry affect which canopy surface gets
reconstructed in the first place, and do the structural attributes follow?

  a. Point density and how it is distributed vertically within the plot.
  b. Tree detection rate, tree height and crown area.

**RQ5. Validation.** What can a photogrammetric UAV cloud measure about forest structure,
compared with the co-located TLS, MLS and ALS, and against the field tree list?

  a. Where will UAV-derived and lidar-derived attributes agree? Photogrammetry only
     reconstructs the outer canopy envelope, so stem-based attributes such as DBH, taper
     and stem volume should be unavailable from the UAV clouds and measurable only from
     TLS and MLS. The interesting question is where that boundary actually falls, not
     whether it exists.
  b. Which acquisition should each attribute be taken from, and with what uncertainty?

# 5. Methods

## 5.1 Environment and reproducibility

Everything will run in Python 3.12 or later in a `uv`-locked environment, written as a
library called `novatrees` with **marimo notebooks** as the executable chapters. The
notebooks are plain `.py` files, so they diff and version-control like any other code, and
they export to HTML and PDF. That means the report and the presentation will come out of
the same runs that produce the numbers, rather than being assembled afterwards. The code
is GPL-3.0-or-later and lives at `github.com/jobelab/nova-course-2026`.

## 5.2 Data preparation

Clouds will be read in a streaming fashion. The largest is 170 million points, and every
summary statistic needed here is additive, so there is no reason to hold one in memory
whole.

Sorting out the band identity on the multispectral products comes before any index is
computed, and the result will be written down as an explicit mapping for the raster and
for the point cloud separately, rather than relying on the channel names. The camera fixes
the band order, but it does not follow that the delivered files preserve it, so the
mapping will be checked against the data rather than assumed from the instrument.

That check has to be **independent of per-band gain**, because the bands are uncalibrated
and their raw values therefore cannot be compared with each other directly. Correlation
meets that condition, since it is unaffected by any constant scaling of a band, and two
correlations will be used. The first compares within-pair band ratios against the
unambiguous RGB products, which identifies the visible bands. The second samples the
orthomosaic at the position of each point in the matching cloud and correlates the two,
which ties the channels of the two products to each other. Both are run on chromatic
coordinates rather than raw values, because otherwise shading dominates and no mapping
separates.

The Metashape project file is not among the delivered data, so the Metashape Python API
cannot be used to read the band configuration directly. These correlations are the
substitute, and they need only the products themselves. Where the data still cannot
separate a pair of bands, the camera's fixed band order decides it, and the report will
say which of the routes each part of the mapping rests on.

Reconstruction blunders will be found from the vertical distribution and removed before
any surface model is built. Clipping to the plot does throw out far-field outliers, but it
is not a filter and should not be mistaken for one, so a proper outlier pass stays in the
chain.

## 5.3 Plot definition, co-registration and clipping

Every acquisition will be clipped to the `plot20mR` polygon described in section 2.4,
using a point-in-polygon test with a bounding-box prefilter and a full winding test at the
boundary. The clipped files will keep their header, scale, offset, coordinate system,
colour and extra dimensions, so they stay comparable with the clouds they came from and
still open in CloudCompare.

The TLS clouds need one extra step. They are already correct in plan, so nothing has to
move horizontally, but their heights are normalised to ground zero and the constant used
is not recorded anywhere. It will be recovered by matching TLS ground returns to the
terrain model rather than guessed from the surveyed elevation at the plot centre, which
refers to a marked point and need not sit on the litter surface.

Vertical agreement between the laser scanning clouds will be checked before any of them is
used as a reference, not assumed. Two clouds can each be internally consistent, carry
plausible elevations, and still sit on different vertical datums, and nothing in a
photogrammetric cloud can reveal that, because it holds no ground of its own to disagree
with. Any offset found will be reported with the residual left after correcting it.

## 5.4 Colour indices

Per point, from the RGB clouds:

$$\mathrm{GCC}=\frac{G}{R+G+B},\qquad
  \mathrm{RCC}=\frac{R}{R+G+B},\qquad
  \mathrm{BCC}=\frac{B}{R+G+B}$$

and from the multispectral clouds, using the resolved band names:

$$\frac{G}{G+R+RE},\qquad
  \mathrm{NDVI}=\frac{NIR-R}{NIR+R},\qquad
  \mathrm{NDRE}=\frac{NIR-RE}{NIR+RE},\qquad
  \mathrm{GNDVI}=\frac{NIR-G}{NIR+G}$$

Chromatic coordinates will be the primary index. Because each is a ratio over the sum of
the bands, multiplying all the channels by some constant leaves it unchanged, which makes
it insensitive to exposure, gain and illumination scaling and therefore usable on
uncalibrated digital numbers. That answers RQ3a directly, and it is also why the spectral
work can begin without waiting for the processing report. Chromatic coordinates on the
multispectral band set will be reported by their denominator and never called GCC, since
GCC is defined over R+G+B and there is no blue band in that set. Points whose bands sum to
zero will come back as missing rather than zero, and will be counted.

One limit is worth stating in advance. A normalised difference built from uncalibrated
digital numbers is **not** comparable with published reflectance-based values, because the
band gains are unknown and unequal. Numbers of that kind are only good for ranking and for
comparing acquisitions within this dataset, and they will not be quoted as ecological
quantities.

## 5.5 Terrain, height normalisation and canopy model

A photogrammetric cloud only contains surfaces the cameras could see, and under a closed
canopy that does not include the ground. A DTM therefore cannot reliably be derived from
the UAV clouds themselves, and **UAV heights will be normalised against a lidar terrain
model instead**. The ALS gives the coverage, since it spans a wider area than the plot and
so has terrain at the plot edges, while the MLS gives the control, since a walked scanner
sees the forest floor directly and at close range. The terrain will be built from the ALS
and tied to MLS ground returns, with the residual reported.

This is not a refinement. Normalising SfM data to its own idea of ground in closed forest
pushes every height downward by however much canopy was mistaken for terrain, and the error
stays invisible unless something independent is there to catch it. The same applies to the
terrain itself: an uncorrected vertical offset in the reference cloud passes straight into
every tree height derived from it.

For the laser scanning data, ground points will be separated with a Cloth Simulation
Filter, cross-checked against a second CSF implementation, then a DTM interpolated and a
canopy height model built. Several DSM and CHM methods will be compared so that the choice
can be reported rather than assumed. Canopy height will be summarised with upper
percentiles rather than the maximum, which in a photogrammetric cloud is really an outlier
statistic.

## 5.6 Tree detection and crown segmentation

Three detection routes will be applied and compared, because the method that works best
changes with the sensor: local maxima with watershed on the CHM; a point-cloud detector
using cross-section stem seeds and geodesic label propagation; and a learned detector
(TreeAIBox / TreeisoNet). Detection will be scored against the field tree list.

## 5.7 Crown-level aggregation

The indices from section 5.4 will be aggregated per segmented crown, because the crown
rather than the whole cloud is the unit worth reporting, and joined to the field tree
list. The result will be one tree-level table carrying structure and colour from every
acquisition.

## 5.8 Analysis design

The comparisons follow the research questions directly. Nadir against oblique with the
band set held constant will answer RQ1; RGB against multispectral with the flight held
constant will answer RQ2; per point against orthomosaic-sampled will answer RQ3b; density,
height and crown metrics between flights will answer RQ4; and UAV against TLS, MLS, ALS
and the field tree list will answer RQ5. All of it will happen on the same clipped plot,
so land cover is held constant throughout.

There is one limitation to flag in advance. Three effects cannot be separated by the nadir
versus oblique contrast on its own, and all three will be carried as live explanations
rather than quietly settling on the one that is most interesting. They are **view
geometry**, which is the effect of interest; **illumination**, since the two acquisitions
may have been flown on different days and at different sun angles, as section 2.1
explains; and **radiometric processing**, since camera white balance and Metashape's
per-chunk colour adjustment are applied to each acquisition independently. Telling them
apart needs either the flight metadata or an invariant target visible in both scenes.
Without one of those, any difference will be reported as a difference between
*acquisitions*, not as an effect of view angle.

# 6. Questions for the course teachers

Some information is simply not in the data, and no amount of further processing will
recover it. Rather than guess, I am asking for it here, in the order it matters to the
project.

**1. When were the two UAV flights flown?** This is the one I would most like answered.
The files give 2026-08-17 for the nadir products and 2026-08-20 for the oblique ones, but
those are the dates the products were written in Metashape, not flight dates. Knowing
whether the two surveys were flown on the same day, and roughly at what time, decides
whether a nadir-to-oblique difference can be read as a view-geometry effect or has to stay
confounded with illumination.

**2. Is the multispectral orthomosaic raw digital numbers or calibrated reflectance?**
Was a reflectance panel or the drone's downwelling light sensor used in processing? The
files are 16-bit either way, so they cannot answer this on their own. Without an answer,
only ratio-form indices are safe to use, which is the route the project takes anyway, but
knowing would allow absolute values to be reported as well.

**3. What were the flight parameters?** Flight height, overlap, and the camera tilt angle
used for the oblique missions.

**4. How were the flights georeferenced?** RTK, PPK or ground control points, and the
reported horizontal and vertical accuracy. This decides how much of any offset between the
UAV and the laser scanning is registration rather than method.

**5. Is the Metashape processing report available?** Alignment accuracy, dense cloud
quality and depth filtering settings, and in particular whether the multispectral and RGB
chunks share one alignment or were aligned independently.

The flight dates matter most. The rest can be worked around, and the project is sequenced
so that a late answer costs one chapter rather than the whole thing.

# 7. Deliverables

1. This document, covering the data, the research questions and the methods.
2. A set of marimo notebooks, one per processing stage, each exportable to HTML or PDF.
3. The `novatrees` library and command-line tool implementing the methods.
4. A written report.
5. A 20-minute oral presentation.
