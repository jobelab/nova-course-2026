#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build every cached artefact once, so scripts and notebooks open instantly after."""
import sys, time; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import _common as C, analysis as A

C.terrain()
for name, fn in (("heights", A.heights), ("detections", A.detections),
                 ("crowns", A.crowns), ("stems", A.stems), ("taper", A.taper)):
    t = time.time(); d = fn()
    print(f"  {name:<12} {len(d):>6} rows  {time.time()-t:6.1f}s", flush=True)
print("cache warm:", sorted(p.name for p in C.OUT.glob('*')))
