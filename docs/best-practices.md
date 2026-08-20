# Best practices, learned the hard way

Every rule below cost something to learn on this course data, and each one names the
mistake it came from. Nothing here is general wisdom copied from a textbook. Where a
practice is specific to boreal plots or to these three sensors, it says so.

The order is the order the pipeline runs in, not the order of importance.

---

## Before anything: know what your sensor cannot see

**Choose the detection method from the viewpoint, not from a benchmark.** ALS looks
down and sees the crown first; TLS and MLS look up from the ground and see bark first.
On the Day 3 TLS plot, cross-section seeding reached recall 0.68 and a CHM watershed
reached 0.15. On the Day 4 ALS the ranking reverses, because a helicopter records no
stem to cut a cross-section through. **Neither method is better. They answer to
different data.**

**A canopy height model cannot see a suppressed tree, and no parameter fixes it.** A
CHM keeps the highest return per cell, so a tree beneath a taller neighbour leaves no
trace in it. On the Day 3 plot, 23 of 41 reference trees stand under 10 m in a 22.8 m
canopy. Over half the stand is invisible before a single threshold is chosen. Check
the height distribution of your reference before blaming the algorithm.

**Density is not coverage.** Day 4 TLS has roughly four times the point density of MLS
and disagreed with the ALS about tree height by 6.34 m RMSE against MLS's 1.31 m. A
tripod resolves the lower stem beautifully and loses the crown top behind everything
in front of it; a scanner walking through the plot sees the same crown from several
sides. More points from one place is not more information.

---

## Ground and height

**Normalise before comparing anything across sensors.** The Day 4 TLS is not
georeferenced in Z: its heights read -2.5 to 27.9 m while the other two sit at 135 to
166 m. Normalised height is the only datum the three share. Anything compared before
that step is comparing nothing.

**A cloud zeroed at the ground is not a normalised cloud.** Its Z is shifted to a
common datum, but the terrain is still in it, so every height still carries the slope
of the plot. The distinction has its own flag in `run_sensor` because it was missed
once.

**The per-cell DTM statistic matters more than the interpolation method.** The
textbook minimum is biased low by sub-surface noise: +0.264 m bias against the
course's own normalisation, RMSE 0.275, of which 96 per cent is bias rather than
scatter. A 0.25 quantile gives bias -0.002 m and RMSE 0.068. Same algorithm, same
cell size, one statistic changed.

**Exclude noise from the ground set before building the DTM.** One return below the
true surface drags its cell down and biases every height above it.

---

## Noise

**Match the filter to the noise, not to a default.** Isolated returns fall to a
statistical outlier filter. **Mist does not**: droplets hanging around stems are
diffuse rather than isolated, so each one looks well-connected to its neighbours, and
raising the threshold removes real sparse canopy first. A radius filter at a scale
wider than the droplet spacing works, and so does the reflectance screen, because
atmospheric returns fall below both bark and foliage.

**Use a second sensor to check the filter rather than trusting it.** ALS puts the
canopy top at 162.72 m over the MLS footprint, and MLS carries 5,853 points above that
height. Nothing in the plot explains those except noise. Two sensors over one plot
turn a judgement call into a measurement.

---

## Detection and segmentation

**Large merged instances are a seeding failure, not a growing failure.** The biggest
predicted tree on the Day 3 plot swallowed two reference trees because only one had a
seed. No graph parameter fixes that: `max_geodesic` truncates every tree and `max_edge`
barely moves it, because the crowns really do touch. Better seeds fix it.

**Remove the ground before region growing.** The forest floor is one continuous sheet
touching the base of every stem, so with it in place the cheapest path from one tree's
seed to another tree's crown runs straight through the ground, and labels bleed across
the plot.

**Ground gets no tree id.** A patch of forest floor does not belong to the tree
standing on it in any measurable sense, and assigning it inflates every per-tree
statistic computed downstream.

**Filter the cross-section on shape and reflectance rather than shrinking the
clustering radius.** Two stems 0.31 m apart merged at the default radius. Shrinking
the radius separates them and fragments single stems everywhere else; filtering the
slice separates them without that cost.

**Watershed debris is positions, and positions are what matching uses.** Of 92 ALS
objects, 26 were slivers caught between basins. They win nearest-neighbour matches
against real stems and bring nonsense heights with them. Removing them took the
matched height RMSE from 10.88 m to 2.09 m. Filter fragments **before** matching, not
after.

---

## Fitting circles and stems

**A cross-section is a ring, so test that it is hollow.** The scanner sees bark and
the wood behind it stops the beam, so the middle of a real cross-section is empty.
Points inside an inner circle are foliage in the slab, a branch crossing it, mist, or
a circle fitted to something that is not a stem. This asks whether the geometry is
right; a minimum point count only asks whether there is enough of it. Idea taken from
3DFin.

**Compare each slice against the last *accepted* slice, not the previous one.**
Otherwise one bad fit becomes the new reference and walks the whole chain off the
stem.

**Track the stem axis instead of assuming it vertical.** A leaning stem's centre must
move with height, so a centre-tolerance test rejects nearly every slice on a tilted
tree no matter how it is tuned. Rotating into a single principal axis is not the fix
either: it improved one tree from 3 to 7 accepted slices and made another worse, from
7 to 1, and it cannot help a curved stem where no single axis exists. Refit the centre
band by band.

