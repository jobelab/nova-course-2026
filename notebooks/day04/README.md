# Day 4: ALS, MLS and TLS over plot 167

The same plot from three platforms, ending in one table: ground-derived stem volume
beside airborne metrics.

## The exercise

1. Preprocess high density ALS over plot 167
2. Run tree detection and segmentation on the ALS
3. Extract metrics from the ALS
4. Detect trees in TLS and MLS over the same area
5. Estimate stem volume for every detected tree
6. Match ALS and ground-based tree positions

Objective: a data frame with TLS/MLS-derived stem volume beside ALS-derived metrics.
The regression that would upscale volume across the wider ALS coverage is separate
work and is deliberately not fitted here.

Step 5 turned out to be the one with a trap in it, and it has its own section below:
**the taper integral is not a stem volume**, so the table carries three volume columns
per tree rather than one.

## Notebook

| notebook | what it covers |
| --- | --- |
| [`00_multisensor_inventory.py`](00_multisensor_inventory.py) | the exercise: all six steps, with both the heuristic and the learned detector |
| [`01_upscaling_regression.py`](01_upscaling_regression.py) | **not part of the exercise**: the extra step of fitting a volume model and applying it to the whole ALS footprint. See the appendix at the end of this file |

Both end with a **Results as measured** section carrying the numbers from the recorded
run, so they can be read without executing anything.

![semantic segmentation, three sensors](../../docs/figures/day04_semantic_segmentation.png)

**Semantic segmentation, side by side.** Between steps 4 and 5 the notebook classifies
every point as ground, stem or foliage and draws the three sensors against each other:
a cross-section over the same 30 m of ground, and the stem class from above. The ALS
panel has no stem class in it, because a helicopter never records bark, and what it
offers instead is a canopy apex twenty metres above the stem. That single figure is the
argument for the whole exercise.

## Data

| | ALS helicopter | MLS | TLS |
| --- | ---: | ---: | ---: |
| points | 11,205,212 | 61,020,343 | 290,336,075 |
| plot radius | 30 m | 15 m | 15 m |
| density | ~3,000 /m2 | ~68,000 /m2 | ~323,000 /m2 |
| Z datum | absolute | absolute | **not georeferenced** |
| stems visible | no | yes | yes, richly |

Reference: Hyyppä et al. (2020), *Under-canopy UAV laser scanning for accurate forest
field measurements*, <https://doi.org/10.1016/j.isprsjprs.2020.03.021>

## Four things this data forces

**The method has to change with the sensor.** ALS switches to CHM watershed, because a
helicopter cannot see a stem under closed canopy and cross-section seeding has nothing
to cluster. On the Day 3 TLS plot the ranking was the exact reverse, watershed at
recall 0.15 against 0.68. Neither method is better in general; they answer to
different data. `novatrees.presets` encodes that, and the important line in it is
`ALS.seed_method = "chm"`.

**The TLS is not georeferenced in Z.** Its heights read -2.5 to 27.9 m while the other
two sit at 135 to 166 m. Normalised height is the only datum the three share, so
normalisation is a correctness requirement here rather than a convenience.

**All three are circular cookie cuts** on a common centre. The cutter slices through
whatever crowns and stems straddle the boundary, so edge trees are measured from a
fraction of themselves and their volume is biased low irreversibly. They are flagged,
not corrected: correcting would mean assuming a shape.

**Position means different things to each sensor.** The ground locates a tree by its
stem base, the air by its canopy apex. On leaning or asymmetric trees those differ by
metres, and that offset is a real property of the measurement, not an error to tune
away.

## Reading the tree counts

Heuristic detector, 8 M points per cloud:

| | points read | trees | on edge | time |
| --- | ---: | ---: | ---: | ---: |
| ALS | 2.8 M | 92 | 15 | 22 s |
| MLS | 7.6 M | 38 | 7 | 50 s |
| TLS | 7.8 M | 48 | 9 | 66 s |

