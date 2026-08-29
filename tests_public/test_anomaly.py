from student_api import detect_metric


def test_large_volume_drop_is_anomaly():
    history = [1000, 1010, 995, 1008, 1004, 1012, 998]
    result = detect_metric(300, history, method="zscore")
    assert result["is_anomaly"] is True


def test_stable_value_is_not_anomaly():
    history = [1000, 1010, 995, 1008, 1004, 1012, 998]
    result = detect_metric(1002, history, method="zscore")
    assert result["is_anomaly"] is False


def test_mad_zero_mad_identical_history_matches():
    history = [100, 100, 100, 100, 100]
    result = detect_metric(100, history, method="mad")
    assert result["is_anomaly"] is False


def test_mad_zero_mad_identical_history_differs():
    history = [100, 100, 100, 100, 100]
    result = detect_metric(120, history, method="mad")
    assert result["is_anomaly"] is True


def test_auto_seasonality_with_same_segment_history():
    # Overall history has high weekday traffic (~1000)
    general_history = [1000, 1020, 990, 1010, 1005]
    # Sunday history is naturally lower (~300)
    sunday_history = [310, 290, 305, 295, 300]
    # Current Sunday traffic of 300 should NOT be an anomaly when using segment history
    result = detect_metric(
        300,
        general_history,
        method="auto",
        context={"same_segment_history": sunday_history, "day_of_week": 6},
    )
    assert result["is_anomaly"] is False