**Do not try to measure lean from cross-section ellipticity.** The geometry is right
and the signal is hopeless: median lean of 4.4 degrees predicts an axis ratio of 0.997,
while real stems are 5 to 15 per cent out of round from ovality and bark alone. The
signal sits roughly 50 times under the noise, and the measured correlation with
PCA-derived lean was 0.25. Ship axis ratio as a quality flag; take lean from the
tracked centreline.

**One test is never enough for a fork.** Counting components per band marked 32 of 32
trees as forked. Adding persistence alone still marked 12 of 12. Persistence, vertical
extent, lean and relative radius together give 3 of 12, which is believable for a
boreal stand.

---

## Volume, and the trap in it

**A taper integral is not a stem volume.** Its limits are the first and last
*accepted* slice, not the ground and the tip. On these clouds the strict thresholds
span 16 to 44 per cent of tree height, so the integral is a partial stem volume and
nothing in the formula says so. This was reported as stem volume for a full day.

**Report cover with every measured volume.** $(z_1 - z_0)/H$ costs nothing and makes
the number impossible to misread.

**Check the form factor before reading the volume.** $f = V / \pi (D_{1.3}/2)^2 H$
sits at 0.45 to 0.50 for a boreal conifer. A value near 0.25 is not a thin tree, it is
an integral that stopped halfway. This one line would have caught the error
immediately, and it is the cheapest check in the whole pipeline.

**An extrapolated taper has to close.** A fitted curve is only usable above the data
if it falls to nearly nothing at the tip and never widens with height. Test it on the
raw prediction, before any clamping, because **clamping a bad fit does not repair it,
it disguises it**: forcing a runaway curve to be non-increasing turns it into a flat
cylinder running to the treetop, which looks plausible on a plot and carries a large
invented volume. One stem did exactly that, at 0.16 m diameter from 18.6 m to 23.6 m,
with a form factor of 0.60 where its neighbours held 0.44 to 0.48.

**Refuse rather than repair, and accept the coverage loss.** Only 26 of 38 trees get a
model volume once the closure test is applied, and 11 of 23 on the learned run. Fewer
trees, defensible numbers. The refusal also *raised* agreement with the ALS, from
+0.791 to +0.822, which is the evidence that it removes noise rather than data.

**Report the variants separately instead of merging them.** Measured-strict,
measured-relaxed and modelled are three different claims. Give the reader all three
with their cover and form factor and let them choose; anything fitted downstream then
has to declare which it used.

---

## Comparing methods

**Do not trust the first result.** Every substantive finding here reversed at least
once. The 4 cm versus 10 cm model comparison reversed. The B versus C detector ranking
reversed. The volume was wrong for a day.

**Watch the denominator.** Scoring recall against only the reference trees a
prediction happened to overlap makes *less coverage raise the score*. A method that
labels a third of the plot looks excellent. Use every reference instance in the cloud.

**Run the other implementation rather than reasoning about it.** `pcf` beats us on ALS
crowns, 25 trees against 20 inside the plot with crowns the right size; we beat `pcf`
on dense-TLS normalisation, bias -0.002 m against -0.066 m. Neither was predictable
from reading the methods.

**Do not retune someone else's software until it agrees with yours.** 3DFin runs here
at its shipped defaults, with one cluster-size floor lowered because 1000 starves on a
small plot. It scores recall 0.39 against our 0.68, and that comparison is worth
little in itself, because our parameters were tuned against that exact plot for a
session and theirs were not.

**Where an independent implementation *agrees* is worth more than where you win.**
3DFin's own stem reconstruction covers a median 24 per cent of tree height at form
factor 0.21; ours covered 30 per cent at 0.24. Two independent implementations
producing the same pathology is what promoted "partial volume" from a suspected bug in
our code to a property of the data.

**Agreement between two instruments beats either one's internal fit statistics.** Both
ground sensors are carried through to volume for exactly this reason: where TLS and
MLS disagree is the honest error bar on the exercise.

---

## Working practice

**Check the arithmetic against domain expectation, not against the previous run.** The
form factor, the implied stem count per hectare, the crown area against a plausible
crown: these catch errors that no unit test would.

**Keep the parameters with the results.** "Cross-sections every 0.08 m through a 0.10 m
slab" is part of the number. A volume without its slice geometry cannot be compared
with anyone else's.

**Beware float32 for projected coordinates.** A UTM northing of 6,481,815 has a float32
resolution of 0.5 m, sixteen times the radius tolerance used for taper fitting.
Caching a cloud as float32 silently destroyed the geometry and inflated median DBH to
0.55 m. Centre the coordinates before casting, or keep float64.

**Deep learning is not automatically the stronger method here.** TreeAIBox took 1,324 s
on MLS and 4,894 s on TLS, on CPU, to find the same number of trees as a heuristic
that runs in under a minute, and fewer of its stems survived to a volume. It does give
the best precision on Day 3. Use it where seeding is the bottleneck, and measure the
cost.

**Say what was not done.** The ALS detection head is 1.6 ms per point, which is 2.5
hours for 5.6 M points on CPU and was not run. The published ALS models are trained on
reclamation sites, not boreal forest. Both facts belong beside the results, not in a
footnote.

---

## See also

- [`methods-and-equations.md`](methods-and-equations.md) - the equations behind each of these
- [`3dfin.md`](3dfin.md) - the third-party comparison in full
- [`../notebooks/day03/README.md`](../notebooks/day03/README.md) and [`../notebooks/day04/README.md`](../notebooks/day04/README.md) - the measurements these rules came from
