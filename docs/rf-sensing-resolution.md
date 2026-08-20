# Can WiFi produce point clouds?

Short answer: yes in a narrow sense, and the resolution is three to four orders of
magnitude worse than the TLS data in this repo. The limit is physical, not an
engineering gap, so it does not close with better hardware or better processing.

Written up after a question during the NOVA 2026 course, 2026-08-19.

## Two limits, and only two

Everything follows from these. Nothing in the signal chain recovers detail that
neither of them captured.

### Range resolution comes from bandwidth

$$\delta_{r} = \frac{c}{2B}$$

Two scatterers closer than $\delta_r$ along the line of sight return echoes that
overlap in time and cannot be separated. Transmit power, antenna count and clever
processing make no difference to this.

| standard | band | bandwidth $B$ | $\delta_r$ |
| --- | --- | ---: | ---: |
| 802.11n | 2.4 / 5 GHz | 20 MHz | 7.5 m |
| 802.11ac | 5 GHz | 80 MHz | 1.9 m |
| 802.11ax (WiFi 6) | 2.4 / 5 / 6 GHz | 160 MHz | 0.94 m |
| 802.11be (WiFi 7) | 6 GHz | 320 MHz | 0.47 m |
| 802.11ad (WiGig) | 60 GHz | 2.16 GHz | 6.9 cm |
| 802.11ay, bonded | 60 GHz | ~8 GHz | ~1.8 cm |

### Cross-range resolution comes from aperture

$$\delta_{cr} \approx \frac{\lambda R}{2L}$$

for wavelength $\lambda$, target range $R$ and aperture $L$. A commodity access
point has three antennas at half-wavelength spacing, so $L \approx 0.12$ m at
5 GHz - a very small aperture:

| configuration | $\lambda$ | $L$ | $\delta_{cr}$ at $R$ = 5 m |
| --- | ---: | ---: | ---: |
| 5 GHz, 3-antenna array | 6 cm | 0.12 m | **1.25 m** |
| 5 GHz, 2 m synthetic aperture | 6 cm | 2 m | 7.5 cm |
| 60 GHz, compact array | 5 mm | 0.05 m | 25 cm |
| 60 GHz, 1 m synthetic aperture | 5 mm | 1 m | **1.25 cm** |

Synthetic aperture is what rescues the cross-range figure, and it is not free: it
requires moving the radio along a known path and knowing that path to a fraction
of a wavelength. Self-localisation becomes the accuracy bottleneck instead.

## Measured against this plot

`crsot_mixed_stand.laz` is 15.6 M points over 18.0 x 18.8 m. Stem circles fit with
residuals around 0.02 m, and the cross-section method depends on resolving stems of
0.04–0.94 m diameter inside a 0.30 m slab.

| | point count | effective resolution |
| --- | ---: | --- |
| TLS (this plot) | 15,595,864 | mm to cm |
| WiFi 6/7 sensing | 10^2 – 10^3 | 0.5 to 2 m |
| 60 GHz with SAR | 10^3 – 10^4 | 1 to 10 cm |

At 80 MHz the *entire* 23 m canopy is about twelve depth cells deep. Even WiFi 7's
320 MHz places one depth sample every half metre - coarser than most of the DBH
values being measured. There is no stem cross-section to cluster.

Density is the second gap and it is separate from resolution. Published "3D from
WiFi" results typically produce hundreds to a few thousand points, and most lean
heavily on learned priors: a network trained on human bodies or indoor scenes
inferring plausible geometry from sparse channel-state information. That is
reasonable for occupancy and pose, and it is not measurement. A taper curve
computed from inferred geometry measures the prior, not the tree.

## The 60 GHz exception, and why it does not help here

802.11ad/ay is the one genuinely interesting case: 2.16 GHz of bandwidth gives
~7 cm range resolution, and $\lambda$ = 5 mm makes even small synthetic apertures
effective. Centimetre-scale RF imaging at 60 GHz is real and demonstrated.

It is also the worst possible band for a forest. Oxygen absorption peaks near
60 GHz (~15 dB/km in clear air) and foliage scattering is severe - the wavelength
is comparable to leaf and needle dimensions, which is precisely the regime where
scattering dominates. The band that has the resolution cannot see into a canopy.

## Where RF does work for forestry

Not at WiFi frequencies or WiFi geometries, but the technique is sound at the
other end of the spectrum. Canopy penetration improves as frequency falls, so
biomass-oriented radar uses **P-band (~435 MHz)** and **L-band (~1.3 GHz)** -
ESA's BIOMASS mission and NISAR, both spaceborne SAR. Longer wavelengths pass
through foliage and scatter off branches and stems, which is what makes them
sensitive to structure and biomass.

The physics runs directly against WiFi: 2.4–6 GHz penetrates canopy only
partially, and 60 GHz barely at all.

## Bottom line

| question | answer |
| --- | --- |
| Can WiFi produce something point-cloud-like? | Yes - sparse, coarse 3D occupancy |
| At what resolution? | Decimetres to metres; ~cm only at 60 GHz with SAR |
| Enough for stem detection? | No, by two to three orders of magnitude |
| Would better processing fix it? | No - $\delta_r = c/2B$ is a hard bound |
| Is any RF useful for forest structure? | Yes, P- and L-band SAR - not WiFi |

## Formulas, together

$$\delta_{r} = \frac{c}{2B}
\qquad
\delta_{cr} \approx \frac{\lambda R}{2L}
\qquad
\lambda = \frac{c}{f}$$

Both are diffraction and time-resolution bounds. They apply to every radar,
sonar and lidar equally - a TLS instrument wins not because light is magic but
because its effective bandwidth and aperture are enormous by comparison.
