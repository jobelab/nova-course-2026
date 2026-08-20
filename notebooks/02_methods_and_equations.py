"""The processing pipeline written out: diagrams and equations.

What each stage actually computes, where semantic segmentation ends and instance
segmentation begins, and the formulas behind every number the other two notebooks
report.

Run:  uv run marimo edit notebooks/02_methods_and_equations.py --watch

SPDX-License-Identifier: GPL-3.0-or-later
Author: José M. Beltrán-Abaunza (ORCID 0000-0003-3777-6788), Lund University
"""

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Glossary

    Every acronym used across this repository, with what it means **here** rather than
    in general. The source is [`docs/glossary.yaml`](../docs/glossary.yaml), so it is
    one file to keep correct rather than definitions scattered through prose.

        from novatrees.glossary import load, table, lookup
        lookup("CHM")
        table(group="metrics")
    """)
    return


@app.cell
def _(mo):
    from novatrees.glossary import groups, table

    glossary_group = mo.ui.dropdown(
        ["all"] + groups(), value="all", label="section"
    )
    glossary_search = mo.ui.text(placeholder="filter, e.g. canopy", label="search")
    mo.vstack([glossary_group, glossary_search])
    return glossary_group, glossary_search, table


@app.cell
def _(glossary_group, glossary_search, mo, table):
    _df = table(group=None if glossary_group.value == "all" else glossary_group.value)
    _q = glossary_search.value.strip().lower()
    if _q:
        _hit = (
            _df["term"].str.lower().str.contains(_q)
            | _df["stands for"].str.lower().str.contains(_q)
            | _df["what it means here"].str.lower().str.contains(_q)
        )
        _df = _df[_hit]
    mo.vstack([
        mo.ui.table(_df, selection=None, page_size=15),
        mo.md(f"**{len(_df)}** terms shown."),
    ])
    return


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Method reference

    Two questions the pipeline answers, and they are not the same question.

    **Semantic segmentation** asks *what kind of thing is this point?* - ground,
    stem, foliage. A label from a fixed set of classes:

    $$f_{\text{sem}} : \mathbb{R}^3 \rightarrow \mathcal{C}, \qquad
      \mathcal{C} = \{\text{ground},\ \text{stem},\ \text{foliage}\}$$

    **Instance segmentation** asks *which tree is this point part of?* - an
    identifier with no fixed vocabulary, because the number of trees is discovered,
    not known in advance:

    $$f_{\text{inst}} : \mathbb{R}^3 \rightarrow \{1, \dots, K\} \cup \{\varnothing\},
      \qquad K \text{ unknown a priori}$$

    Doing both at once is *panoptic* segmentation: every point gets a class **and**,
    if it belongs to a countable object, an instance id.

    The pipeline uses semantic steps as scaffolding for the instance step. Ground
    classification is semantic and exists to make the instance step possible at all;
    stem detection is semantic and exists to generate seeds.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## The pipeline end to end
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.mermaid(
        """
    graph TD
        RAW["Raw TLS cloud<br/>15.6 M points, absolute Z"]

        subgraph SEM1["Semantic: ground vs non-ground"]
            CSF["CSF cloth simulation<br/>rigidness, cloth resolution"]
            GRD["ground points"]
            NGRD["non-ground points"]
        end

        subgraph NORM["Height normalisation"]
            DTM["DTM per cell<br/>q-quantile of ground Z"]
            HN["h = z - DTM(x,y)"]
        end

        subgraph SEM2["Semantic: stem vs non-stem"]
            SLICE["cross-section slab<br/>1.15 - 1.45 m"]
            DB["DBSCAN in 2D"]
            FIT["Taubin circle fit"]
            VC["vertical continuity test"]
        end

        subgraph INST["Instance: which tree"]
            SEEDS["stem seeds<br/>one per tree"]
            GRAPH["kNN graph over<br/>above-ground points"]
            DIJ["multi-source Dijkstra<br/>geodesic Voronoi"]
            IDS["treeID per point"]
        end

        METRICS["Per-tree metrics<br/>DBH, height, taper"]

        RAW --> CSF
        CSF --> GRD
        CSF --> NGRD
        GRD --> DTM
        DTM --> HN
        NGRD --> HN
        HN --> SLICE
        SLICE --> DB --> FIT --> VC --> SEEDS
        HN --> GRAPH
        SEEDS --> DIJ
        GRAPH --> DIJ
        DIJ --> IDS
        IDS --> METRICS

        style SEM1 fill:#e8f0e0,stroke:#54a24b
        style SEM2 fill:#e8f0e0,stroke:#54a24b
        style INST fill:#e6eef7,stroke:#4c78a8
        style NORM fill:#f7f0e6,stroke:#c78a4c
            """
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    The green blocks are semantic, the blue block is instance. Note the arrow from
    normalisation into the graph as well as into the slice: **the ground must be
    removed before the graph is built**, and that is the single most consequential
    line in the diagram. The forest floor is a continuous sheet of points touching
    the base of every stem, so if it stays in, the cheapest path from one tree's
    seed to another tree's crown runs through the ground and every label bleeds
    into its neighbours.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 1. CSF - cloth simulation

    Flip the cloud upside down and drop a cloth on it. Where the cloth comes to
    rest is the terrain. Each cloth particle is a mass under gravity, integrated
    with Verlet:

    $$\mathbf{X}(t + \Delta t) = 2\,\mathbf{X}(t) - \mathbf{X}(t - \Delta t)
      + \frac{\mathbf{G}}{m}\,\Delta t^{2}$$

    Then internal constraints pull neighbouring particles back toward each other,
    applied as a displacement between connected particles $i, j$:

    $$\Delta \mathbf{p} = \tfrac{1}{2}\, b \,(\mathbf{p}_{j} - \mathbf{p}_{i}),
      \qquad b \in \{0, 1\}$$

    with $b = 0$ for particles already pinned by the terrain. **Rigidness** is
    simply how many times this constraint is applied per step - more iterations, a
    stiffer cloth that ignores small dips. Finally a point is ground if it sits
    close enough to the settled cloth:

    $$c(\mathbf{p}) =
      \begin{cases}
        \text{ground}, & \lvert z_{\mathbf{p}} - z_{\text{cloth}}(\mathbf{p}) \rvert \le h_{cc} \\
        \text{non-ground}, & \text{otherwise}
      \end{cases}$$

    where $h_{cc}$ is `class_threshold`. That is the whole classifier - one
    distance test against a simulated surface.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 2. Height normalisation

    Ground points are binned into cells of side $c$, and each cell takes a single
    height. Which statistic you take is not cosmetic:

    $$\mathrm{DTM}(i,j) = Q_{q}\big(\{\, z_{p} \;:\; p \in \mathcal{G},\;
      \kappa(p) = (i,j) \,\}\big)$$

    where $\mathcal{G}$ is the ground set, $\kappa(p)$ is the cell of point $p$ and
    $Q_q$ is the $q$-quantile. Setting $q = 0$ recovers the textbook minimum. Cells
    with no ground point are filled from the nearest filled cell. Normalised height
    is then

    $$h_{p} = z_{p} - \mathrm{DTM}\big(\kappa(p)\big)$$

    The minimum is biased low, because TLS noise leaves a few returns beneath the
    real surface, and every height above them inherits the error. Measured against
    the course's own `_hnorm` file: $q=0$ gives a bias of $+0.264$ m, $q=0.25$ gives
    $-0.002$ m.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 3. Bias and RMSE

    The two numbers used to judge normalisation, over $n$ points with estimate
    $\hat{h}_i$ and reference $h_i$:

    $$\mathrm{bias} = \frac{1}{n} \sum_{i=1}^{n} \left( \hat{h}_{i} - h_{i} \right)$$

    $$\mathrm{RMSE} = \sqrt{ \frac{1}{n} \sum_{i=1}^{n}
      \left( \hat{h}_{i} - h_{i} \right)^{2} }$$

    They are not independent. Writing $s$ for the standard deviation of the
    residuals,

    $$\mathrm{RMSE}^{2} = \mathrm{bias}^{2} + s^{2}$$

    which is why they must be read together. A method can have near-zero bias and a
    terrible RMSE (unbiased but noisy), or a small RMSE dominated entirely by bias -
    the latter is the $q=0$ case here, where $\mathrm{bias} = 0.264$ and
    $\mathrm{RMSE} = 0.275$, so $s = \sqrt{0.275^2 - 0.264^2} \approx 0.077$ m.
    Almost all of that error is a constant offset, and a constant offset is a
    systematic problem, not random noise. Fixable, and worth fixing.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## 4. Cross-section stem detection

    **DBSCAN** on the 2D slice. A point is a core point when its $\varepsilon$-ball
    holds at least `minPts` neighbours:

    $$N_{\varepsilon}(p) = \{\, q \in D \;:\; \lVert p - q \rVert_{2} \le \varepsilon \,\},
      \qquad p \text{ is core} \iff \lvert N_{\varepsilon}(p) \rvert \ge \mathrm{minPts}$$

    Clusters are the transitive closure of core points; everything else is noise.
    No cluster count is required in advance, which is exactly the property we need.

    **Taubin circle fit** on each cluster. A circle in algebraic form is

    $$A\,(x^{2} + y^{2}) + B\,x + C\,y + D = 0$$

    and Taubin's estimator minimises the algebraic distance normalised by its
    gradient, which is what makes it unbiased for partial arcs - the usual case in
    TLS, where a stem is only scanned from one side:

    $$\min_{A,B,C,D} \;
      \frac{\sum_{i} \left( A(x_{i}^{2} + y_{i}^{2}) + B x_{i} + C y_{i} + D \right)^{2}}
           {4A^{2}\,\overline{(x^{2} + y^{2})} + 4AB\,\bar{x} + 4AC\,\bar{y} + B^{2} + C^{2}}$$

    giving centre and radius

    $$(x_{c}, y_{c}) = \left( \frac{-B}{2A},\ \frac{-C}{2A} \right), \qquad
      r = \frac{\sqrt{B^{2} + C^{2} - 4AD}}{2\lvert A \rvert}, \qquad
      \mathrm{DBH} = 2r$$

    **Vertical continuity.** A stem persists above and below breast height; a bush
    does not. A candidate survives only if both check slabs hold enough points
    within the fitted radius:

    $$\big\lvert \{\, p \in S^{-} : \lVert (x_p, y_p) - (x_c, y_c) \rVert \le r + \delta \,\} \big\rvert \ge m
      \quad \wedge \quad \text{same for } S^{+}$$

    This single test is what separates stems from understory clutter.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 5. 3D Dijkstra region growing

    Voxel-downsample the above-ground points to graph nodes,

    $$\kappa(\mathbf{p}) = \left\lfloor \mathbf{p} / v \right\rfloor$$

    keeping one representative per occupied voxel. Build an undirected kNN graph
    $G = (V, E)$ with Euclidean weights, refusing any edge longer than $d_{\max}$:

    $$w(u,v) =
      \begin{cases}
        \lVert \mathbf{p}_{u} - \mathbf{p}_{v} \rVert_{2},
          & v \in \mathrm{kNN}_{k}(u) \ \wedge\ \lVert \mathbf{p}_{u} - \mathbf{p}_{v} \rVert_{2} \le d_{\max} \\
        \infty, & \text{otherwise}
      \end{cases}$$

    That $d_{\max}$ cut is what stops the graph leaping across open air into a
    neighbouring crown. The geodesic distance from a seed $s$ to a node $x$ is the
    cheapest path through the point cloud,

    $$d_{g}(s, x) = \min_{\pi \in \Pi(s,x)} \sum_{(a,b) \in \pi} w(a,b)$$

    and each node takes the label of its nearest seed:

    $$\ell(x) = \arg\min_{s \in S} \; d_{g}(s, x)$$

    This is a **geodesic Voronoi partition** of the cloud. The contrast with an
    ordinary Voronoi diagram is the whole point: straight-line distance would assign
    a low branch to whichever stem is nearest in space, even across a gap, whereas
    geodesic distance has to travel *through the tree*, so a branch stays with the
    trunk it is physically connected to.

    Computed for all seeds at once with a multi-source Dijkstra - one pass, $O(|E| \log |V|)$,
    not one pass per tree.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 6. Scoring instance segmentation
    """)
    return


