"""Contract validator with strict type checking, freshness, and severity-aware actions.

Supports both column-based (orders) and field-based (knowledge base) contracts,
type drift detection, freshness verification, and automated quarantine.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


def _issue(
    check: str,
    *,
    column: str | None,
    severity: str,
    passed: bool,
    details: str,
) -> dict[str, Any]:
    return {
        "check": check,
        "column": column,
        "severity": severity,
        "passed": bool(passed),
        "details": details,
    }


def load_contract(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _check_type(series: pd.Series, declared_type: str) -> tuple[bool, int, str]:
    """Strictly checks if series values conform to declared type without hiding drift."""
    non_null = series.dropna()
    if non_null.empty:
        return True, 0, "all_null_or_empty"

    dtype_str = declared_type.lower().strip()

    if dtype_str in {"integer", "int", "bigint", "int64", "int32"}:
        coerced = pd.to_numeric(non_null, errors="coerce")
        # Invalid if non-convertible or contains non-integer decimal
        invalid_mask = coerced.isna() | (coerced % 1 != 0)
        invalid_count = int(invalid_mask.sum())
        return (invalid_count == 0), invalid_count, f"invalid_integer_count={invalid_count}"

    elif dtype_str in {"number", "float", "double", "numeric", "decimal"}:
        coerced = pd.to_numeric(non_null, errors="coerce")
        invalid_count = int(coerced.isna().sum())
        return (invalid_count == 0), invalid_count, f"invalid_number_count={invalid_count}"

    elif dtype_str in {"string", "str", "varchar", "text"}:
        return True, 0, "string_ok"

    elif dtype_str in {"datetime", "timestamp", "date"}:
        coerced = pd.to_datetime(non_null, errors="coerce", utc=True)
        invalid_count = int(coerced.isna().sum())
        return (invalid_count == 0), invalid_count, f"invalid_datetime_count={invalid_count}"

    elif dtype_str in {"boolean", "bool"}:
        valid_bools = {True, False, 1, 0, "true", "false", "True", "False", "1", "0", 1.0, 0.0}
        invalid_mask = ~non_null.isin(valid_bools)
        invalid_count = int(invalid_mask.sum())
        return (invalid_count == 0), invalid_count, f"invalid_boolean_count={invalid_count}"

    return True, 0, f"unhandled_type_{declared_type}"


def validate_dataframe(
    df: pd.DataFrame,
    contract: dict[str, Any],
    *,
    reference_time: datetime | pd.Timestamp | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    columns = contract.get("columns") or contract.get("fields") or {}

    for column, rules in columns.items():
        if isinstance(rules, str):
            rules = {"type": rules}

        severity = rules.get("severity", "warning")
        required = bool(rules.get("required", False))

        if column not in df.columns:
            if required:
                issues.append(
                    _issue(
                        "required_column",
                        column=column,
                        severity=severity,
                        passed=False,
                        details=f"Missing required column: {column}",
                    )
                )
            continue

        series = df[column]

        # 1. Not Null Check
        if required:
            null_count = int(series.isna().sum())
            issues.append(
                _issue(
                    "not_null",
                    column=column,
                    severity=severity,
                    passed=(null_count == 0),
                    details=f"null_count={null_count}",
                )
            )

        # 2. Unique Check
        if rules.get("unique"):
            duplicate_count = int(series.duplicated(keep=False).sum())
            issues.append(
                _issue(
                    "unique",
                    column=column,
                    severity=severity,
                    passed=(duplicate_count == 0),
                    details=f"duplicate_rows={duplicate_count}",
                )
            )

        # 3. Data Type Validation
        if "type" in rules:
            declared_type = rules["type"]
            passed_type, invalid_count, type_details = _check_type(series, declared_type)
            issues.append(
                _issue(
                    "type",
                    column=column,
                    severity=severity,
                    passed=passed_type,
                    details=f"expected_type={declared_type}; {type_details}",
                )
            )

        # 4. Accepted Values Check
        accepted = rules.get("accepted_values")
        if accepted is not None:
            invalid_mask = series.notna() & ~series.isin(accepted)
            invalid_count = int(invalid_mask.sum())
            issues.append(
                _issue(
                    "accepted_values",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}; accepted={accepted}",
                )
            )

        # 5. Range Check (min / max)
        if "min" in rules or "max" in rules:
            numeric = pd.to_numeric(series, errors="coerce")
            invalid = pd.Series(False, index=series.index)
            if "min" in rules:
                invalid |= numeric < rules["min"]
            if "max" in rules:
                invalid |= numeric > rules["max"]
            invalid_count = int((invalid | (series.notna() & numeric.isna())).sum())
            issues.append(
                _issue(
                    "range",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}",
                )
            )

        # 6. Min Length Check
        if "min_length" in rules:
            min_len = int(rules["min_length"])
            text_lens = series.dropna().astype(str).str.len()
            short_count = int((text_lens < min_len).sum())
            issues.append(
                _issue(
                    "min_length",
                    column=column,
                    severity=severity,
                    passed=(short_count == 0),
                    details=f"short_count={short_count}; min_length={min_len}",
                )
            )

    # 7. Dataset Freshness Validation
    freshness = contract.get("freshness")
    if freshness and isinstance(freshness, dict):
        freshness_col = freshness.get("column")
        max_delay = float(freshness.get("max_delay_minutes", 60))
        freshness_severity = freshness.get("severity", "warning")

        if freshness_col and freshness_col in df.columns:
            ts_series = pd.to_datetime(df[freshness_col], utc=True, errors="coerce").dropna()
            if not ts_series.empty:
                latest_ts = ts_series.max()
                now_utc = (
                    pd.Timestamp(reference_time)
                    if reference_time is not None
                    else pd.Timestamp(datetime.now(timezone.utc))
                )
                delay_minutes = (now_utc - latest_ts).total_seconds() / 60.0
                # Stale check: delay exceeds max_delay
                is_fresh = delay_minutes <= max_delay
                issues.append(
                    _issue(
                        "freshness",
                        column=freshness_col,
                        severity=freshness_severity,
                        passed=bool(is_fresh),
                        details=f"delay_minutes={delay_minutes:.1f}; max_delay_minutes={max_delay}",
                    )
                )
            else:
                issues.append(
                    _issue(
                        "freshness",
                        column=freshness_col,
                        severity=freshness_severity,
                        passed=False,
                        details="No parseable timestamps found in freshness column",
                    )
                )
        elif freshness_col:
            issues.append(
                _issue(
                    "freshness",
                    column=freshness_col,
                    severity=freshness_severity,
                    passed=False,
                    details=f"Freshness column '{freshness_col}' not found in dataframe",
                )
            )

    return issues


def failed_issues(issues: list[dict[str, Any]], min_severity: str | None = None) -> list[dict[str, Any]]:
    failed = [i for i in issues if not i.get("passed", False)]
    if min_severity is None:
        return failed
    order = {"info": 0, "warning": 1, "critical": 2}
    threshold = order.get(min_severity, 1)
    return [i for i in failed if order.get(i.get("severity", "warning"), 1) >= threshold]


def get_action_for_issues(issues: list[dict[str, Any]]) -> str:
    """Returns 'block' for critical failures, 'warn' for warnings, 'pass' otherwise."""
    failed = [i for i in issues if not i.get("passed", True)]
    if any(i.get("severity") == "critical" for i in failed):
        return "block"
    if any(i.get("severity") == "warning" for i in failed):
        return "warn"
    return "pass"


def quarantine_invalid_rows(
    df: pd.DataFrame,
    contract: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Partition dataframe into (valid_df, quarantined_df) based on row-level contract violations."""
    if df.empty:
        return df.copy(), df.copy()

    columns = contract.get("columns") or contract.get("fields") or {}
    bad_mask = pd.Series(False, index=df.index)

    for col, rules in columns.items():
        if col not in df.columns:
            continue
        series = df[col]
        if rules.get("required"):
            bad_mask |= series.isna()
        if rules.get("unique"):
            bad_mask |= series.duplicated(keep=False)
        if "accepted_values" in rules:
            bad_mask |= series.notna() & ~series.isin(rules["accepted_values"])
        if "min" in rules:
            num = pd.to_numeric(series, errors="coerce")
            bad_mask |= (series.notna() & num.isna()) | (num < rules["min"])
        if "max" in rules:
            num = pd.to_numeric(series, errors="coerce")
            bad_mask |= (series.notna() & num.isna()) | (num > rules["max"])

    return df[~bad_mask].copy(), df[bad_mask].copy()

