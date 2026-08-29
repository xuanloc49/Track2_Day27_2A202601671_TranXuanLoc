"""Anomaly detection engine.

Z-score is deliberately the default baseline. In auto mode, same_segment_history
(seasonality) takes precedence over rolling baseline, and known_event is suppressed.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def _numeric_history(history: Iterable[float]) -> np.ndarray:
    """Convert an iterable to finite observations only."""
    try:
        values = np.asarray(list(history), dtype=float)
        return values[np.isfinite(values)]
    except Exception:
        return np.array([], dtype=float)


def zscore_detector(current: float, history: Iterable[float], threshold: float = 3.0) -> dict[str, Any]:
    values = _numeric_history(history)
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
    """Detect outliers with the robust modified Z-score based on median/MAD."""
    values = _numeric_history(history)
    if values.size < 5:
        return {"is_anomaly": False, "score": 0.0, "method": "mad", "reason": "insufficient_history"}
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if mad == 0:
        score = 0.0 if float(current) == median else float("inf")
        return {
            "is_anomaly": bool(score > threshold),
            "score": score,
            "method": "mad",
            "reason": f"median={median:.3f}, mad=0; threshold={threshold}",
        }
    modified_z = 0.6745 * abs(float(current) - median) / mad
    return {
        "is_anomaly": bool(modified_z > threshold),
        "score": float(modified_z),
        "method": "mad",
        "reason": f"median={median:.3f}, mad={mad:.3f}, threshold={threshold}",
    }


def detect_anomaly(
    current: float,
    history: Iterable[float],
    *,
    method: str = "auto",
    threshold: float = 3.0,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Detect anomalies using an explicit or context-aware robust baseline."""
    if method == "mad":
        return mad_detector(current, history, threshold=threshold)
    if method == "zscore":
        return zscore_detector(current, history, threshold=threshold)
    if method == "auto":
        context = context or {}
        if context.get("known_event"):
            return {
                "is_anomaly": False,
                "score": 0.0,
                "method": "auto:known_event",
                "reason": f"suppressed_by_known_event={context['known_event']}",
            }

        segment = _numeric_history(context.get("same_segment_history", []))
        if segment.size >= 5:
            result = mad_detector(current, segment, threshold=threshold)
            result["method"] = "auto:mad_same_segment"
            result["reason"] += f"; segment_size={segment.size}"
            return result

        rolling = _numeric_history(history)[-14:]
        result = mad_detector(current, rolling, threshold=threshold)
        if rolling.size < 5:
            result = zscore_detector(current, rolling, threshold=threshold)
            result["method"] = "auto:zscore_short_history"
        else:
            result["method"] = "auto:mad_rolling"
        result["reason"] += f"; rolling_window={rolling.size}"
        return result
    raise ValueError(f"Unsupported method: {method}")




