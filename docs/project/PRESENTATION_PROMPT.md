# Prompt: a visual story for the NOVA 2026 project talk

Copy everything below the line into the tool that will build the deck. Attach the
figures listed under "Material" (all in `figures/`), plus `report.md` for reference.

---

Build a 20 minute presentation (about 12 slides) for my individual project in the course
NOVA 2026, Point cloud processing for forestry. The audience is the course teachers and
the other students, who know lidar and photogrammetry. I will talk over the slides, so
the slides should carry pictures and a few numbers, not paragraphs.

## Focus

The teachers asked me to focus on the two point cloud questions and leave out the
spectral ones:

- **RQ4.** How does drone flight geometry (nadir against oblique) change the
  reconstructed canopy, and do tree attributes follow?
- **RQ5.** What can a drone point cloud measure compared with terrestrial (TLS), mobile
  (MLS) and helicopter (ALS) laser scanning and the field tree list?

Do not include colour indices, greenness, band mapping or species separation (RQ1 to
RQ3). One line on the question slide can say they are left out.

## The story

Tell it as one idea: **each instrument measures what it can see.** The drone looks down
and sees the canopy surface. The ground scanners look up and see stems and ground. The
plot is the same; the forest in the data is not.

Suggested arc:

1. **Title.** "What a drone point cloud can measure on a forest plot." One plot, seven
   point clouds, 74 surveyed stems.
2. **The setup.** Plot 167 at Remningstorp from the air (`fig1_plot_context.png`), with
   small icons or labels for the seven acquisitions: four drone clouds (nadir and
   oblique, RGB and multispectral camera), TLS, MLS, helicopter ALS.
3. **The two questions**, RQ4 and RQ5, large and short.
4. **Same trees, different forests.** Put the drone and laser cross-sections next to each
   other (`slide/fig3_drone_cross_sections.png`, `slide/fig4_lidar_cross_sections.png`).
   The drone is a shell over the canopy; TLS and MLS show stems and ground. This is the
   key visual of the talk.
5. **Where the points are.** `fig5_vertical_profiles.png`, with one big number per
   instrument for median return height: TLS 1.3 m, MLS 5.9 m, ALS 17.5 m, drone about
   20 m. Then the canopy top agrees: p95 23.6 to 23.8 m drone against 23.77 m ALS.
6. **The hidden error.** A simple diagram: drone canopy surface on top, terrain model
   below, a 2.089 m gap between ALS terrain and MLS ground. Big number "2.089 m". Message:
   every drone tree height would have been that much too tall, and the drone data alone
   could not show it. After one constant correction the RMSE is 0.079 m.
7. **RQ4: crowns change, heights do not.** A before/after visual of one crown in nadir
   and oblique (use `fig2_drone_from_above.png` or a simple drawing): oblique crowns are
   a third larger (22.0 against 16.7 m²), height changes only 0.1 to 0.2 m. Oblique has
   26 to 45 % more points.
8. **RQ4 and RQ5: detection.** A clean bar or dot chart of F1: Nadir RGB 0.815, Oblique
   RGB 0.780, Nadir MS 0.772, Oblique MS 0.750, ALS 0.794, TLS via canopy height model
   0.566, TLS via stem slice 0.800, MLS via stem slice 0.795. Highlight two points:
   nadir beats oblique despite fewer points, and the drone equals the helicopter.
9. **Small trees are missed by everyone.** `fig6_detection_by_dbh.png`. Precision is
   above 0.92 everywhere; recall is limited by suppressed trees under the canopy.
10. **RQ5: stems only from below.** `fig8_dbh_and_form.png` (left panel is enough). TLS
    diameter RMSE 1.30 cm against a contemporaneous list; the drone cannot measure
    diameter at all.
11. **The surprise.** I expected volume to need both views (diameter from below, top
    from the drone). It did not: 0.847 m³ with and without the drone height, because TLS
    already reconstructs 86 % of the tree. The drone's real value is coverage: TLS and
    MLS miss 28 % of the plot. A plot map showing the 30 by 30 m ground-scanner box inside
    the 20 m radius plot would make this clear.
12. **What each instrument can measure.** A visual matrix, instruments as columns,
    attributes as rows, with ticks, crosses and the key number in each cell:

    | | drone | ALS | TLS / MLS |
    |---|---|---|---|
    | tree detection | F1 0.815 | F1 0.794 | F1 0.800 / 0.795 |
    | canopy height | yes | yes | under-sampled |
    | crown area | depends on flight | not tested | no |
    | stem diameter | no | no | RMSE 1.3 cm |
    | ground | no | yes | yes |

    End with one line: check heights against a second instrument.

Optional last slide: limits (field survey from 2011, detection tuned on the same
reference, no field reference for volume) and one assumption: the nadir and oblique
flights were flown on the same day or at most one day apart, so the differences between
them are mainly view geometry.

## Style

- Mostly images, diagrams and big numbers. At most three short lines of text per slide.
- First person ("I compared", "I expected"), plain and clear.
- No em dashes and no section symbol.
- One accent colour for the drone and one for the lasers, used the same way on every
  slide, so the audience can follow "from above" against "from below".
- Keep every number exactly as given here. Do not round them differently or add new
  ones.
- Author line: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University.

## Material

Figures in `figures/`:

- `fig1_plot_context.png`: the plot on the orthomosaic, with scan positions
- `fig2_drone_from_above.png`: the four drone clouds from above
- `slide/fig3_drone_cross_sections.png`: drone cross-sections, landscape
- `slide/fig4_lidar_cross_sections.png`: laser cross-sections, landscape
- `fig5_vertical_profiles.png`: height distribution of returns per instrument
- `fig6_detection_by_dbh.png`: detection rate by DBH quartile
- `fig8_dbh_and_form.png`: TLS diameter against the references, and form factor

Do not use `fig7_species.png`; it belongs to the spectral questions.
