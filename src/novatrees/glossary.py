# NOVA course 2026 - point cloud tooling
# Author: José M. Beltrán-Abaunza (jose.beltran@mgeo.lu.se), Lund University
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of a free software project distributed under the GNU General
# Public License v3 or later. See LICENSE at the repository root.

"""The acronym glossary, loadable in a notebook.

Every term used across this repository lives in `docs/glossary.yaml`, one file rather
than scattered through prose, so a reader meeting CHM or DBH for the first time has
somewhere to look and there is one place to keep correct.

    from novatrees.glossary import load, table, lookup

    load()                 # the whole thing as a dict
    table()                # a DataFrame, ready for mo.ui.table
    table(group="metrics") # one section
    lookup("CHM")          # a single term
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

__all__ = ["GLOSSARY_PATH", "load", "table", "lookup", "groups"]


def _find_glossary() -> Path:
    """Locate docs/glossary.yaml relative to the installed package or the repo."""
    here = Path(__file__).resolve()
    for base in (here.parents[2], here.parents[1], Path.cwd()):
        candidate = base / "docs" / "glossary.yaml"
        if candidate.exists():
            return candidate
    return here.parents[2] / "docs" / "glossary.yaml"


GLOSSARY_PATH = _find_glossary()


@lru_cache(maxsize=1)
def load(path: str | Path | None = None) -> dict:
    """Read the glossary. Cached, since it is small and read repeatedly."""
    import yaml

    p = Path(path) if path else GLOSSARY_PATH
    with open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def groups(path: str | Path | None = None) -> list[str]:
    """The section names, in the order they appear in the file."""
    terms = load(path)["terms"]
    seen: list[str] = []
    for entry in terms.values():
        g = entry.get("group", "other")
        if g not in seen:
            seen.append(g)
    return seen


def lookup(term: str, path: str | Path | None = None) -> dict | None:
    """One term, case-insensitively. Returns None if it is not in the glossary."""
    terms = load(path)["terms"]
    if term in terms:
        return {"term": term, **terms[term]}
    lowered = {k.lower(): k for k in terms}
    key = lowered.get(term.lower())
    return {"term": key, **terms[key]} if key else None


def table(group: str | None = None, path: str | Path | None = None):
    """The glossary as a DataFrame: term, stands for, group, what it means here.

    `group` filters to one section; `groups()` lists them.
    """
    import pandas as pd

    rows = [
        {
            "term": term,
            "stands for": entry.get("name", ""),
            "group": entry.get("group", "other"),
            "what it means here": " ".join(str(entry.get("note", "")).split()),
        }
        for term, entry in load(path)["terms"].items()
        if group is None or entry.get("group") == group
    ]
    return pd.DataFrame(rows)


def markdown(group: str | None = None, path: str | Path | None = None) -> str:
    """The glossary as a markdown table, for a notebook or a document."""
    df = table(group=group, path=path)
    lines = ["| term | stands for | what it means here |", "| --- | --- | --- |"]
    lines += [f"| **{r.term}** | {r._2} | {r._4} |" for r in df.itertuples()]
    return "\n".join(lines)
