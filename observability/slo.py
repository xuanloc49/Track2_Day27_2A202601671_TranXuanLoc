from __future__ import annotations

from typing import Any


def calculate_slo(target: float, bad_events: int, total_events: int) -> dict[str, Any]:
    if not 0 < target < 1:
        raise ValueError("target must be between 0 and 1 (exclusive)")
    if bad_events < 0 or total_events < 0 or bad_events > total_events:
        raise ValueError("invalid event counts")
    allowed_bad_rate = 1.0 - target
    if total_events == 0:
        return {
            "target": target,
            "actual_bad_rate": 0.0,
            "allowed_bad_rate": allowed_bad_rate,
            "burn_rate": 0.0,
            "remaining_error_budget_fraction": 1.0,
            "breached": False,
        }
    actual_bad_rate = bad_events / total_events
    burn_rate = actual_bad_rate / allowed_bad_rate
    consumed_fraction = min(1.0, actual_bad_rate / allowed_bad_rate)
    return {
        "target": target,
        "actual_bad_rate": actual_bad_rate,
        "allowed_bad_rate": allowed_bad_rate,
        "burn_rate": burn_rate,
        "remaining_error_budget_fraction": max(0.0, 1.0 - consumed_fraction),
        "breached": bool(actual_bad_rate > allowed_bad_rate),
    }


def evaluate_multiwindow_burn(
    *,
    short_window_burn: float,
    long_window_burn: float,
    policy: str = "google_sre",
) -> dict[str, Any]:
    """Evaluates multi-window multi-burn-rate alerting according to Google SRE best practices.

    Prevents alert fatigue by ensuring:
    - Sustained fast burn (both short & long window elevated) -> Page (P1/Critical)
    - Sustained slow/moderate burn -> Ticket/Warning (P2/Warning)
    - Transient short spike (short window high, long window low) -> No page (suppressed)
    """
    short_burn = float(short_window_burn)
    long_burn = float(long_window_burn)

    # Sustained Critical Fast Burn (e.g., >= 14.4x in 1h and 6h, or >= 6.0x in both)
    if short_burn >= 14.4 and long_burn >= 14.4:
        return {
            "page": True,
            "severity": "critical",
            "reason": "sustained_critical_fast_burn_p0",
            "short_window_burn": short_burn,
            "long_window_burn": long_burn,
            "policy": policy,
        }
    if short_burn >= 6.0 and long_burn >= 6.0:
        return {
            "page": True,
            "severity": "critical",
            "reason": "sustained_high_burn_page",
            "short_window_burn": short_burn,
            "long_window_burn": long_burn,
            "policy": policy,
        }

    # Transient Short Spike: short window is elevated but long window is not sustained
    if short_burn >= 6.0 and long_burn < 3.0:
        return {
            "page": False,
            "severity": "warning",
            "reason": "transient_spike_suppressed_no_page",
            "short_window_burn": short_burn,
            "long_window_burn": long_burn,
            "policy": policy,
        }

    # Sustained Moderate Burn (1.0x to 3.0x in both windows)
    if short_burn >= 1.0 and long_burn >= 1.0:
        return {
            "page": False,
            "severity": "warning",
            "reason": "sustained_moderate_burn_ticket",
            "short_window_burn": short_burn,
            "long_window_burn": long_burn,
            "policy": policy,
        }

    # Healthy
    return {
        "page": False,
        "severity": "info",
        "reason": "burn_rate_healthy",
        "short_window_burn": short_burn,
        "long_window_burn": long_burn,
        "policy": policy,
    }

