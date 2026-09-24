% What a drone point cloud can measure on a forest plot
% José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
% NOVA 2026 individual project: point cloud processing for forestry

# Summary

I compared seven point clouds of one 20 m forest plot at Remningstorp: four from a drone
(nadir and oblique flights, each with an RGB and a multispectral camera) and three from
laser scanners (terrestrial, mobile and helicopter). Seventy-four stems on the plot have
been surveyed in the field.

Following the course teachers' advice, this report covers the two point cloud questions
of my proposal. RQ4 asks how flight geometry changes the reconstructed canopy. RQ5 asks
what a drone cloud can measure compared with laser scanning and the field data. The three
spectral questions (RQ1 to RQ3) are left out.

My main results:

- Flight geometry changes the crowns but not the heights. Oblique flights give 26 to 45 %
  more points, crowns about a third larger, and fewer detected trees. Canopy height
  changes by only 0.1 to 0.2 m.
- The drone sees only the top of the canopy. It matches the helicopter lidar on canopy
  height (p95 23.6 to 23.8 m against 23.77 m) and on tree detection (F1 0.815 against
  0.794), but it sees no ground and no stems.
- Stem diameter can only be measured from below, to 1.3 cm RMSE with TLS.
- The largest error I found was a 2.089 m vertical offset between the helicopter lidar
  and the mobile scanner. It would have made every drone tree height 2.089 m too tall, and
  nothing in the drone data could have shown it.

# 1. Questions

**RQ4.** How does flight geometry affect which canopy surface is reconstructed, and do
structural attributes follow?

**RQ5.** What can a photogrammetric cloud measure compared with co-located laser scanning
and the field tree list?

# 2. Data

The study plot is plot 167 at Remningstorp, Västergötland, Sweden, centred at
E 420407.631, N 6481815.136 (SWEREF99 TM), with a ground elevation of 137.642 m (RH2000).

![**Figure 1.** Plot 167 on the nadir RGB orthomosaic. The 20 m plot boundary is yellow and the five TLS and MLS scan positions are marked.](figures/fig1_plot_context.png)

| cloud | instrument | points (whole delivery) |
|---|---|---:|
| `Nadir_RGB` | DJI Mavic 3 Multispectral, RGB camera | 46,347,917 |
| `Oblique_RGB` | same, RGB camera | 170,060,798 |
| `Nadir_MS` | same, multispectral camera | 15,641,772 |
| `Oblique_MS` | same, multispectral camera | 49,615,363 |
| TLS | Riegl VZ-400i | 290,336,075 |
| MLS | Faro Orbis | 61,020,343 |
| ALS | helicopter, Riegl MiniVUX-1DL + VUX-1HA + VQ-840-G | 11,205,212 |

The drone clouds were produced in Agisoft Metashape. The flight dates are not in the data.
I assume the nadir and oblique flights were flown on the same day or at most one day
apart, so the trees and the season are the same in both. TLS and MLS were delivered as a 30 by 30 m
box, which covers only 72 % of the plot, so 24 of the 74 field stems have no ground-based
data. I score those two scanners only inside their box.

The field reference is 74 stems surveyed in 2011 (45 Scots pine and 29 Norway spruce, DBH
15.0 to 36.4 cm, mean spacing 4.12 m).

# 3. Methods

I did all processing in Python with my own library (`novatrees`). Every number in this
report comes from the scripts in the repository.

- **Clipping.** I clipped every cloud to the 20 m plot polygon that the field list is
  defined on.
- **Terrain.** The drone clouds contain no ground, so I built the DTM from the ALS ground
  returns and checked it against MLS ground points.
- **Tree detection.** I found treetops with a marker-controlled watershed on a canopy
  height model and matched them one to one with the field stems within 2.0 m. For TLS and
  MLS I also detected stems directly from a breast-height slice.
- **Stems.** I fitted circles to the breast-height slices with RANSAC and kept only stems
  with enough arc coverage and vertical continuity. I then followed each stem upward to
  get its taper and volume.

