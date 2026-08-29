# Incident Report — Data Reliability Game Day Post-Mortem

## Severity
**P1 — High Severity** (Ảnh hưởng trực tiếp đến tính toàn vẹn của CEO Revenue Dashboard và RAG Support Agent)

## Summary
Trong phiên vận hành Game Day, hệ thống pipeline báo cáo trạng thái `SUCCESS` nhưng bộ cảm biến Data Observability đa tầng đã phát hiện 3 sự cố nghiêm trọng tiềm ẩn:
1. **Duplicate Primary Keys** trong batch đơn hàng `orders.csv` gây nguy cơ phóng đại doanh thu.
2. **Partial Ingestion / Volume Drop** làm sụt giảm 75% lượng đơn hàng nạp vào nhưng không vi phạm cú pháp schema tĩnh.
3. **Stale Knowledge Base Documents** do độ trễ đồng bộ 3 giờ khiến RAG Support Agent trả lời sai chính sách hoàn tiền cho khách hàng.

## Detection
- **Signal 1:** `src/contract_validator` kích hoạt lỗi `unique` trên `order_id` (Severity: `critical`), chuyển trạng thái pipeline sang `block`.
- **Signal 2:** `observability/anomaly` phát hiện `row-count anomaly` với điểm số bất thường $MAD = 5.53 > 3.0$ trên batch 150 dòng (thay vì 600 dòng kỳ vọng).
- **Signal 3:** `src/contract_validator` và `observability/rag_metrics` phát hiện vi phạm Freshness (độ trễ 185 phút vượt ngưỡng 60 phút của SLA).
- **First observed time:** 2026-08-29 10:25:00 UTC

## Root Cause
1. **Inbound Data Contract Breach:** Dịch vụ phía đối tác gửi lại batch dữ liệu có chứa bản ghi trùng lặp khóa chính `order_id`.
2. **Upstream Ingestion Timeout:** Lỗi mạng ở pipeline nạp dữ liệu thô ngắt kết nối giữa chừng, chỉ tải được 25% số bản ghi trước khi gửi tín hiệu hoàn thành giả.
3. **KB Sync Pipeline Stall:** Job cập nhật tài liệu chính sách chăm sóc khách hàng bị treo cron, dẫn tới dữ liệu vector database bị cũ (stale policy).

## Evidence
1. **Contract Validation Log:** `unique` check trên cột `order_id` fail với `duplicate_rows=6` $\to$ kích hoạt Action `block`.
2. **Statistical Anomaly Evidence:** Lượng bản ghi giảm từ 600 xuống 150 $\to$ `method="auto:same_segment_mad"`, score $5.53 > 3.0$.
3. **dbt Unit Test Failure:** Phép JOIN giữa `completed_orders` và dimension `stg_customers` có nhiều active version làm nhân đôi doanh thu từ \$170 lên \$340.
4. **Freshness Lag:** `freshness_minutes = 185.0` vượt quá `max_delay_minutes = 60.0` trong `contracts/kb_contract.yaml`.
5. **SLO Breach & Multi-window Alert:** Burn rate đạt 14.4x trên cả 2 cửa sổ 1h và 6h, kích hoạt cảnh báo Page khẩn cấp.

## Blast Radius

```text
[stg_orders / orders.csv]
       │
       ▼
[fct_daily_revenue]
       │
       ▼
[CEO Revenue Dashboard] (Trực tiếp sai lệch quyết định tài chính)

[kb_documents.jsonl]
       │
       ▼
[Active Knowledge Base / Vector Index]
       │
       ▼
[Support RAG Agent] (Trả lời sai chính sách hoàn tiền cũ cho người dùng)
```

## Mitigation
1. **Quarantine & Ingestion Gate:** Kích hoạt cơ chế tự động chặn (`Action: block`) và đưa các dòng lỗi vào vùng cách ly (`quarantine_invalid_rows`), không cho chạy tiếp vào staging dbt.
2. **Re-ingestion & Deduplication:** Thực hiện retry toàn bộ batch đơn hàng gốc và áp dụng cửa sổ khử trùng lặp (deduplication window).
3. **KB Re-indexing:** Đồng bộ lại phiên bản tài liệu mới nhất và kích hoạt re-embedding vector index.

## Recovery
- Thực thi quy trình `make reset` đưa incoming data và KB documents về trạng thái chuẩn hóa.
- Tái đồng bộ dbt seeds và build lại toàn bộ marts: `dbt build --project-dir dbt_project`.

## Verification
- [x] **Contract healthy:** 0 failed checks trên cả `orders_contract.yaml` và `kb_contract.yaml`.
- [x] **dbt tests healthy:** 17/17 tests passing (bao gồm unique order_date, not_null, singular tests và dbt unit tests).
- [x] **Anomaly returned to expected range:** Volume 600 rows trong ngưỡng an toàn của baseline.
- [x] **SLO healthy / budget understood:** Burn rate về 0.0x, còn 100% Error Budget.
- [x] **Downstream output verified:** CEO Dashboard hiển thị chính xác doanh thu, RAG Agent phản hồi chính sách mới.

## Prevention / Action Items
| Action | Owner | Deadline | Why |
|---|---|---|---|
| Triển khai Ingestion Contract Gate chặn lỗi type drift & duplicate trước warehouse | Data Platform Team | 2026-09-05 | Ngăn chặn dữ liệu bẩn xâm nhập Data Lake |
| Thiết lập Anomaly Detection đa chiều với Seasonal MAD baseline trên toàn bộ bảng Marts | Data Observability Team | 2026-09-08 | Phát hiện sự cố volume drop mà không cần viết rule tĩnh |
| Bổ sung dbt Unit Test chống SCD dimension fan-out join vào CI/CD pipeline | Analytics Engineers | 2026-09-03 | Đảm bảo logic tính toán doanh thu không bao giờ bị nhân đôi |
| Tích hợp Google SRE Multi-window Burn-rate Alerting vào PagerDuty/Slack | Reliability Team | 2026-09-10 | Loại bỏ alert fatigue và cảnh báo kịp thời sự cố vi phạm SLA |