@app.cell
def _(mo):
    mo.mermaid(
        """
    graph LR
        P["predicted instances<br/>P1 ... Pm"]
        R["reference instances<br/>R1 ... Rn"]
        IOU["IoU matrix<br/>m x n"]
        GREEDY["greedy one-to-one<br/>match, highest IoU first"]
        TAU{"IoU >= tau ?"}
        TP["matched"]
        FP["false positive<br/>spurious tree"]
        FN["missed<br/>undetected tree"]
        SPLIT["over-segmented<br/>1 tree -> many"]
        MERGE["under-segmented<br/>many trees -> 1"]

        P --> IOU
        R --> IOU
        IOU --> GREEDY
        GREEDY --> TAU
        TAU -->|yes| TP
        TAU -->|no| FP
        TAU -->|no| FN
        IOU --> SPLIT
        IOU --> MERGE

        style TP fill:#e8f0e0,stroke:#54a24b
        style FP fill:#f7e6e6,stroke:#c74c4c
        style FN fill:#f7e6e6,stroke:#c74c4c
            """
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    Instances are sets of points, so overlap is intersection over union:

    $$\mathrm{IoU}(P_{i}, R_{j}) = \frac{\lvert P_{i} \cap R_{j} \rvert}{\lvert P_{i} \cup R_{j} \rvert}
      = \frac{\lvert P_{i} \cap R_{j} \rvert}{\lvert P_{i} \rvert + \lvert R_{j} \rvert - \lvert P_{i} \cap R_{j} \rvert}$$

    Predictions are matched to references greedily, highest IoU first, one-to-one.
    A match counts only above a threshold $\tau$ (0.5 here), giving

    $$\mathrm{precision} = \frac{\mathrm{TP}}{\lvert \hat{\mathcal{T}} \rvert}, \qquad
      \mathrm{recall} = \frac{\mathrm{TP}}{\lvert \mathcal{T} \rvert}, \qquad
      F_{1} = \frac{2\,\mathrm{PR}}{\mathrm{P} + \mathrm{R}}$$

    Those three hide the two failure modes that matter most in forestry, so they are
    counted separately. With $\phi$ a coverage fraction (0.20 here), a reference tree
    is **over-segmented** when several predictions each claim a real share of it,

    $$\mathrm{split}(R_{j}) = \Big\lvert \Big\{ i \;:\;
      \tfrac{\lvert P_{i} \cap R_{j} \rvert}{\lvert R_{j} \rvert} \ge \phi \Big\} \Big\rvert > 1$$

    and a prediction is **under-segmented** when it swallows several reference trees,

    $$\mathrm{merge}(P_{i}) = \Big\lvert \Big\{ j \;:\;
      \tfrac{\lvert P_{i} \cap R_{j} \rvert}{\lvert P_{i} \rvert} \ge \phi \Big\} \Big\rvert > 1$$

    A method can post a respectable mean IoU while quietly merging half the stand,
    which is why these are reported alongside rather than folded in.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 7. The reference method: CHM watershed
    """)
    return


@app.cell
def _(mo):
    mo.mermaid(
        """
    graph TD
        subgraph A["A - top-down (PCT, Yrttimaa)"]
            A1["normalised cloud"] --> A2["CHM: max h per cell"]
            A2 --> A3["Gaussian smooth"]
            A3 --> A4["local maxima = tree tops"]
            A4 --> A5["marker-controlled watershed"]
            A5 --> A6["crown polygons"]
            A6 --> A7["treeID"]
        end

        subgraph B["B - bottom-up (this pipeline)"]
            B1["normalised cloud"] --> B2["remove ground"]
            B2 --> B3["slice at breast height"]
            B3 --> B4["cluster + circle fit"]
            B4 --> B5["stem seeds"]
            B2 --> B6["kNN graph"]
            B5 --> B7["multi-source Dijkstra"]
            B6 --> B7
            B7 --> B8["treeID"]
        end

        A7 --> CMP{"compare vs<br/>reference treeid"}
        B8 --> CMP

        style A fill:#f7f0e6,stroke:#c78a4c
        style B fill:#e6eef7,stroke:#4c78a8
            """
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    Method A builds a canopy height model, keeping the highest return per cell,

    $$\mathrm{CHM}(i,j) = \max \{\, h_{p} \;:\; \kappa(p) = (i,j) \,\}, \qquad
      \tilde{C} = \mathrm{CHM} * G_{\sigma}$$

    finds tree tops as local maxima under a minimum separation $\rho$,

    $$T = \{\, (i,j) \;:\; \tilde{C}(i,j) = \max_{\lVert (i,j)-(u,v) \rVert \le \rho} \tilde{C}(u,v)
      \ \wedge\ \tilde{C}(i,j) \ge h_{\min} \,\}$$

    and floods watershed basins on the inverted surface $-\tilde{C}$ from those
    markers.

    **Where that breaks here.** The $\max$ in the first equation is the entire
    problem. A suppressed tree beneath a taller neighbour contributes to no cell's
    maximum, so it is absent from $\tilde{C}$, absent from $T$, and cannot be
    recovered by any downstream tuning. On this plot 23 of 41 reference trees are
    under 10 m in a 22.8 m canopy - over half the stand is invisible to the method
    before a single parameter is chosen.

    Method B's seeds come from a slab at $h \approx 1.3$ m, where a suppressed stem
    is exactly as visible as a dominant one. Hence recall 0.51 against 0.10–0.15,
    on the same cloud, scored the same way.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Stem taper, volume, and the limits of the integral

    Circles are fitted per slice by RANSAC, checked against the last accepted slice,
    and integrated:

    $$V = \int_{z_0}^{z_1} \pi \left( \frac{d(z)}{2} \right)^{2} dz$$

    **$z_0$ and $z_1$ are the first and last accepted slice, not the ground and the
    tip.** Returns per stem thin with height until slices fall below the minimum
    point count and the chain stops, usually in the lower canopy. Measured here, the
    strict thresholds span 16 to 44 per cent of tree height, so this integral returns
    a *partial* stem volume. Nothing in the formula announces that, which is why the
    number was believed longer than it should have been.

    An analytic taper is what allows the missing part to be estimated. The Kozak form
    keeps a power of $X$ whose exponent varies with relative height:

    $$d(h) = D \cdot X^{\,b_1 z^2 + b_2 \ln(z + 0.001) + b_3 \sqrt{z} + b_4 e^{z}},
    \qquad X = \frac{1 - \sqrt{z}}{1 - \sqrt{p}}, \quad z = \frac{h}{H},
    \quad p = \frac{1.3}{H}$$

    reduced to four coefficients, since the published nine-coefficient version is
    fitted across a population rather than one stem. $X \to 0$ as $h \to H$, so the
    curve closes to zero diameter at the tip and $\int_0^H$ is well posed. It is
    still extrapolation above $z_1$.

    ### Three answers, and the diagnostic that separates them

    | | integrated over | claim |
    | --- | --- | --- |
    | measured, strict | $[z_0, z_1]$ at PCT thresholds | what the scanner saw |
    | measured, relaxed | $[z_0', z_1']$, loosened thresholds | more of what it saw, less precisely |
    | model | $[0, H]$ | the whole stem, part of it predicted |

    Cover, $(z_1 - z_0)/H$, travels with the measured columns. The form factor

    $$f = \frac{V}{\pi \left( D_{1.3} / 2 \right)^{2} H}$$

    travels with all of them. A boreal conifer stem holds $f \approx 0.45$ to $0.50$.
    Values near $0.25$ do not describe thin trees; they describe an integral that
    stopped halfway, which is exactly how the defect above was caught. Reading $f$
    before reading $V$ costs nothing and would have caught it immediately.
    """)
    return


@app.cell
def _(mo):
    mo.md(r"""
    ---

    ### Sources

    - CSF - Zhang W. et al. (2016), [Remote Sensing 8(6):501](https://doi.org/10.3390/rs8060501)
    - Taubin fit - Taubin G. (1991), *IEEE PAMI* 13(11)
    - DBSCAN - Ester M. et al. (1996), *KDD-96*
    - Kozak taper - Kozak A. (2004), *Forestry Chronicle* 80(4):507-515
    - PCT - Yrttimaa T. (2021), [zenodo.5779288](https://doi.org/10.5281/zenodo.5779288);
      [Yrttimaa et al. 2019](https://doi.org/10.3390/rs11121423),
      [2020](https://doi.org/10.1016/j.isprsjprs.2020.08.017)
    """)
    return


if __name__ == "__main__":
    app.run()
