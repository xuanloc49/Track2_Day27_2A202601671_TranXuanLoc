from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from observability.anomaly import zscore_detector


def approximate_token_lengths(texts: Iterable[str]) -> list[int]:
    """Token length proxy splitting by whitespace, filtering out None values."""
    return [len(str(t).split()) for t in texts if t is not None and str(t).strip()]


def detect_text_length_shift(
    current_texts: Iterable[str],
    baseline_batch_means: Iterable[float],
    *,
    threshold: float = 3.0,
) -> dict[str, Any]:
    lengths = approximate_token_lengths(current_texts)
    current_mean = float(np.mean(lengths)) if lengths else 0.0
    result = zscore_detector(current_mean, baseline_batch_means, threshold=threshold)
    result["metric"] = "mean_text_length"
    result["current_mean"] = current_mean
    return result


def detect_embedding_norm_shift(
    current_norms: Iterable[float],
    baseline_norms: Iterable[float],
    *,
    threshold: float = 3.0,
) -> dict[str, Any]:
    """Detects embedding norm / vector magnitude shift using statistical z-score."""
    try:
        cur = np.asarray(list(current_norms), dtype=float)
        base = np.asarray(list(baseline_norms), dtype=float)
        cur = cur[np.isfinite(cur)]
        base = base[np.isfinite(base)]
    except Exception:
        cur = np.array([], dtype=float)
        base = np.array([], dtype=float)

    if cur.size == 0 or base.size == 0:
        return {"is_anomaly": False, "score": 0.0, "method": "embedding_norm_zscore", "reason": "empty_input"}

    cur_mean = float(np.mean(cur))
    result = zscore_detector(cur_mean, base, threshold=threshold)
    result["metric"] = "mean_embedding_norm"
    result["current_mean"] = cur_mean
    result["baseline_mean"] = float(np.mean(base))
    return result
