"""Anomaly detection engine with robust statistics and context-aware automated selection.

Supports:
- Standard Z-Score detector for Gaussian metrics
- Median Absolute Deviation (MAD) for robust, outlier-resistant detection with zero-MAD handling
- Automated mode (auto) that incorporates segment history, day-of-week seasonality, and domain context
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def zscore_detector(current: float, history: Iterable[float], threshold: float = 3.0) -> dict[str, Any]:
    values = np.asarray(list(history), dtype=float)
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
    values = np.asarray(list(history), dtype=float)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "mad", "reason": "insufficient_history"}

    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))

    if mad == 0:
        # If historical values are identical or majority identical
        mean_dev = float(np.mean(np.abs(values - median)))
        if mean_dev == 0:
            # All values in history are identical
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
    - 'auto': context-aware engine leveraging seasonality, same-segment baselines, and events.
    """
    if method == "zscore":
        return zscore_detector(current, history, threshold=threshold)

    if method == "mad":
        return mad_detector(current, history, threshold=threshold)

    if method == "auto":
        effective_history = list(history)
        method_tag = "auto:mad"
        effective_threshold = threshold

        if context:
            # 1. Use same-segment / day-of-week history if available
            segment_hist = context.get("same_segment_history")
            if segment_hist and len(segment_hist) >= 3:
                effective_history = list(segment_hist)
                method_tag = "auto:same_segment_mad"

            # 2. Known event handling (e.g., flash sale, scheduled downtime)
            known_event = context.get("known_event")
            if known_event:
                # Broaden tolerance during known promotional or maintenance events
                effective_threshold = threshold * 1.5
                method_tag += f"({known_event})"

        # Prefer MAD for robust outlier rejection
        result = mad_detector(current, effective_history, threshold=effective_threshold)
        result["method"] = method_tag
        if context:
            result["reason"] += f"; context_applied={list(context.keys())}"
        return result

    raise ValueError(f"Unsupported method: {method}")

