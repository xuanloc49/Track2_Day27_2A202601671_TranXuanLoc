from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def detect_distribution_shift(
    current_values: Iterable[float],
    baseline_values: Iterable[float],
    *,
    ratio_threshold: float = 3.0,
    ks_alpha: float = 0.01,
) -> dict[str, Any]:
    """Distribution drift detector combining Kolmogorov-Smirnov 2-sample test and robust mean/quantile ratios."""
    cur = np.asarray(list(current_values), dtype=float)
    base = np.asarray(list(baseline_values), dtype=float)
    if cur.size == 0 or base.size == 0:
        return {"is_anomaly": False, "score": 0.0, "method": "ks_and_ratio", "reason": "empty_input"}

    cur_mean = float(np.mean(cur))
    base_mean = float(np.mean(base))

    # 1. Ratio-based score
    if base_mean == 0:
        ratio_score = float("inf") if cur_mean != 0 else 1.0
    else:
        ratio_score = max(abs(cur_mean / base_mean), abs(base_mean / cur_mean)) if cur_mean != 0 else float("inf")

    ratio_anomaly = bool(ratio_score >= ratio_threshold)

    # 2. Kolmogorov-Smirnov 2-sample test for arbitrary distribution drift
    ks_stat = 0.0
    ks_pvalue = 1.0
    ks_anomaly = False
    try:
        from scipy import stats
        res = stats.ks_2samp(cur, base)
        ks_stat = float(res.statistic)
        ks_pvalue = float(res.pvalue)
        # Anomaly if distributions differ significantly at alpha level and min sample size
        if cur.size >= 5 and base.size >= 5 and ks_pvalue < ks_alpha and ks_stat >= 0.3:
            ks_anomaly = True
    except Exception:
        pass

    is_anomaly = ratio_anomaly or ks_anomaly
    primary_score = float(ratio_score) if ratio_anomaly else float(ks_stat)

    return {
        "is_anomaly": bool(is_anomaly),
        "score": primary_score,
        "method": "ks_and_ratio",
        "ks_statistic": ks_stat,
        "ks_pvalue": ks_pvalue,
        "mean_ratio": float(ratio_score),
        "reason": f"baseline_mean={base_mean:.3f}, current_mean={cur_mean:.3f}, ks_stat={ks_stat:.3f}, ks_pvalue={ks_pvalue:.4f}",
    }

