from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def _clean_array(values: Iterable[float]) -> np.ndarray:
    try:
        arr = np.asarray(list(values), dtype=float)
        return arr[np.isfinite(arr)]
    except Exception:
        return np.array([], dtype=float)


def calculate_psi(actual: np.ndarray, expected: np.ndarray, num_buckets: int = 10) -> float:
    """Calculate Population Stability Index (PSI) between two numeric distributions."""
    if actual.size == 0 or expected.size == 0:
        return 0.0
    try:
        percentiles = np.linspace(0, 100, num_buckets + 1)
        buckets = np.percentile(expected, percentiles)
        buckets[0] = -np.inf
        buckets[-1] = np.inf
        # Deduplicate bucket edges if ties exist
        buckets = np.unique(buckets)
        if len(buckets) < 2:
            return 0.0

        exp_counts, _ = np.histogram(expected, bins=buckets)
        act_counts, _ = np.histogram(actual, bins=buckets)

        exp_pct = np.clip(exp_counts / len(expected), 1e-4, 1.0)
        act_pct = np.clip(act_counts / len(actual), 1e-4, 1.0)

        psi_val = float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))
        return max(0.0, psi_val)
    except Exception:
        return 0.0


def detect_distribution_shift(
    current_values: Iterable[float],
    baseline_values: Iterable[float],
    *,
    ratio_threshold: float = 3.0,
    ks_alpha: float = 0.01,
    psi_threshold: float = 0.25,
) -> dict[str, Any]:
    """Distribution drift detector combining KS 2-sample test, PSI, and robust ratios."""
    cur = _clean_array(current_values)
    base = _clean_array(baseline_values)
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

    # 2. Kolmogorov-Smirnov 2-sample test
    ks_stat = 0.0
    ks_pvalue = 1.0
    ks_anomaly = False
    try:
        from scipy import stats
        res = stats.ks_2samp(cur, base)
        ks_stat = float(res.statistic)
        ks_pvalue = float(res.pvalue)
        if cur.size >= 5 and base.size >= 5 and ks_pvalue < ks_alpha and ks_stat >= 0.3:
            ks_anomaly = True
    except Exception:
        pass

    # 3. Population Stability Index (PSI)
    psi_value = calculate_psi(cur, base)
    psi_anomaly = bool(psi_value >= psi_threshold)

    is_anomaly = ratio_anomaly or ks_anomaly or psi_anomaly
    primary_score = float(ratio_score) if ratio_anomaly else (float(ks_stat) if ks_anomaly else float(psi_value))

    return {
        "is_anomaly": bool(is_anomaly),
        "score": primary_score,
        "method": "ks_and_ratio",
        "ks_statistic": ks_stat,
        "ks_pvalue": ks_pvalue,
        "psi": psi_value,
        "mean_ratio": float(ratio_score),
        "reason": f"baseline_mean={base_mean:.3f}, current_mean={cur_mean:.3f}, ks_stat={ks_stat:.3f}, psi={psi_value:.3f}",
    }


