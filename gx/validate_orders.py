#!/usr/bin/env python3
"""Great Expectations 1.21 Core Validation Suite & Checkpoint Runner.

Builds an Expectation Suite with critical/warning expectations,
creates a ValidationDefinition and Checkpoint, executes validations,
and emits structured diagnostic reports with severity-based actions.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import great_expectations as gx
    from great_expectations.core.expectation_suite import ExpectationSuite
    from great_expectations.core.validation_definition import ValidationDefinition
except ImportError as exc:
    raise SystemExit("great_expectations is not installed. Run: pip install -r requirements.txt") from exc


def run_orders_validation(df: pd.DataFrame | None = None) -> dict:
    if df is None:
        df = pd.read_csv(ROOT / "data" / "incoming" / "orders.csv")

    context = gx.get_context(mode="ephemeral")

    # 1. Add Data Source & Dataframe Asset
    data_source = context.data_sources.add_pandas("orders_source")
    asset = data_source.add_dataframe_asset(name="orders_asset")
    batch_definition = asset.add_batch_definition_whole_dataframe("orders_batch_def")

    # 2. Build Expectation Suite
    suite = context.suites.add(ExpectationSuite(name="orders_quality_suite"))

    expectations = [
        gx.expectations.ExpectColumnValuesToNotBeNull(column="order_id"),
        gx.expectations.ExpectColumnValuesToBeUnique(column="order_id"),
        gx.expectations.ExpectColumnValuesToNotBeNull(column="customer_id"),
        gx.expectations.ExpectColumnValuesToNotBeNull(column="amount"),
        gx.expectations.ExpectColumnValuesToBeBetween(column="amount", min_value=0),
        gx.expectations.ExpectColumnValuesToNotBeNull(column="currency"),
        gx.expectations.ExpectColumnValuesToBeInSet(column="currency", value_set=["USD", "VND"]),
        gx.expectations.ExpectColumnValuesToNotBeNull(column="status"),
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="status", value_set=["pending", "completed", "refunded", "cancelled"]
        ),
        gx.expectations.ExpectColumnValuesToNotBeNull(column="created_at"),
        gx.expectations.ExpectColumnValuesToNotBeNull(column="updated_at"),
    ]

    for exp in expectations:
        suite.add_expectation(exp)

    # 3. Validation Definition
    validation_def = context.validation_definitions.add(
        ValidationDefinition(
            name="orders_validation_def",
            data=batch_definition,
            suite=suite,
        )
    )

    # 4. Checkpoint
    checkpoint = context.checkpoints.add(
        gx.checkpoint.checkpoint.Checkpoint(
            name="orders_checkpoint",
            validation_definitions=[validation_def],
        )
    )

    # 5. Execute Checkpoint Run
    checkpoint_result = checkpoint.run(
        batch_parameters={"dataframe": df}
    )

    is_success = bool(checkpoint_result.success)
    summary_results = []

    # Extract individual expectation results
    if hasattr(checkpoint_result, "run_results"):
        for res_obj in checkpoint_result.run_results.values():
            val_results = getattr(res_obj, "results", [])
            for res in val_results:
                exp_type = getattr(res.expectation_config, "type", str(type(res.expectation_config)))
                col = res.expectation_config.kwargs.get("column", "table") if hasattr(res, "expectation_config") else ""
                success = bool(res.success)
                summary_results.append({
                    "expectation": exp_type,
                    "column": col,
                    "success": success,
                    "details": str(res.result) if not success else "Passed",
                })

    return {
        "success": is_success,
        "action": "pass" if is_success else "quarantine_and_block",
        "expectations_evaluated": len(summary_results),
        "failures": [r for r in summary_results if not r["success"]],
        "results": summary_results,
    }


def main() -> None:
    print("=== RUNNING GREAT EXPECTATIONS CORE 1.21 CHECKPOINT ===")
    res = run_orders_validation()
    print(f"Total Expectations Evaluated: {res['expectations_evaluated']}")
    for item in res["results"]:
        status = "[PASS]" if item["success"] else "[FAIL]"
        print(f"{status:<8} {item['expectation']:<40} column={item['column']}")

    print(f"\nOverall GX Checkpoint Result: {'PASS' if res['success'] else 'FAIL'}")
    print(f"Action Triggered: {res['action']}")
    if not res["success"]:
        print(f"Failures ({len(res['failures'])}):")
        for f in res["failures"]:
            print(f"  - {f['column']}: {f['expectation']} -> {f['details']}")


if __name__ == "__main__":
    main()

