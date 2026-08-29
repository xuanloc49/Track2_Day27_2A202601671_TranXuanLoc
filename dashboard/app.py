from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "latest_metrics.json"
HISTORY = ROOT / "data" / "history" / "metrics_history.csv"

st.set_page_config(page_title="Data & AI Reliability Center", layout="wide", page_icon="🛡️")
st.title("🛡️ Data & AI Reliability Observability Dashboard")
st.caption("Game Day Incident Triage & Reliability Management")

if not REPORT.exists():
    st.warning("Run `make baseline` first to generate reports/latest_metrics.json")
    st.stop()

report = json.loads(REPORT.read_text(encoding="utf-8"))

# Top-level Health KPIs
pipeline_action = report.get("orders_pipeline_action", "pass")
if pipeline_action == "block":
    st.error("🚨 **PIPELINE BLOCKED**: Critical data contract failures detected. Ingestion halted.")
elif pipeline_action == "warn":
    st.warning("⚠️ **PIPELINE WARNING**: Non-critical warnings detected.")
else:
    st.success("✅ **PIPELINE HEALTHY**: All contract checks and invariants passing.")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Orders Ingested", report["orders_rows"])
c2.metric("Freshness Lag", f"{report['freshness_minutes']:.1f} min")
c3.metric("Failed Checks", report["failed_contract_checks"])
c4.metric("Critical Failures", report["critical_contract_failures"])

slo_data = report.get("contract_slo", {})
remaining_budget = slo_data.get("remaining_error_budget_fraction", 1.0) * 100
c5.metric("Remaining Budget", f"{remaining_budget:.1f}%", delta=f"-{slo_data.get('burn_rate', 0.0):.1f}x Burn" if slo_data.get('burn_rate', 0.0) > 0 else "0.0x")

# Reliability Signals & Multi-Window Burn
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("📊 Anomaly & Shift Signals")
    row_anomaly = report.get("row_count_anomaly", {})
    if row_anomaly.get("is_anomaly"):
        st.error(f"⚠️ Volume Anomaly Detected ({row_anomaly.get('method')} | Score: {row_anomaly.get('score', 0):.2f})")
    else:
        st.success(f"✓ Volume In Range ({row_anomaly.get('method')} | Score: {row_anomaly.get('score', 0):.2f})")

    st.json({
        "row_count_anomaly": row_anomaly,
        "kb_text_length_signal": report.get("kb_text_length_signal"),
        "multiwindow_burn_alert": report.get("multiwindow_burn_alert"),
    })

with col_right:
    st.subheader("🎯 Service Level Objectives (SLO)")
    st.json(slo_data)
    
    burn_alert = report.get("multiwindow_burn_alert", {})
    if burn_alert.get("page"):
        st.error(f"🚨 **PAGING ALERT TRIGGERED**: {burn_alert.get('reason')} (Severity: {burn_alert.get('severity')})")
    else:
        st.info(f"ℹ️ Alert Status: No Page Required ({burn_alert.get('reason', 'healthy')})")

st.divider()

# Historical Trends & Lineage
col_hist, col_lineage = st.columns([2, 1])

with col_hist:
    st.subheader("📈 Historical Ingestion Volume Trend")
    history = pd.read_csv(HISTORY)
    st.line_chart(history.set_index("date")[["row_count", "mean_text_length"]])

with col_lineage:
    st.subheader("🕸️ Blast Radius Lineage")
    st.markdown("**Root Source**: `stg_orders`")
    blast_radius = report.get("sample_blast_radius_from_stg_orders", [])
    for idx, asset in enumerate(blast_radius, 1):
        st.markdown(f"**Step {idx} Downstream**: `{asset}`")
    st.caption("Downstream impacts traced via BFS graph traversal.")