The two ground sensors agreeing at 38 and 48 while ALS reports 92 is the expected
shape. ALS is fragmenting crowns, not finding trees the ground missed, since a
helicopter cannot see a stem the scanner was standing beside.

Learned detector, same clouds: MLS 39 trees in 1,324 s, TLS 35 in 4,894 s. It finds
the same number of trees as the heuristic on MLS and fewer on TLS, at roughly thirty
and seventy times the cost, all on CPU. Fewer of them survive to a volume, 23 against
38 and 42, because its stem masks are thinner.

**Twenty-six of those 92 are debris**, not suppressed trees: slivers of a few
returns caught between two watershed basins. They matter because they are
*positions*, and a sliver near a real stem wins the nearest-neighbour match and
brings a nonsense height with it. `novatrees.drop_fragments` removes them, which
took the matched height RMSE from 10.88 m to 2.09 m. The thresholds are loose on
purpose: every combination from 5,000 to 30,000 points, 5 to 15 m and 5 to 20 m2
returns the same twelve matched trees, so they cut debris rather than select trees.

Both ground sensors are carried through to volume rather than one, because where TLS
and MLS disagree that disagreement is the honest error bar on the whole exercise. Two
independent instruments agreeing is worth more than either one's internal fit
statistics.

## Step 5 in detail: a taper integral is not a stem volume

![the three volume answers](../../docs/figures/day04_volume_variants.png)

The volume in the first version of this table was wrong, and the error is worth
keeping on the page because it is invisible in the formula.

$$V = \int_{z_0}^{z_1} \pi \left( d(z)/2 \right)^2 dz$$

$z_0$ and $z_1$ are the first and last **accepted** slice. Returns per stem thin with
height until slices fall below the minimum point count and the chain stops, usually
in the lower canopy. On MLS the strict PCT thresholds reach a median of 30 per cent
of tree height, so what was reported as stem volume was the volume of the lower
third of the stem.

**The check that catches it costs nothing.** Divide by the cylinder that DBH and
height give, $f = V / \pi (D_{1.3}/2)^2 H$. A boreal conifer stem holds $f = 0.45$ to
$0.50$. The original column sat at 0.24.

`novatrees.taper.volume_variants` now reports all three answers per tree. MLS with
the heuristic detector, 38 trees, medians:

| | volume | cover | form factor | what it claims |
| --- | ---: | ---: | ---: | --- |
| measured, strict (PCT thresholds) | 0.407 m3 | 0.30 | 0.24 | the lower third of the stem, measured |
| measured, relaxed thresholds | 0.772 m3 | 0.75 | 0.44 | three quarters of the stem, measured, noisier |
| Kozak model, integrated $0$ to $H$ | 0.981 m3 | 1.00 | **0.49** | the whole stem, extrapolated above the slices |
| cylinder $\pi (D_{1.3}/2)^2 H$ | 1.769 m3 | | 1.00 | the bound no stem reaches |

The model column covers 26 of the 38 trees. The other twelve had fits that did not
close at the tip and were refused rather than clamped, which is the subject of the
stem-profile figure above.

Median DBH 0.300 m, median height 25.2 m.