# 4. Results

## 4.1 The drone sees only the top of the canopy (RQ4, RQ5)

![**Figure 2.** The four drone clouds from above, clipped to the plot. Crowns are sharp in nadir and blurred in oblique.](figures/fig2_drone_from_above.png)

![**Figure 3.** A 6 m slice through the plot centre in the four drone clouds. Each cloud is a shell over the canopy, with almost nothing below 15 m and no ground.](figures/fig3_drone_cross_sections.png)

![**Figure 4.** The same slice in the three laser clouds. TLS and MLS see stems and ground; the helicopter sees canopy and ground but hardly any stem. TLS and MLS stop at 15 m because they were delivered as a 30 by 30 m box.](figures/fig4_lidar_cross_sections.png)

![**Figure 5.** Height of the returns above the terrain model for each cloud.](figures/fig5_vertical_profiles.png)

| cloud | median height (m) | p95 (m) | below 0.5 m |
|---|---:|---:|---:|
| `Nadir_RGB` | 20.07 | 23.76 | 4.8 % |
| `Oblique_RGB` | 19.87 | 23.68 | 6.1 % |
| `Nadir_MS` | 20.15 | 23.61 | 1.1 % |
| `Oblique_MS` | 20.24 | 23.83 | 2.4 % |
| TLS | 1.29 | 20.08 | 47.3 % |
| MLS | 5.94 | 20.85 | 28.3 % |
| ALS | 17.50 | 23.77 | 25.8 % |

The drone clouds put their median at about 20 m, the TLS at 1.3 m. The drone only
reconstructs surfaces the camera saw, and under a closed canopy that excludes the ground
and the stems. On the upper canopy the drone matches the helicopter lidar: p95 is 23.6 to
23.8 m for every drone cloud against 23.77 m for the ALS.

## 4.2 A vertical offset only a second instrument could find (RQ5)

Because the drone clouds have no ground, their heights depend on a lidar terrain model.
When I checked the ALS terrain against 513,390 MLS ground points, I found a constant
offset:

| MLS ground minus ALS terrain | median | RMSE |
|---|---:|---:|
| before correction | +2.089 m | 2.100 m |
| after one constant offset | +0.000 m | 0.079 m |

The ALS terrain had the right shape but the wrong datum. Without this check every drone
tree height would have been 2.089 m too tall. The same check showed that the TLS heights
had been normalised with 138.124 m, not the surveyed plot elevation of 137.642 m.

## 4.3 Flight geometry changes crowns, not heights (RQ4)

I paired the same crowns between the nadir and oblique clouds:

| pair | crowns | h95, nadir minus oblique | crown area, nadir minus oblique |
|---|---:|---:|---:|
| RGB | 48 | +0.10 m | -1.8 m² |
| multispectral | 42 | -0.16 m | -2.0 m² |

Clipped to the plot, the oblique clouds have more points than the nadir ones: 1,079,832
against 745,114 for RGB (+45 %) and 372,359 against 295,497 for multispectral (+26 %).

Tree height changes by 0.1 to 0.2 m on 22 m trees, so it transfers between flight
geometries. Crown area does not: oblique crowns are about a third larger (median 22.0
against 16.7 m²), because the side views widen and blur the crown edge.

## 4.4 Tree detection (RQ4, RQ5)

| cloud | tops | recall | precision | F1 |
|---|---:|---:|---:|---:|
| `Nadir_RGB` | 56 | 0.716 | 0.946 | **0.815** |
| `Oblique_RGB` | 49 | 0.649 | 0.980 | 0.780 |
| `Nadir_MS` | 53 | 0.662 | 0.925 | 0.772 |
| `Oblique_MS` | 46 | 0.608 | 0.978 | 0.750 |
| ALS | 52 | 0.676 | 0.962 | 0.794 |
| TLS, canopy height model | 32 | 0.405 | 0.938 | 0.566 |
| TLS, stem slice | 35 | 0.680 | 0.971 | **0.800** |
| MLS, stem slice | 33 | 0.660 | 1.000 | 0.795 |

