from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def detect_distribution_shift(
    current_values: Iterable[float],
    baseline_values: Iterable[float],
    *,
    ratio_threshold: float = 3.0,
) -> dict[str, Any]:
    """Robust detector using mean ratio.

    Compares current batch mean against baseline mean with finite array cleaning.
    """
    try:
        cur_arr = np.asarray(list(current_values), dtype=float)
        cur = cur_arr[np.isfinite(cur_arr)]
    except Exception:
        cur = np.array([], dtype=float)

    try:
        base_arr = np.asarray(list(baseline_values), dtype=float)
        base = base_arr[np.isfinite(base_arr)]
    except Exception:
        base = np.array([], dtype=float)

    if cur.size == 0 or base.size == 0:
        return {"is_anomaly": False, "score": 0.0, "method": "mean_ratio", "reason": "empty_input"}

    cur_mean = float(np.mean(cur))
    base_mean = float(np.mean(base))
    if base_mean == 0:
        score = float("inf") if cur_mean != 0 else 1.0
    else:
        score = max(abs(cur_mean / base_mean), abs(base_mean / cur_mean)) if cur_mean != 0 else float("inf")

    return {
        "is_anomaly": bool(score >= ratio_threshold),
        "score": float(score),
        "method": "mean_ratio",
        "reason": f"baseline_mean={base_mean:.3f}, current_mean={cur_mean:.3f}",
    }




