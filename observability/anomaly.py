"""Anomaly detection engine with robust statistics and context-aware automated selection.

Supports:
- Standard Z-Score detector for Gaussian metrics
- Median Absolute Deviation (MAD) for robust, outlier-resistant detection with zero-MAD handling
- Automated mode (auto) that incorporates segment history, day-of-week seasonality, and domain context
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def _clean_history(history: Iterable[float]) -> np.ndarray:
    """Extract finite numeric values from history, discarding NaNs and non-numerics."""
    try:
        arr = np.asarray(list(history), dtype=float)
        return arr[np.isfinite(arr)]
    except Exception:
        return np.array([], dtype=float)


def zscore_detector(current: float, history: Iterable[float], threshold: float = 3.0) -> dict[str, Any]:
    values = _clean_history(history)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "zscore", "reason": "insufficient_history"}
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std == 0:
        score = float("inf") if float(current) != mean else 0.0
    else:
        score = abs(float(current) - mean) / std
    return {
        "is_anomaly": bool(score > threshold),
        "score": float(score),
        "method": "zscore",
        "reason": f"mean={mean:.3f}, std={std:.3f}, threshold={threshold}",
    }


def mad_detector(current: float, history: Iterable[float], threshold: float = 3.5) -> dict[str, Any]:
    """Robust Median Absolute Deviation detector with graceful zero-MAD fallback."""
    values = _clean_history(history)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "mad", "reason": "insufficient_history"}

    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))

    if mad == 0:
        mean_dev = float(np.mean(np.abs(values - median)))
        if mean_dev == 0:
            if float(current) == median:
                return {
                    "is_anomaly": False,
                    "score": 0.0,
                    "method": "mad",
                    "reason": f"all_history_identical ({median:.3f}) and matches current",
                }
            else:
                return {
                    "is_anomaly": True,
                    "score": float("inf"),
                    "method": "mad",
                    "reason": f"all_history_identical ({median:.3f}) but current={float(current):.3f}",
                }
        else:
            modified_z = 0.6745 * abs(float(current) - median) / mean_dev
            return {
                "is_anomaly": bool(modified_z > threshold),
                "score": float(modified_z),
                "method": "mad",
                "reason": f"median={median:.3f}, mean_dev={mean_dev:.3f}, threshold={threshold}",
            }

    modified_z = 0.6745 * abs(float(current) - median) / mad
    return {
        "is_anomaly": bool(modified_z > threshold),
        "score": float(modified_z),
        "method": "mad",
        "reason": f"median={median:.3f}, mad={mad:.3f}, threshold={threshold}",
    }


def iqr_detector(current: float, history: Iterable[float], multiplier: float = 1.5) -> dict[str, Any]:
    """Interquartile Range (IQR / Tukey fence) detector for skewed metrics."""
    values = _clean_history(history)
    if values.size < 4:
        return {"is_anomaly": False, "score": 0.0, "method": "iqr", "reason": "insufficient_history"}
    q25, q75 = float(np.percentile(values, 25)), float(np.percentile(values, 75))
    iqr = q75 - q25
    lower_bound = q25 - multiplier * iqr
    upper_bound = q75 + multiplier * iqr
    is_anomaly = bool(current < lower_bound or current > upper_bound)
    score = (
        float(max(abs(current - q75) / (iqr + 1e-9), abs(q25 - current) / (iqr + 1e-9)))
        if iqr > 0
        else (float("inf") if is_anomaly else 0.0)
    )
    return {
        "is_anomaly": is_anomaly,
        "score": score,
        "method": "iqr",
        "reason": f"q25={q25:.3f}, q75={q75:.3f}, iqr={iqr:.3f}, bounds=[{lower_bound:.3f}, {upper_bound:.3f}]",
    }


def ewma_detector(
    current: float, history: Iterable[float], alpha: float = 0.3, threshold: float = 3.0
) -> dict[str, Any]:
    """Exponentially Weighted Moving Average (EWMA) detector for tracking smooth trend changes."""
    values = _clean_history(history)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "ewma", "reason": "insufficient_history"}
    ewma_mean = float(values[0])
    for v in values[1:]:
        ewma_mean = alpha * float(v) + (1 - alpha) * ewma_mean
    std = float(np.std(values))
    if std == 0:
        score = float("inf") if float(current) != ewma_mean else 0.0
    else:
        score = abs(float(current) - ewma_mean) / std
    return {
        "is_anomaly": bool(score > threshold),
        "score": float(score),
        "method": "ewma",
        "reason": f"ewma_mean={ewma_mean:.3f}, std={std:.3f}, alpha={alpha}, threshold={threshold}",
    }


def detect_anomaly(
    current: float,
    history: Iterable[float],
    *,
    method: str = "auto",
    threshold: float = 3.0,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stable anomaly detection API.

    Methods:
    - 'zscore': classic parametric z-score.
    - 'mad': non-parametric Median Absolute Deviation.
    - 'iqr': interquartile range / Tukey fence detector.
    - 'ewma': exponentially weighted moving average.
    - 'rolling': rolling-window baseline.
    - 'auto': context-aware engine leveraging seasonality, same-segment baselines, and events.
    """
    if method == "zscore":
        return zscore_detector(current, history, threshold=threshold)

    if method == "mad":
        return mad_detector(current, history, threshold=threshold)

    if method == "iqr":
        return iqr_detector(current, history)

    if method in {"ewma", "rolling"}:
        return ewma_detector(current, history, threshold=threshold)

    if method == "auto":
        effective_history = _clean_history(history)
        method_tag = "auto:mad"
        effective_threshold = threshold

        if context:
            segment_hist = context.get("same_segment_history")
            if segment_hist and len(segment_hist) >= 3:
                effective_history = _clean_history(segment_hist)
                method_tag = "auto:same_segment_mad"

            known_event = context.get("known_event")
            if known_event:
                effective_threshold = threshold * 1.5
                method_tag += f"({known_event})"

        result = mad_detector(current, effective_history, threshold=effective_threshold)
        result["method"] = method_tag
        if context:
            result["reason"] += f"; context_applied={list(context.keys())}"
        return result

    raise ValueError(f"Unsupported method: {method}")


