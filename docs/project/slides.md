::: {.title}
# How much of a forest measurement belongs to the forest?

<p class="lead">One plot. Seven point clouds. Seventy-four surveyed stems.</p>

<p class="sub">José M. Beltrán-Abaunza &nbsp;·&nbsp; jose.beltran@mgeo.lu.se &nbsp;·&nbsp; Lund University<br>
NOVA 2026, Point cloud processing for forestry &nbsp;·&nbsp; individual project</p>
:::

## The question

<p class="lead">Every forest attribute we derive is a measurement of two things at once: the forest, and the instrument that looked at it.</p>

- Plot 167 at Remningstorp is covered by **four drone acquisitions**, nadir and oblique, RGB and multispectral
- Plus **TLS, MLS and helicopter ALS** over the same trees
- Plus **74 stems surveyed in the field**, with diameter and species

**So for once we can ask which is which.**

<p class="sub">And the answer turns out to depend entirely on which attribute you mean.</p>

## One plot, seven acquisitions

![](figures/fig1_plot_context.png)

## Photogrammetry sees the canopy and nothing under it

![](figures/fig3_drone_cross_sections.png)

## The lasers see what the drone cannot

![](figures/fig4_lidar_cross_sections.png)

## The same stand, four different forests

![](figures/fig5_vertical_profiles.png)

<p class="sub">Median return height: 1.29 m from TLS, 5.94 m from MLS, 17.50 m from ALS, about 20 m from every drone cloud.</p>

## The error nothing in the drone data could reveal

<div class="two">
<div>

### ALS terrain against MLS ground control

| | median | RMSE |
|---|---:|---:|
| before | +2.089 m | 2.100 m |
| after one constant | +0.000 m | **0.079 m** |

<p class="sub">513,390 control points. p05 to p95 spans 0.25 m before correction, so it is a shift, not scatter.</p>

</div>
<div>

<p class="big">2.089 m</p>

Every drone-derived tree height would have been that much **too tall**.

The drone clouds hold **no ground of their own** to disagree with.

**Cross-instrument checks are not optional.**

</div>
</div>

## Flight geometry changes an index on the same tree

<div class="two">
<div>

Comparing plot means confounds the acquisition with **which surfaces it sampled**.

Pairing the **same crown** between acquisitions removes that.

| pair | crowns | nadir minus oblique |
|---|---:|---:|
| RGB | 48 | **+0.0106** [+0.0073, +0.0147] |
| multispectral | 42 | **-0.0051** [-0.0067, -0.0032] |

</div>
<div>

### What moves and what does not

- **Canopy height: +0.10 m** on 22 m trees. It transfers.
- **Crown area: oblique is a third larger**, 22.0 against 16.7 m²
- The multispectral set has **no blue band** and barely moves

<p class="sub">Land cover was eliminated by clipping. View geometry, illumination and per-flight processing remain confounded, because the flight dates are not in the data.</p>

</div>
</div>

## Detection: nadir wins, and the method must match the sensor

<div class="two">
<div>

| cloud | F1 |
|---|---:|
| Nadir RGB | **0.815** |
| Oblique RGB | 0.780 |
| ALS helicopter | 0.794 |
| TLS, canopy height model | 0.566 |
| **TLS, stem cross-section** | **0.800** |

</div>
<div>

### Two results worth pausing on

- **Oblique carries 26 to 45 % more points and finds fewer trees.** Off-nadir smears the crown apex. *More points are not more information.*
- **The same TLS cloud scores 0.566 or 0.800** depending only on the method. A canopy height model throws away everything a ground scanner is good at.

</div>
</div>

## Recall is limited by tree size, not by sensor

![](figures/fig6_detection_by_dbh.png)

<p class="sub">A recall of 0.72 is not missing a quarter of the forest. It is finding almost every canopy tree and none of the suppressed ones. Size-dependent under-count for stem number; near complete for dominant height.</p>

## Colour separates the two species

![](figures/fig7_species.png)

<p class="sub">AUC in the middle DBH quartiles, so size is controlled: GCC 0.954 and 0.981, multispectral NDVI 0.897 and NDRE 0.989. An uncalibrated 20 MP RGB camera matches the four-band payload.</p>

## Diameter only from below, and the offset is the forest growing

![](figures/fig8_dbh_and_form.png)

<p class="sub">TLS diameter against a contemporaneous list: bias -1.26 cm, RMSE 1.30 cm. Against the 2011 survey the bias is +3.65 cm, and median plot DBH grew 5.5 cm in those fifteen years. Form factor 0.454, in the boreal band, but it rises with how much of the tree was reconstructed.</p>

## The fusion argument I expected, tested and lost

<div class="two">
<div>

**The claim:** stem volume needs both viewpoints. Diameter only from below, treetop only from above.

**The test:** reconstruct the same 21 stems with and without the drone height.

| | with drone | without |
|---|---:|---:|
| measured volume | 0.847 m³ | 0.847 m³ |
| form factor | 0.462 | 0.452 |

</div>
<div>

### Why it failed

The TLS already reconstructs **86 %** of these trees, so its own upper extent is a fine proxy for the top.

### What the drone does contribute

**Coverage.** TLS and MLS cover 900 m² of a 1256 m² plot. **28 % of the plot has no ground-based data at all.**

<p class="sub">That is an argument about where the instrument was, not about what it could see from there.</p>

</div>
</div>

## What I would tell a forest inventory

<div class="two">
<div>

| attribute | from above | from below |
|---|---|---|
| detection | 0.815 | 0.800 |
| canopy height | yes | poorly |
| crown area | yes | no |
| **stem diameter** | **no** | **1.3 cm** |

</div>
<div>

1. **Canopy height is robust. Crown area, detection and colour are not.**
2. **Detection bias is size-dependent**, so stem counts need correcting and dominant height does not.
3. **Uncalibrated RGB matches multispectral** for separating these two species.
4. **The largest error I found was invisible inside any single dataset.**

</div>
</div>

## Honest limits, and one open question

<div class="two">
<div>

### Limits

- Field reference is **2011**, scans are 2021 onwards
- Detection tuned on the reference it is scored against
- Species: **two species, one plot, ~50 crowns**, spruce the minority
- Stem volume has **no field reference at all**

</div>
<div>

### The open question

**When were the two drone flights flown?**

The file dates are when Metashape wrote the products. The flight dates are not in the data.

If nadir and oblique flew on **different days**, then illumination differs and the geometry result stays confounded. If the **same day**, it becomes a clean result.

<p class="sub">Code, notebooks and figures: github.com/jobelab/nova-course-2026 &nbsp;·&nbsp; GPL-3.0-or-later</p>

</div>
</div>
