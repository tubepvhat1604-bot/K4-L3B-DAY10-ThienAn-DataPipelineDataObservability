# Corruption & Repair Report — Baseline vs Corrupted vs Repaired

_Generated at 2026-09-26T03:53:12.782367+00:00 bởi `script/run_corruption_flow.py` (số liệu sinh tự động, không sửa tay)._

Cả 3 trạng thái được đánh giá trên **cùng một** `data/eval/test_set.json`, cùng embedding model và cùng `top_k`.

## 1. Bảng đối chiếu 3 trạng thái

| Metric | Baseline | Corrupted | Repaired | Δ Corrupted | Δ Repaired |
| --- | --- | --- | --- | --- | --- |
| Retrieval Hit Rate | 1.000 | 0.700 | 1.000 | -0.300 | +0.000 |
| Mean Token F1 | 1.000 | 0.674 | 1.000 | -0.326 | +0.000 |
| Judge Accuracy | 1.000 | 0.600 | 1.000 | -0.400 | +0.000 |
| Mean Judge Score (1-5) | 5.000 | 3.900 | 5.000 | -1.100 | +0.000 |

### Trạng thái dữ liệu

| Metric | Baseline | Corrupted | Repaired | Δ Corrupted | Δ Repaired |
| --- | --- | --- | --- | --- | --- |
| Rows | 24 | 23 | 24 |  |  |
| Quality Gate (GX 1.x) | ✅ PASS | ❌ FAIL | ✅ PASS |  |  |
| Freshness SLA | ✅ Fresh | ❌ Stale | ✅ Fresh |  |  |

### Theo loại câu hỏi

| Question type | Baseline (Hit / F1) | Corrupted (Hit / F1) | Repaired (Hit / F1) |
| --- | --- | --- | --- |
| summary | 1.00 / 1.00 | 0.67 / 0.25 | 1.00 / 1.00 |
| authors | 1.00 / 1.00 | 0.67 / 1.00 | 1.00 / 1.00 |
| date | 1.00 / 1.00 | 0.50 / 0.50 | 1.00 / 1.00 |
| categories | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |

## 2. Các kịch bản lỗi đã tiêm

| Scenario | Mô tả | Rows ảnh hưởng |
| --- | --- | --- |
| drop_latest_records | Bỏ rơi các bài báo mới nhất (ingestion fail) | 5 |
| blank_summary | Xóa trắng summary (scrape rỗng) | 4 |
| inject_noise | Chèn ký tự rác vào summary (lỗi encoding/HTML) | 4 |
| truncate_title | Cắt title còn 6 ký tự | 4 |
| stale_date | Lùi published về 365 ngày trước | 6 |
| duplicate_rows | Nhân bản dòng (ingest 2 lần) | 4 |

## 3. Data Quality Gate theo từng expectation

| Expectation | Column | Baseline | Corrupted | Repaired |
| --- | --- | --- | --- | --- |
| expect_table_row_count_to_be_between | (table) | ✅ | ✅ | ✅ |
| expect_column_values_to_not_be_null | paper_id | ✅ | ✅ | ✅ |
| expect_column_values_to_be_unique | paper_id | ✅ | ❌ (8 lỗi) | ✅ |
| expect_column_values_to_not_be_null | title | ✅ | ✅ | ✅ |
| expect_column_value_lengths_to_be_between | title | ✅ | ❌ (5 lỗi) | ✅ |
| expect_column_values_to_not_be_null | text_for_embedding | ✅ | ✅ | ✅ |
| expect_column_value_lengths_to_be_between | summary | ✅ | ❌ (5 lỗi) | ✅ |

## 4. Freshness SLA

| Freshness | Baseline | Corrupted | Repaired |
| --- | --- | --- | --- |
| Total rows | 24 | 23 | 24 |
| Stale rows (age > threshold) | 1 | 6 | 1 |
| Stale ratio | 0.042 | 0.261 | 0.042 |
| Max stale ratio (SLA) | 0.250 | 0.250 | 0.250 |
| Latest published | 2026-07-22 | 2026-06-11 | 2026-07-22 |
| Oldest published | 2026-03-28 | 2025-03-28 | 2026-03-28 |
| is_fresh | ✅ True | ❌ False | ✅ True |

## 5. Phân tích

- **Suy giảm lớn nhất (tương đối):** Judge Accuracy giảm từ 1.000 xuống 0.600 (-40.0%) khi dữ liệu bị tiêm lỗi. Mức giảm các metric khác: Retrieval Hit Rate -30.0%, Mean Token F1 -32.6%, Mean Judge Score (1-5) -22.0%.
- **Silent failure:** trên dữ liệu lỗi, pipeline không crash và không có exception nào; agent trả lời 8/10 câu một cách bình thường. Tuy nhiên 3 câu là thất bại thầm lặng: 1 câu sai nội dung (Token F1 < 0.5) và 3 câu không truy xuất được tài liệu gốc (trả lời dựa trên tài liệu khác). Ngoài ra 2 câu trả lời rỗng. Lỗi chỉ lộ ra khi đo metrics hoặc nhờ Quality Gate.
- **Observability:** Quality Gate trên dữ liệu lỗi = ❌ FAIL (vi phạm: expect_column_values_to_be_unique(paper_id), expect_column_value_lengths_to_be_between(title), expect_column_value_lengths_to_be_between(summary)); Freshness = ❌ Stale (stale ratio 0.261).
- **Repair:** các metrics sau repair trùng khớp hoàn toàn với baseline. Quality Gate sau repair = ✅ PASS, Freshness = ✅ Fresh.
- **Idempotent:** chạy repair 2 lần liên tiếp cho dataset giống hệt nhau = ✅ True; repaired dataset trùng với baseline clean dataset = ✅ True.
- **Kích hoạt repair:** Tự động kích hoạt vì Quality Gate FAIL (3 expectations); Freshness SLA vi pham (stale ratio 0.2609).
