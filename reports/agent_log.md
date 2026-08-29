# AI Agent Decision Log

## Decision 1: Strict Type & Freshness Validation in Data Contracts
- **Hypothesis:** Ép kiểu tự động (`pd.to_numeric(..., errors='coerce')`) che giấu Type Drift và làm mất dữ liệu âm thầm; thiếu kiểm tra Freshness khiến pipeline không phát hiện được batch dữ liệu bị trễ.
- **Prompt / request to agent:** Nâng cấp `src/contract_validator.py` hỗ trợ strict type checking, freshness validation dựa trên `contract['freshness']`, hỗ trợ cả schema `columns` và `fields`, cùng cơ chế phân loại action (block / warn / pass) và phân vùng quarantine.
- **Agent proposal:** Xây dựng hàm `_check_type` kiểm tra kiểu dữ liệu nghiêm ngặt cho integer, number, string, datetime, boolean; tính độ trễ `delay_minutes` so với `max_delay_minutes`; thêm hàm `quarantine_invalid_rows` và `get_action_for_issues`.
- **Evidence/test:** Chạy `pytest tests_public/test_contracts.py` $\to$ 5/5 tests passed bao gồm `test_type_drift_is_detected` và `test_stale_data_is_detected`.
- **Accept / reject / revise:** Accept.
- **Why:** Ngăn chặn triệt để type drift lọt vào warehouse và chặn đứng sự cố stale data trước khi downstream models chạy.

---

## Decision 2: Context-Aware Anomaly Detection (MAD & Day-of-Week Seasonality)
- **Hypothesis:** Z-score truyền thống giả định phân phối chuẩn (Gaussian) và bị sai lệch nặng khi có outlier lớn trong lịch sử hoặc khi dữ liệu có tính chu kỳ (ví dụ: ngày cuối tuần traffic tự nhiên giảm 60%).
- **Prompt / request to agent:** Nâng cấp `observability/anomaly.py` để xử lý triệt để trường hợp `mad == 0` và cài đặt `method="auto"` tận dụng context (`same_segment_history`, `day_of_week`, `known_event`).
- **Agent proposal:** Bổ sung fallback kiểm tra mean deviation cho zero-MAD; trong `auto` mode tự động ưu tiên `same_segment_history` (phân khúc cùng thứ trong tuần) kết hợp MAD detector để loại bỏ false positive vào cuối tuần.
- **Evidence/test:** `test_mad_zero_mad_identical_history_matches`, `test_mad_zero_mad_identical_history_differs`, `test_auto_seasonality_with_same_segment_history` đều pass. Bắt thành công kịch bản `volume_drop` (score = 5.53).
- **Accept / reject / revise:** Accept.
- **Why:** Giúp hệ thống phân biệt chính xác giữa giảm tải theo chu kỳ bình thường (weekend) và sự cố tụt volume thực sự (partial ingestion).

---

## Decision 3: Transitive BFS Downstream Lineage Traversal
- **Hypothesis:** Hàm tìm kiếm downstream ban đầu chỉ trả về direct children (bậc 1), dẫn đến việc đánh giá thiếu phạm vi ảnh hưởng (blast radius) khi xảy ra sự cố ở các node đầu nguồn.
- **Prompt / request to agent:** Cài đặt thuật toán duyệt đồ thị BFS hoàn chỉnh cho `get_column_downstream` và `get_downstream_assets` trong `observability/lineage.py`.
- **Agent proposal:** Sử dụng hàng đợi `collections.deque` và tập `seen` để duyệt toàn bộ các quan hệ phụ thuộc bắc cầu (transitive downstream), loại trừ node xuất phát.
- **Evidence/test:** `test_transitive_downstream_assets` và `test_transitive_column_downstream` pass với chuỗi 3 bậc (`orders.amount -> stg_orders.amount_usd -> fct_daily_revenue.daily_revenue -> ceo_dashboard.total_rev`).
- **Accept / reject / revise:** Accept.
- **Why:** Đảm bảo khi một cột/bảng bị lỗi, toàn bộ các bảng mart và dashboard tiêu thụ hạ nguồn đều được cảnh báo chính xác.

---

## Decision 4: Google SRE Multi-window Multi-burn-rate Alerting Policy
- **Hypothesis:** Cảnh báo dựa trên một cửa sổ thời gian đơn lẻ gây ra hiện tượng alert fatigue (nếu cửa sổ ngắn gặp transient spike) hoặc phát hiện quá trễ (nếu cửa sổ dài).
- **Prompt / request to agent:** Triển khai chính sách Multi-window Multi-burn-rate trong `observability/slo.py` theo Google SRE Workbook.
- **Agent proposal:** Cài đặt `evaluate_multiwindow_burn` kết hợp cả short window (1h) và long window (6h). Chỉ kích hoạt Page/P0 khi cả 2 cửa sổ đều vượt ngưỡng tiêu hao ngân sách (sustained fast burn), và hạ mức cảnh báo/suppress khi chỉ có transient short spike.
- **Evidence/test:** `test_sustained_fast_burn_pages` (short=15.0, long=15.0 $\to$ `page=True`, `severity="critical"`) và `test_transient_short_spike_does_not_page` (short=15.0, long=1.2 $\to$ `page=False`).
- **Accept / reject / revise:** Accept.
- **Why:** Loại bỏ 100% false pages do các đợt tăng vọt tải tức thời trong khi vẫn phản ứng tức thì khi có sự cố hệ thống kéo dài.

---

## Decision 5: dbt Data Tests & Unit Tests for SCD Revenue Inflation Prevention
- **Hypothesis:** Khi bảng chiều khách hàng (`stg_customers`) có nhiều hơn 1 bản ghi active cho cùng 1 `customer_id` (lỗi quản lý SCD Type 2), phép LEFT JOIN trong `fct_daily_revenue` sẽ bị nhân đôi số dòng và làm thổi phồng doanh thu mà không gây lỗi cú pháp SQL.
- **Prompt / request to agent:** Bổ sung generic data tests vào `schema.yml` và viết dbt unit test nhỏ nhất để expose & bảo vệ mô hình doanh thu.
- **Agent proposal:** Thêm `unique` data test trên cột `order_date` của `fct_daily_revenue`, thêm `completed_orders_sum_to_expected_revenue` dbt unit test.
- **Evidence/test:** `dbt build` chạy thành công toàn bộ 17/17 tasks (2 seeds, 3 models, 11 data tests, 1 unit test) trên DuckDB adapter.
- **Accept / reject / revise:** Accept.
- **Why:** Đảm bảo tính toàn vẹn của báo cáo tài chính cho CEO Dashboard ngay từ tầng dbt transformation.

