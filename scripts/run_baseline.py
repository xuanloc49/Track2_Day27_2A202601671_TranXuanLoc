#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from observability.anomaly import detect_anomaly
from observability.lineage import get_column_downstream, get_downstream_assets
from observability.rag_metrics import detect_text_length_shift
from observability.slo import calculate_slo, evaluate_multiwindow_burn
from src.contract_validator import failed_issues, get_action_for_issues, load_contract, validate_dataframe
from src.io_utils import load_jsonl


def main() -> None:
    orders = pd.read_csv(ROOT / "data" / "incoming" / "orders.csv")
    history = pd.read_csv(ROOT / "data" / "history" / "metrics_history.csv")
    orders_contract = load_contract(ROOT / "contracts" / "orders_contract.yaml")
    orders_issues = validate_dataframe(orders, orders_contract)
    orders_failed = failed_issues(orders_issues)
    orders_critical_failed = failed_issues(orders_issues, min_severity="critical")
    orders_action = get_action_for_issues(orders_issues)

    # Anomaly detection on daily order row count with seasonality awareness
    current_dow = datetime.now().weekday()
    segment = history.loc[history["day_of_week"] == current_dow, "row_count"].tail(8).tolist()
    row_history = segment if len(segment) >= 3 else history["row_count"].tail(14).tolist()
    row_result = detect_anomaly(
        len(orders),
        history["row_count"].tail(14).tolist(),
        method="auto",
        context={"metric_name": "row_count", "day_of_week": current_dow, "same_segment_history": segment},
    )

    updated = pd.to_datetime(orders["updated_at"], utc=True, errors="coerce")
    freshness_minutes = (
        pd.Timestamp(datetime.now(timezone.utc)) - updated.max()
    ).total_seconds() / 60.0

    # Knowledge Base validation & text length signal
    docs = load_jsonl(ROOT / "data" / "incoming" / "kb_documents.jsonl")
    kb_df = pd.DataFrame(docs)
    kb_contract = load_contract(ROOT / "contracts" / "kb_contract.yaml")
    kb_issues = validate_dataframe(kb_df, kb_contract)
    kb_failed = failed_issues(kb_issues)

    text_result = detect_text_length_shift(
        [d["content"] for d in docs], history["mean_text_length"].tail(14).tolist()
    )

    # SLO & Burn-rate evaluations
    bad = 1 if (orders_critical_failed or kb_failed) else 0
    contract_slo = calculate_slo(0.999, bad_events=bad, total_events=1)
    
    # Example multi-window burn check:
    burn_1h = 14.4 if bad > 0 else 0.0
    burn_6h = 14.4 if bad > 0 else 0.0
    burn_alert = evaluate_multiwindow_burn(short_window_burn=burn_1h, long_window_burn=burn_6h)

    with open(ROOT / "data" / "baseline" / "lineage_graph.json", "r", encoding="utf-8") as f:
        lineage = json.load(f)["dataset_lineage"]
    blast_radius = get_downstream_assets(lineage, "stg_orders")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "orders_rows": int(len(orders)),
        "failed_contract_checks": len(orders_failed),
        "critical_contract_failures": len(orders_critical_failed),
        "orders_pipeline_action": orders_action,
        "kb_failed_contract_checks": len(kb_failed),
        "row_count_anomaly": row_result,
        "freshness_minutes": freshness_minutes,
        "kb_text_length_signal": text_result,
        "contract_slo": contract_slo,
        "multiwindow_burn_alert": burn_alert,
        "sample_blast_radius_from_stg_orders": blast_radius,
    }
    out = ROOT / "reports" / "latest_metrics.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("=== DATA RELIABILITY BASELINE ===")
    print(f"orders rows              : {len(orders)}")
    print(f"contract failed checks   : {len(orders_failed)}")
    print(f"critical contract fails  : {len(orders_critical_failed)}")
    print(f"orders action            : {orders_action}")
    print(f"KB contract failed       : {len(kb_failed)}")
    print(f"row-count anomaly        : {row_result['is_anomaly']} ({row_result['method']}, score={row_result['score']:.2f})")
    print(f"freshness minutes        : {freshness_minutes:.1f}")
    print(f"KB length anomaly        : {text_result['is_anomaly']}")
    print(f"multiwindow page alert   : {burn_alert['page']} ({burn_alert['severity']})")
    print(f"sample blast radius      : {', '.join(blast_radius)}")
    print(f"report                   : {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