Nadir beats oblique with both cameras, even though oblique has 26 to 45 % more points. The
larger, blurred oblique crowns merge neighbouring trees. The drone does as well as the
helicopter lidar.

For TLS the method matters more than the sensor: the same cloud gives F1 0.566 from a
canopy height model and 0.800 from a stem slice.

![**Figure 6.** Detection rate by field DBH quartile.](figures/fig6_detection_by_dbh.png)

Precision is above 0.92 everywhere, so the limit is recall. Figure 6 shows why: almost all
large trees are found, and about two thirds of the smallest are missed. These are
suppressed trees under the canopy. So stem counts are underestimated, while dominant
height is nearly complete.

## 4.5 Stems and volume (RQ5)

The drone cannot measure stem diameter at all, because it never sees a stem. From below
it works well:

| cloud | reference | n | bias | RMSE |
|---|---|---:|---:|---:|
| TLS | 2011 field survey | 34 | +3.65 cm | 3.93 cm |
| TLS | contemporaneous tree list | 35 | -1.26 cm | 1.30 cm |
| MLS | contemporaneous tree list | 33 | -0.14 cm | 0.34 cm |

![**Figure 7.** Left: TLS stem diameter against the 2011 survey and the contemporaneous list. Right: form factor against the fraction of tree height reconstructed.](figures/fig8_dbh_and_form.png)

The bias against the 2011 survey is mostly growth: median DBH was 25.8 cm in 2011 and is
31.3 cm now. The contemporaneous list was probably derived from the same laser data, so
I read that agreement as a check of my code, not as a validation.

I expected that stem volume would need both views: diameter from below and the treetop
from the drone. It did not. For 21 stems, adding the drone tree height left the volume
unchanged (0.847 m³) and moved the form factor only from 0.452 to 0.462, because the TLS
already reconstructs 86 % of these trees. What the drone adds is coverage: it sees the
whole plot, including the 28 % that TLS and MLS did not cover.

# 5. Discussion

**RQ4.** Flight geometry changes the reconstructed canopy but not all attributes equally.
Height transfers between nadir and oblique. Crown area and detection do not: oblique gives
more points, bigger and blurrier crowns, and fewer trees. More points did not mean more
information.

**RQ5.** What each instrument can measure depends on its line of sight:

| attribute | drone (from above) | TLS / MLS (from below) |
|---|---|---|
| tree detection | F1 0.815 | F1 0.800 / 0.795 |
| canopy height | same as ALS (p95 within 0.2 m) | underestimated |
| crown area | yes, but depends on flight | no |
| stem diameter | no | RMSE 1.3 cm |
| ground | no, needs lidar | yes |

**Checks between instruments are necessary.** The 2.089 m offset was invisible inside any
single dataset.

# 6. Limitations

The field survey is from 2011 and the scans are later, so some misses may be trees that
died in between. I tuned detection against the same reference I score it on. Stem volume
has no field reference. I assume the two drone flights were at most one day
apart. The differences between them are then mainly view geometry, although light
conditions and the Metashape processing could still differ between flights.

# 7. Conclusions

1. Canopy height from a drone is robust to flight geometry and matches helicopter lidar.
2. Crown area and tree detection depend on flight geometry; nadir works better.
3. A drone cloud cannot measure ground or stem diameter; TLS gives diameter to 1.3 cm.
4. Detection misses small suppressed trees whatever the sensor.
5. Heights from a drone need an independent terrain check; here it removed a 2.089 m
   error.

# 8. Code and data

Code, notebooks, scripts and figures: `github.com/jobelab/nova-course-2026`
(GPL-3.0-or-later). The point clouds are not in version control; their location and
provenance are documented in the repository.
