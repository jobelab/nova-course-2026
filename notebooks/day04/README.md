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

## Notebook

[`00_multisensor_inventory.py`](00_multisensor_inventory.py) runs all six steps, with
both the heuristic and the learned detector.

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
| ALS | 2.8 M | 92 | 15 | 23 s |
| MLS | 7.6 M | 38 | 7 | 44 s |
| TLS | 7.8 M | 43 | 8 | 61 s |

The two ground sensors agreeing at 38 and 43 while ALS reports 92 is the expected
shape. ALS is fragmenting crowns, not finding trees the ground missed, since a
helicopter cannot see a stem the scanner was standing beside.

Both ground sensors are carried through to volume rather than one, because where TLS
and MLS disagree that disagreement is the honest error bar on the whole exercise. Two
independent instruments agreeing is worth more than either one's internal fit
statistics.

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
