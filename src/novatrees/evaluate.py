"""Score predicted tree instances against the reference `treeid` field.

The course clouds ship a per-point reference labelling, which makes this a real
instance-segmentation problem rather than a look-at-the-colours exercise.

Instances are matched greedily by IoU, highest first, one-to-one. From that
matching fall the three failure modes worth naming separately:

* **missed** — a reference tree no prediction claimed
* **over-segmentation** — one reference tree split across several predictions
* **under-segmentation** — several reference trees merged into one prediction

A method can score a respectable mean IoU while doing badly on any of these, so
they are reported alongside, not folded in.
"""

from __future__ import annotations

import numpy as np

__all__ = ["instance_scores", "confusion_pairs"]


def _pair_counts(pred: np.ndarray, ref: np.ndarray):
    """Co-occurrence counts between predicted and reference labels, ignoring unlabelled."""
    m = (pred >= 0) & (ref > 0)
    p, r = pred[m], ref[m]
    pu, pi = np.unique(p, return_inverse=True)
    ru, ri = np.unique(r, return_inverse=True)
    counts = np.zeros((len(pu), len(ru)), np.int64)
    np.add.at(counts, (pi, ri), 1)
    return pu, ru, counts, m.sum()


def instance_scores(pred: np.ndarray, ref: np.ndarray, iou_threshold: float = 0.5) -> dict:
    """Greedy IoU matching of predicted instances to reference instances.

    `pred` is 0-based with -1 unassigned; `ref` is the raw `treeid` field where
    0 means unassigned.
    """
    pu, ru, counts, n_common = _pair_counts(pred, ref)
    if counts.size == 0:
        return {"n_pred": 0, "n_ref": 0, "matched": 0}

    pred_sizes = np.bincount(pred[pred >= 0], minlength=pred.max() + 1)[pu]
    ref_sizes = np.array([(ref == r).sum() for r in ru], np.int64)

    union = pred_sizes[:, None] + ref_sizes[None, :] - counts
    iou = np.where(union > 0, counts / np.maximum(union, 1), 0.0)

    # Greedy one-to-one assignment, best IoU first.
    order = np.argsort(iou, axis=None)[::-1]
    taken_p, taken_r, pairs = set(), set(), []
    for flat in order:
        i, j = divmod(int(flat), iou.shape[1])
        if iou[i, j] <= 0:
            break
        if i in taken_p or j in taken_r:
            continue
        taken_p.add(i)
        taken_r.add(j)
        pairs.append((int(pu[i]), int(ru[j]), float(iou[i, j])))

    ious = np.array([p[2] for p in pairs]) if pairs else np.zeros(0)
    matched = int((ious >= iou_threshold).sum())

    # How many predictions overlap each reference tree by a non-trivial amount,
    # and vice versa — the split/merge signal.
    frac_of_ref = counts / np.maximum(ref_sizes[None, :], 1)
    frac_of_pred = counts / np.maximum(pred_sizes[:, None], 1)
    splits = (frac_of_ref >= 0.20).sum(axis=0)  # predictions covering each ref
    merges = (frac_of_pred >= 0.20).sum(axis=1)  # refs covered by each prediction

    return {
        "n_pred": int(len(pu)),
        "n_ref": int(len(ru)),
        "n_points_scored": int(n_common),
        "matched": matched,
        "recall": matched / len(ru),
        "precision": matched / len(pu),
        "mean_iou_matched": float(ious[ious >= iou_threshold].mean()) if matched else 0.0,
        "mean_iou_all_pairs": float(ious.mean()) if len(ious) else 0.0,
        "missed": int(len(ru) - len(taken_r)),
        "over_segmented_refs": int((splits > 1).sum()),
        "under_segmented_preds": int((merges > 1).sum()),
        "pairs": pairs,
    }


def confusion_pairs(scores: dict, top: int = 10) -> list[tuple[int, int, float]]:
    """The `top` best-matched (pred, ref, IoU) triples, for eyeballing."""
    return sorted(scores.get("pairs", []), key=lambda t: -t[2])[:top]
