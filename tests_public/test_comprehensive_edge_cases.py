import math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from student_api import (
    column_downstream,
    detect_distribution,
    detect_metric,
    downstream_assets,
    multiwindow_burn,
    rag_embedding_shift,
    rag_length_shift,
    slo_status,
    validate_orders,
)
from src.contract_validator import (
    get_action_for_issues,
    load_contract,
    quarantine_invalid_rows,
    validate_dataframe,
)

ROOT = Path(__file__).resolve().parents[1]
ORDERS_CONTRACT_PATH = ROOT / 'contracts' / 'orders_contract.yaml'
KB_CONTRACT_PATH = ROOT / 'contracts' / 'kb_contract.yaml'


def test_contract_empty_dataframe():
    empty_df = pd.DataFrame(columns=['order_id', 'customer_id', 'amount', 'currency', 'status', 'created_at', 'updated_at'])
    issues = validate_orders(empty_df, ORDERS_CONTRACT_PATH)
    assert isinstance(issues, list)


def test_contract_missing_required_column():
    df = pd.DataFrame([{'customer_id': 'C1', 'amount': 10.0}])
    issues = validate_orders(df, ORDERS_CONTRACT_PATH)
    missing_order_id = [i for i in issues if i['check'] == 'required_column' and i['column'] == 'order_id']
    assert len(missing_order_id) == 1
    assert missing_order_id[0]['severity'] == 'critical'
    assert missing_order_id[0]['passed'] is False


def test_contract_dict_passed_directly():
    contract_dict = {
        'columns': {
            'user_id': {'type': 'integer', 'required': True, 'unique': True, 'severity': 'critical'},
            'score': {'type': 'number', 'min': 0, 'max': 100, 'severity': 'warning'},
        }
    }
    df = pd.DataFrame([{'user_id': 1, 'score': 85.5}, {'user_id': 2, 'score': 92.0}])
    issues = validate_orders(df, contract_dict)
    assert all(i['passed'] for i in issues)


def test_contract_quarantine_and_actions():
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    df = pd.DataFrame([
        {'order_id': 1, 'customer_id': 'C1', 'amount': 50.0, 'currency': 'USD', 'status': 'completed', 'created_at': now, 'updated_at': now},
        {'order_id': 1, 'customer_id': 'C2', 'amount': -10.0, 'currency': 'INVALID', 'status': 'pending', 'created_at': now, 'updated_at': now},
    ])
    contract = load_contract(ORDERS_CONTRACT_PATH)
    clean_df, bad_df = quarantine_invalid_rows(df, contract)
    assert len(clean_df) == 0
    assert len(bad_df) == 2

    issues = validate_dataframe(df, contract)
    action = get_action_for_issues(issues)
    assert action == 'block'


def test_anomaly_nan_and_inf_in_history():
    history = [100.0, np.nan, 105.0, float('inf'), 98.0, 102.0, 101.0]
    result = detect_metric(100.0, history, method='zscore')
    assert result['is_anomaly'] is False
    assert math.isfinite(result['score'])


def test_anomaly_known_event_suppression():
    history = [100.0, 102.0, 98.0, 101.0, 99.0, 100.0, 103.0]
    res = detect_metric(500.0, history, method='auto', context={'known_event': 'flash_sale'})
    assert res['is_anomaly'] is False
    assert res['score'] == 0.0
    assert res['method'] == 'auto:known_event'


def test_anomaly_insufficient_history():
    history = [100]
    res = detect_metric(150, history, method='auto')
    assert res['is_anomaly'] is False
    assert res['score'] == 0.0


def test_distribution_identical_samples():
    base = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    cur = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    res = detect_distribution(cur, base)
    assert res['is_anomaly'] is False
    assert res['score'] < 1.0


def test_distribution_empty_current_is_anomaly():
    res = detect_distribution([], [1.0, 2.0, 3.0, 4.0, 5.0])
    assert res['is_anomaly'] is True
    assert math.isinf(res['score'])


def test_lineage_cyclic_graph():
    cyclic_graph = {
        'A': ['B'],
        'B': ['C'],
        'C': ['A', 'D'],
        'D': [],
    }
    downstream = downstream_assets(cyclic_graph, 'A')
    assert set(downstream) == {'B', 'C', 'D'}


def test_lineage_nonexistent_start():
    graph = {'A': ['B'], 'B': ['C']}
    assert downstream_assets(graph, 'UNKNOWN_NODE') == []
    assert column_downstream(graph, 'UNKNOWN_NODE') == []


def test_lineage_deep_transitive():
    graph = {f'node_{i}': [f'node_{i+1}'] for i in range(10)}
    downstream = downstream_assets(graph, 'node_0')
    assert downstream == [f'node_{i}' for i in range(1, 11)]


def test_slo_100_percent_bad_events():
    res = slo_status(0.99, bad_events=100, total_events=100)
    assert res['actual_bad_rate'] == 1.0
    assert res['burn_rate'] == pytest.approx(100.0)
    assert res['remaining_error_budget_fraction'] == 0.0
    assert res['breached'] is True


def test_multiwindow_sustained_moderate_burn():
    res = multiwindow_burn(short_window_burn=7.0, long_window_burn=4.0)
    assert res['page'] is True
    assert res['severity'] == 'warning'
    assert 'sustained_elevated_burn' in res['reason']


def test_multiwindow_healthy():
    res = multiwindow_burn(short_window_burn=0.1, long_window_burn=0.2)
    assert res['page'] is False
    assert res['severity'] == 'info'


def test_rag_length_shift_handles_empty_and_none():
    base_means = [20.0, 21.0, 20.5, 19.8, 20.2]
    current = ['This is a normal sentence with some words.', None, '', 'Another test sentence here.']
    res = rag_length_shift(current, base_means)
    assert 'current_mean' in res
    assert math.isfinite(res['current_mean'])


def test_rag_embedding_shift_handles_nan_and_empty():
    base_norms = [1.0, 1.01, 0.99, 1.02, 0.98, 1.0, 1.01]
    current = [0.1, 0.15, 0.12, 0.11, 0.14]
    res = rag_embedding_shift(current, base_norms)
    assert res['is_anomaly'] is True