**All four runs say the same thing**, which is the part that makes it believable.
Two sensors, two detectors, medians (and it holds on a second stand as well, see
[Day 3](../day03/README.md#the-second-plot-for-the-taper-work)):

| run | trees | strict | cover | f | relaxed | cover | f | model | f | model usable |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MLS heuristic | 38 | 0.407 | 0.30 | 0.24 | 0.772 | 0.75 | 0.44 | 0.981 | **0.49** | 26/38 |
| TLS heuristic | 42 | 0.308 | 0.35 | 0.27 | 0.643 | 0.73 | 0.46 | 0.763 | **0.51** | 30/42 |
| MLS learned | 23 | 0.139 | 0.17 | 0.18 | 0.522 | 0.74 | 0.47 | 0.826 | **0.51** | 11/23 |
| TLS learned | 23 | 0.176 | 0.27 | 0.22 | 0.532 | 0.70 | 0.45 | 0.695 | **0.53** | 18/23 |

The strict column varies by a factor of three across runs because it is measuring
different amounts of stem, not different trees. The relaxed column collapses that
spread to 0.44 to 0.47, and the model column to **0.49 to 0.53**. Four runs that
disagree on the raw number and agree on the ratio is exactly what a coverage artefact
looks like once it is corrected.

**The last column is the price.** Only 26 of 38 trees get a model volume on MLS, and
11 of 23 on MLS learned. A fitted taper that does not close at the tip is refused
rather than clamped flat, so fewer trees carry a whole-stem estimate and the ones that
do are defensible. An earlier version clamped instead and reported 38 of 38, with the
MLS learned form factor at 0.60 rather than 0.51. The extra twelve trees were
cylinders running to the treetop.

Read the three rows as one argument. Loosening the thresholds is not a fudge: cover
goes from 0.30 to 0.75 and the form factor moves from 0.24 to 0.44, which is measured
stem that the strict settings refused to integrate rather than volume invented by the
parameters. The model then adds the part above the highest usable slice and lands at
0.50, exactly where forestry says a boreal conifer belongs. Three independent routes
converging on the same place is the reason to believe the last one.

**What each is for.** The strict column is what the scanner saw and is the one to
quote when the question is measurement. The model column is the one to carry into a
regression against ALS metrics, because ALS crown metrics respond to the whole tree.
The relaxed column is the bridge that shows the other two are consistent.

![stem profile with the fitted taper](../../docs/figures/day04_taper_profile.png)

The stem profile is where the three columns become one picture. Grey circles are the
cross-sections accepted at PCT's thresholds, blue triangles the relaxed ones, the
solid line is the Kozak function fitted through them, and the dashed line is where it
is extrapolating above the last usable slice. Shaded area is stem that was never
measured.

**The third panel is a fit being refused.** Its curve does not close at the tip: the
predicted diameter at the top is 0.998 of the diameter at the last measurement, so
the model would have run a 0.16 m cylinder from 18.6 m to the tree top and charged
the volume for it. Its form factor came out at 0.60 where its neighbours hold 0.44 to
0.48. Clamping such a fit to be non-increasing does not repair it, it disguises it,
so the volume is refused instead. The two tests are that the curve must close,
$d(0.999H) \le 0.5\,d(z_1)$, and must not widen with height.

### The numbers behind the numbers

Nothing here used half-metre sections. Every reported volume came from these:

| | strict | relaxed | 3DFin |
| --- | ---: | ---: | ---: |
| slice thickness | 0.10 m | 0.20 m | 0.05 m |
| **step between cross-sections** | **0.08 m** | **0.20 m** | **0.20 m** |
| minimum points per slice | 100 | 15 | n/a |
| RANSAC distance threshold | 0.04 m | 0.06 m | 0.02 m |
| radius tolerance between slices | 0.03 m | 0.09 m | n/a |
| centre tolerance | 0.06 m | 0.15 m | n/a |
| RANSAC iterations | 2000 | 2000 | n/a |
| diameter accepted | 0.02 to 3.0 m | 0.02 to 3.0 m | 0.06 to 1.0 m |

The strict column is PCT's Phase 5 as taught: cross-sections every 8 cm through a
10 cm slab, so consecutive slabs overlap. `presets.ALS.taper` does carry a 0.50 m
step, but `run_sensor` never consumes it, so no result here used it.

**DBH is not a slice.** It is the fitted Kozak curve evaluated at exactly 1.3 m, so it
does not depend on a slice landing at breast height. Without a fitted model it falls
back to interpolating the smoothed curve there. 3DFin instead has `tree_locator` pick
the best-quality section near breast height, which is one reason the two disagree
tree by tree.

The relaxed settings are `TaperParams.relaxed()`: slices twice as thick, steps two
and a half times longer, the minimum point count cut to 15 per cent, and the
between-slice tolerances widened. The defaults they replace are PCT's, and PCT is a
TLS tool: 100 points in a 0.10 m slice is easy at 323,000 points per square metre and
impossible on MLS returns eight metres up.

**The model is refused rather than trusted blindly.** Kozak's exponent carries a log
term, so extrapolating below the lowest slice can run the predicted diameter away by
orders of magnitude. The fit is extrapolated upward only, capped at two and a half
times DBH, forced not to widen with height, and discarded outright when the cap binds
on more than a tenth of the profile. Below the lowest slice the volume is a cylinder
at the last measured diameter, which understates butt swell slightly and cannot
explode.

## Step 6 and the objective: the joined table

![the objective, twelve matched trees](../../docs/figures/day04_objective.png)

`out/day04/FINAL_joined_MLS_ALSfiltered.csv`, twelve trees matched between the MLS
heuristic run and the fragment-filtered ALS, median position offset 0.53 m:

| ground | air |
| --- | --- |
| tree id, stem x and y | matched ALS tree id, apex x and y |
| total height | h_max, h_p99, h_p95, h_p75, h_p50, h_p25, h_mean, h_std |
| DBH, strict and relaxed | crown area, crown volume, crown base |
| **three volumes**, each with cover and form factor | fraction of returns above mean height, point count |
| | distance to plot edge, edge flag, match distance |

Every volume variant is kept in the row rather than one being chosen, so anything
fitted on this table has to declare which it used.

**How the four runs match:**

| run | matched | median offset | height RMSE against ALS |
| --- | ---: | ---: | ---: |
| MLS heuristic | 12 | 0.53 m | **1.31 m** |
| TLS heuristic | 12 | 0.59 m | 6.34 m |
| MLS learned | 7 | 0.57 m | 1.51 m |
| TLS learned | 8 | 2.34 m | 2.41 m |

TLS heuristic matches as many trees as MLS and then disagrees with the air about their
height by 6.34 m. That is the occlusion signature: a tripod sees the lower stem in
detail and loses the top of the crown behind everything in front of it, so its tree
tops are too low. MLS, walking through the plot, sees the same crown from several
sides. **Density is not the same as coverage,** and TLS has four times the density of
MLS here.

### The volume that is more complete correlates better

Correlation with ALS metrics across the twelve matched trees, one column per volume
variant:

| ALS metric | strict (n=12) | relaxed (n=12) | model (n=10) |
| --- | ---: | ---: | ---: |
| h_max | +0.590 | +0.752 | **+0.822** |
| h_p99 | +0.495 | +0.676 | **+0.763** |
| crown volume | +0.680 | +0.724 | +0.689 |
| crown area | +0.625 | +0.649 | +0.565 |

The model column covers ten of the twelve trees; the other two had their fits refused.
Refusing them **raised** the height correlation, from +0.791 to +0.822, which is a
second independent argument that the refusal is right: the ALS knows nothing about the
taper, so a rule that improves the agreement is removing noise rather than data.

This is worth more than it looks. Nothing in the taper reconstruction knows about the
ALS, so the ALS correlations are an independent test of which column is closest to the
truth. Against the height metrics the ordering is unambiguous and in the expected
direction: a helicopter measures the top of the tree, so a volume that includes the
upper stem should track it better than one that stops a third of the way up, and it
does, +0.59 to +0.79.

Against crown metrics the three are indistinguishable, which is also expected, since
crown size responds to competition and growing space rather than to the length of the
stem underneath it.

The form factors of these twelve trees fall between 0.436 and 0.526, median 0.49.

**This is where the exercise stops.** Fitting the regression that would upscale volume
across the wider ALS coverage is the next step and is deliberately not done here:
twelve trees from one plot would produce a demonstration, not a model.

## Against the earlier course pipeline

The exercises from the earlier sessions of this course are the organisers' material,
written in R against `lidR`: `Lecture2_Exercise_SurfaceModels.Rmd` for ground, DTM and
CHM, and `Session3_Exercise_Segmentation.Rmd` for detection and crowns. `pcf` is my own
Python mirror of that pipeline, written for those sessions and reused here rather than
rewritten. The algorithms in it belong to their authors: Dalponte and Coomes 2016 for
the crowns used on the ALS, Silva et al. 2016 for the alternative, Roussel et al. 2020
for lidR itself.

It follows the lidR route: CSF or morphological ground, **TIN** height
normalisation, variable-window tree tops, then Dalponte 2016 or Silva 2016 crowns.
`novatrees.pcf_bridge` runs it beside this one rather than choosing between them,
because they were built for different data and it shows.

**Height normalisation, on dense TLS.** Scored against the course's own normalised
copy of the Day 3 cloud, point for point:

| | bias | RMSE |
| --- | ---: | ---: |
| `novatrees`, DTM quantile 0.25 per 0.5 m cell | -0.0025 m | 0.0685 m |
| `pcf`, TIN through the ground returns | -0.0662 m | 0.1535 m |

Ours wins here, and the reason is the data rather than the algorithm. Ground returns
under a TLS scanner are dense enough that a per-cell quantile has plenty to work with,
while a TIN triangulates through whatever low vegetation survived classification and
carries it into the surface. On sparse airborne ground returns the argument reverses,
which is why both are kept.

**ALS tree detection, inside the 15 m ground plot** where the two ground sensors give
a reference count:

| | objects over the ALS footprint | inside the plot | median crown area |
| --- | ---: | ---: | ---: |
| `pcf`, variable window 3 m + Dalponte 2016 | 118 | **25** | 26.0 m2 |
| `novatrees.chm_watershed` | 92 | 20 | 57.6 m2 |
| ours after `drop_fragments` | 53 | 13 | 84.1 m2 |
| ground reference (MLS / TLS stems) | | **38 / 48** | |

`pcf` is closer, and its crowns are the right size while ours are roughly twice too
large, which is the signature of a watershed basin merging neighbouring crowns. Its
seeding is also better suited: a variable window scaled to canopy height separates
adjacent tops that one fixed smoothing kernel runs together.

**Both undercount by a factor of two.** That is not a tuning failure either. The same
stand that made a CHM fail on Day 3 is here: over half the stems are suppressed, and
a helicopter records the crown that shades them, not the tree. No airborne method
recovers a tree that left no return.

**This is now wired in.** `run_sensor(..., detector="pcf")` runs `pcf`'s chain on our
normalised heights, so only the segmentation differs, and its crown raster becomes the
per-point labels directly. Measured against the ground stems:

| | ours, watershed | `pcf`, dalponte2016 |
| --- | ---: | ---: |
| crowns inside the 15 m ground plot | 13 | **25** |
| median crown area | 84.1 m2 | **29.8 m2** |
| stems per occupied crown | 2.64 | **1.31** |
| stems the ALS accounts for | 34 % | **63 %** |

Our crowns were roughly three times too large, each swallowing two or three stems.
Everything downstream inherited that: the fitted height exponent moved from 1.48 to
2.21, which is what a cone predicts, and the volume expansion ratio fell from 1.60 to
1.06. See the appendix at the end of this file.

The division of labour is therefore `pcf` for the ALS crown step and `novatrees` for
normalisation on the ground clouds and everything below breast height.

## On the learned detector

TLS and MLS use TreeAIBox's **boreal** stem classifier and tree locator, which suit
this forest.

ALS uses the **reclamation-site** models, because those are the only published ALS
weights, and the released ALS set has no stem classifier at all. That run is a
domain-transfer test, not a like-for-like comparison, and it is labelled as such
wherever its numbers appear.

## Noise, including mist

Mist deserves separate mention because it does not behave like other noise. Droplets
hanging around stems are **diffuse rather than isolated**, so a statistical filter
finds each droplet well-connected to its neighbours and keeps it, and raising the
threshold removes real sparse canopy first. Two things do work: a radius filter at a
scale wider than the droplet spacing, and the reflectance screen, since atmospheric
returns fall below both bark and foliage.

Having two sensors over one plot makes the filter checkable rather than trusted. ALS
puts the canopy top at 162.72 m over the MLS footprint, and MLS carries 5,853 points
above that height, which nothing in the plot can explain except noise.

---

## Appendix: upscaling, an extra step taken after the exercise

**Not part of the Day 4 exercise.** The exercise ends at the joined table above. This
asks what that table is for: fit a volume model on the matched trees and apply it to
every airborne crown, including the ones no ground sensor reached. Whether the course
goes this way next is unknown at the time of writing.

It fits the model that table exists for, applies it to every airborne crown, and spends
most of its length on why the result should not be believed as a model of anything.
[`01_upscaling_regression.py`](01_upscaling_regression.py) needs `out/day04/` to exist,
so run the exercise notebook first.

### Which stem does a crown belong to?

The Day 4 join used nearest neighbour: each crown apex takes the closest stem within
3 m. **That asks the wrong question.** An airborne crown is the top of one tree, the
one that reached the light there, and every other stem underneath it is a tree the
helicopter could not see. Calling those "unmatched" hides the largest limitation of
airborne inventory in a layered stand.

`novatrees.match_by_crown` gives each crown to the dominant stem beneath it and
records the rest as suppressed. On the MLS stems against the filtered ALS crowns:

| | |
| --- | ---: |
| ground stems | 38 |
| standing under some crown | 35 |
| **owning a crown, so matched** | **13** |
| **suppressed, under a taller neighbour** | **22** |
| under no crown at all | 3 |
| crowns with no stem beneath | 38 |

The helicopter appears to see 34 per cent of the stems standing in this plot. **That
number turned out to be mostly our own fault**, and the correction is further down: it
is 63 per cent once the ALS is segmented with `pcf`'s Dalponte crowns instead of our
watershed. Read this section as the method, and the ALS detector comparison below as
the result.

Two details the rule needs, both found by running it:

- **A height check.** "Tallest stem inside the footprint" handed a 25 m crown to a
  6.1 m sapling standing under it, because the real owner was never detected from the
  ground. Requiring the stem and the crown to agree on height to within 4 m removes
  that, and the result is stable anywhere from 2 to 6 m.
- **The footprint is a circle** of radius `sqrt(area / pi)`, because the ALS table
  stores crown area and apex rather than a polygon. A crown is not round and its apex
  is not its centre, so the scale is exposed as a slider and the counts move with it:
  13 matched at 0.8, 14 at 1.0, 16 at 1.2, 19 at 1.5.

### The better matching gives the worse-looking model

Same response, same predictors, only the matching rule changed:

| matching | n | fitted | R2 cv | RMSE cv |
| --- | ---: | --- | ---: | ---: |
| nearest neighbour | 10 | `V = 2.81e-07 h_max^4.060 crown_volume^0.326` | **+0.557** | 19.8 % |
| crown ownership | 11 | `V = 0.000897 h_max^1.523 crown_volume^0.341` | -0.116 | 29.9 % |

A stem is roughly a cone, so height should enter at a power near 2 to 3 once crown
size is accounted for. Nearest neighbour returned **4.06**, which is not a taper
relationship; it is a small sample letting one variable absorb the correlation with
everything else. Crown ownership returns 1.52, which is plausible, and predicts worse.

The explanation is selection. Matching within 3 m quietly keeps the trees whose stem
base sits almost under their own apex: isolated, upright, dominant trees. That is an
easier sample, not a better one, and the flattering cross-validation score came from
the sample rather than from the model.

**The honest reading of the second row is that eleven trees cannot support this
regression.** That was equally true of the first row and the selection hid it.

### What the notebook does about a sample of twelve

- **Leave-one-out cross-validation on every model.** In-sample R2 at n = 12 is
  meaningless; a four-parameter model fits twelve points well no matter what.
- **The null model sits in the table.** Predict the mean for every tree. Several
  candidates lose to it, including crown area alone, whose cross-validated R2 is
  negative.
- **The back-transform is corrected.** A log-log fit predicts the conditional median,
  so exponentiating and summing biases the total low. The Baskerville factor is
  applied and reported rather than applied silently.
- **The sensor is swapped.** Fitting on TLS-derived volumes instead of MLS moves the
  upscaled total by about 26 per cent and the height exponent from 4.06 to 5.39. No
  internal statistic could have revealed that, and it is the floor on what any
  regression fitted here can achieve.

### The result, and how far to trust it

With height and crown volume, fitted on MLS, applied to 53 crowns over 0.283 ha:

| | |
| --- | ---: |
| plot total | 57.3 m3 |
| **volume per hectare** | **203 m3/ha** |
| stems per hectare | 187 |
| sampling interval, 95 % | 179 to 227 m3/ha |
| model error if errors are independent | 1.7 m3 (3 %) |
| model error if errors are correlated | 12.6 m3 (22 %) |

A boreal stand of this height carries 150 to 300 m3/ha, so the number is plausible.
**Plausible is not validated.** Three things are wrong with it, in increasing order of
seriousness:

1. The two model-error rows differ by a factor of seven. A model fitted on twelve
   trees from one plot makes correlated errors, so the second is nearer the truth.
2. The response is itself partly modelled, and swapping the ground sensor moves it by
   a quarter.
3. **Only 187 stems per hectare are being counted**, against roughly 540 in the ground
   plot, so the per-hectare figure is a total over dominant trees rather than over the
   forest. This looked like an airborne detection limit and was mostly our own crown
   delineation; the correction is two sections below.

### Stop naming the tree, and count instead

Everything above models the dominant stem under each crown, which throws away 22 of
38 stems. **Counting keeps them.** `novatrees.crown_occupancy` asks how many stems
stand under each crown and what they add up to, so the unit becomes the crown and the
quantity becomes the volume *under* a crown rather than the volume *of* a stem. That
is the right target: summing it over every airborne crown recovers the suppressed
trees, while summing a dominant-stem model reproduces the undercount by construction.

It also sidesteps the hardest part of matching. Naming the owner needs the stem
detected, segmented and ranked; counting needs only that it was detected. With two
ground sensors the count is averaged and their disagreement becomes its error bar.

| sensor | crowns occupied | stems placed | stems per occupied crown |
| --- | ---: | ---: | ---: |
| MLS | 14 | 35 of 38 | 2.50 |
| TLS | 14 | 39 of 42 | 2.79 |
| **averaged** | **14** | | **2.64** |

Median disagreement between the sensors: **1.0 stem** per crown. Median share of the
volume under a crown that does **not** belong to its dominant stem: **0.43**.

**Crowns overlap, so the partition has to be exclusive.** Counting a stem in every
footprint that contains it inflated the total from 38 stems to 54. Each stem now goes
to the crown whose apex is nearest, which makes the sums addable. That was a real bug
in the first version of this.

### Can a crown predict what stands under it? No.

| target | best model | R2 cv | RMSE cv |
| --- | --- | ---: | ---: |
| volume under the crown | crown volume | +0.122 | 52.5 % |
| **number of stems** | **every model loses to the mean** | **negative** | > 51 % |

Fourteen crowns, and the stem count is not predictable from crown height or width at
all. That is worth more than a fitted line: the crown-level quantity is the one an
unbiased stand total needs, and it is far harder than the dominant-stem quantity that
scored +0.557 earlier. **The earlier score came from modelling an easier thing on a
selected sample.**

How many trees hide under a crown is a property of the stand's layering, not of that
crown's geometry.

### A ratio estimator instead

When the per-unit relationship cannot be fitted, the answer is not to fit a worse one.
Measure the ratio where both quantities are known and expand the total:

| | |
| --- | ---: |
| crowns with both quantities | 13 |
| **expansion ratio R** | **1.60** (95 % 1.30 to 1.92) |
| per-crown ratio, median | 1.51 |
| per-crown ratio, range | 1.00 to 2.85 |

| | dominant stems only | corrected |
| --- | ---: | ---: |
| plot total | 57.3 m3 | **91.4 m3** |
| **per hectare** | 203 m3/ha | **323 m3/ha** (95 % 263 to 388) |
| stems per hectare | 187 | **461** |

**The dominant-stem total was missing about a third of the wood and more than half
the stems.** The ground plot holds 38 stems in 0.071 ha, near 540 per hectare, so the
corrected density is the right order and the uncorrected one was not.

The interval covers the ratio only. It excludes the regression error, the sensor
disagreement, and the assumption that crowns outside the ground coverage are layered
like the ones inside it. That last one is the shakiest thing here: the ratio was
measured on 13 crowns near the plot centre and applied to 53.

### The ALS segmentation was the problem, not the sensor

Everything above ran on our own CHM watershed crowns. Repeating it with `pcf`'s
variable-window tops and Dalponte 2016 crowns, on the same normalised heights so that
only the segmentation differs.

`pcf` is my Python mirror of the R exercises from the earlier course sessions, and the
crown algorithm inside it is [Dalponte and Coomes
2016](https://doi.org/10.1111/2041-210X.12575), reached through
[lidR](https://doi.org/10.1016/j.rse.2020.112061). Neither is mine, and on this step
both are better than what I wrote:

| | ours, watershed | `pcf`, dalponte2016 |
| --- | ---: | ---: |
| objects found | 92 | 118 |
| after fragment filtering | 53 | 97 |
| crowns inside the 15 m ground plot | 13 | **25** |
| median crown area | 84.1 m2 | **29.8 m2** |
| stems per occupied crown | 2.64 | **1.31** |
| **stems the ALS accounts for** | **34 %** | **63 %** |
| training trees for the regression | 11 | **21** |
| R2 cv | -0.174 | **+0.378** |
| RMSE cv | 30.7 % | **20.8 %** |
| fitted height exponent | 1.48 | **2.21** |
| expansion ratio R | 1.60 | **1.06** |

Every line improves, and two of them matter more than the rest.

**The height exponent lands at 2.21**, which is what a cone predicts once crown size
is accounted for. Our crowns were three times too large, each swallowing two or three
stems, so the dominant-stem relationship was being fitted through a quantity that was
not one tree.

**The expansion ratio falls to 1.06.** With crowns that hold roughly one stem each,
the dominant-stem model already captures 94 per cent of the volume standing under
them, and the ratio correction that mattered so much above becomes almost unnecessary.

So the reading earlier on this page, that most of the stand is invisible from the air,
was **wrong as stated**. The helicopter was fine; our crown delineation was merging
neighbours. That is worth more than the volume number: the failure looked like a
sensor limitation and was a software one, and only running someone else's
implementation on the same data separated them.

### The result, corrected

| | ours, watershed | `pcf`, dalponte2016 |
| --- | ---: | ---: |
| dominant-stem total | 187 m3/ha | 359 m3/ha |
| corrected by R | 298 m3/ha | **381 m3/ha** |
| stems per hectare | 461 | **450** |

The two routes to stem density now agree, 461 against 450, from segmentations that
disagreed by a factor of two on how many crowns exist. The ground plot holds 38 stems
in 0.071 ha, near 540 per hectare, so both remain a little low, which is what a canopy
that still hides the smallest trees should do.

At 450 stems per hectare and 381 m3/ha the mean tree is 0.85 m3, and a 25 m stem of
0.30 m DBH at a form factor of 0.5 is 0.88 m3. That the two agree is a check, not a
proof, and the volume figure still rests on 21 trees.

### What would make it a model

More plots before more trees per plot; a held-out plot never touched during fitting;
species separated, since a power law across pine, spruce and birch is an average of
three taper forms; and better ground truth, since the sensor swap already sets the
floor. See [`../../docs/best-practices.md`](../../docs/best-practices.md).
