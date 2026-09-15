#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Taper, volume, and the fusion argument tested rather than assumed.

Computation lives in analysis.taper(), which reconstructs each stem twice: once with a
drone-supplied total height and once without.
"""
import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import numpy as np
import analysis as A

T = A.taper()
q = T.dropna(subset=["volume"])
print(f"taper reconstructed for {len(q)} stems\n")
print(f"  DBH taper vs cross-section fit    r {q.dbh_taper.corr(q.dbh_slice):+.3f}")
print(f"  covered fraction  median {q.covered.median():.2f}"
      f"  [{q.covered.quantile(.25):.2f}, {q.covered.quantile(.75):.2f}]")
print(f"  form factor       median {q.form.median():.3f}"
      f"  [{q.form.quantile(.25):.3f}, {q.form.quantile(.75):.3f}]")
print(f"  form vs covered fraction          r {q.form.corr(q.covered):+.3f}")
print(f"  stem volume       median {q.volume.median():.3f} m3   total {q.volume.sum():.2f} m3")

u = q.dropna(subset=["volume_no_h"])
print(f"\nsame {len(u)} stems, with and without the drone height")
print(f"  measured volume  {u.volume.median():.3f} m3  against  {u.volume_no_h.median():.3f} m3")
print(f"  form factor      {u.form.median():.3f}     against  {u.form_no_h.median():.3f}")
print(f"  covered fraction {u.covered.median():.3f}     against  {u.covered_no_h.median():.3f}")
print("\n  The measured volume is an integral over what was reconstructed, so it never")
print("  depended on the drone. What changes is the denominator of the form factor.")
