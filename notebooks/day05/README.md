# Day 5: upscaling volume from twelve trees to a hectare

Day 4 ended at a table of matched trees. This fits the model that table exists for,
applies it to every airborne crown, and spends most of its length on why the result
should not be believed as a model of anything.

## Notebook

[`00_upscaling_regression.py`](00_upscaling_regression.py). It needs `out/day04/` to
exist, so run the Day 4 notebook or the Day 4 script first.

## Which stem does a crown belong to?

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

## The better matching gives the worse-looking model

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

## What the notebook does about a sample of twelve

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

## The result, and how far to trust it

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

## Stop naming the tree, and count instead

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

## The ALS segmentation was the problem, not the sensor

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

## The result, corrected

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

## What would make it a model

More plots before more trees per plot; a held-out plot never touched during fitting;
species separated, since a power law across pine, spruce and birch is an average of
three taper forms; and better ground truth, since the sensor swap already sets the
floor. See [`../../docs/best-practices.md`](../../docs/best-practices.md).
