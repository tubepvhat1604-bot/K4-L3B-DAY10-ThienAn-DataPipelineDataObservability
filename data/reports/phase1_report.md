# Phase 1 Report — Baseline Pipeline

_Generated at 2026-09-26T03:52:20.217308+00:00 bởi `script/run_phase1.py` (số liệu sinh tự động, không sửa tay)._

## 1. Nguồn dữ liệu & cấu hình

| Thuộc tính | Giá trị |
| --- | --- |
| Source | Crossref REST API |
| Ingestion mode | offline_snapshot |
| Ingestion note | REFRESH_SOURCE chua bat -> doc snapshot local. |
| Query | agentic retrieval augmented generation large language model |
| Raw items / parsed records | 24 / 24 |
| Clean rows | 24 |
| Run date (UTC) | 2026-09-26 |
| Embedding model | sentence-transformers/all-MiniLM-L6-v2 |
| Chroma collection | papers-baseline |
| Indexed documents | 24 |
| Retrieval top_k | 4 |
| LLM provider / model | openai / gpt-4o-mini |
| Test set | 10 câu (data/eval/test_set.json) |

## 2. Baseline metrics

| Metric | Baseline |
| --- | --- |
| Samples | 10 |
| Retrieval Hit Rate | 1.000 |
| Mean Token F1 | 1.000 |
| Judge Accuracy | 1.000 |
| Mean Judge Score (1-5) | 5.000 |
| Judge backend | llm:openai/gpt-4o-mini |

### Theo loại câu hỏi

| Question type | Baseline (Hit / F1) |
| --- | --- |
| summary | 1.00 / 1.00 |
| authors | 1.00 / 1.00 |
| date | 1.00 / 1.00 |
| categories | 1.00 / 1.00 |

## 3. Data Quality Gate (Great Expectations 1.x)

- Great Expectations version: `1.18.0`
- Suite: `papers_quality_suite_baseline` — 7/7 expectations pass
- **Quality Gate: ✅ PASS**

| Expectation | Column | Pass | Observed |
| --- | --- | --- | --- |
| expect_table_row_count_to_be_between | (table) | ✅ | 24 |
| expect_column_values_to_not_be_null | paper_id | ✅ | 0 unexpected |
| expect_column_values_to_be_unique | paper_id | ✅ | 0 unexpected |
| expect_column_values_to_not_be_null | title | ✅ | 0 unexpected |
| expect_column_value_lengths_to_be_between | title | ✅ | 0 unexpected |
| expect_column_values_to_not_be_null | text_for_embedding | ✅ | 0 unexpected |
| expect_column_value_lengths_to_be_between | summary | ✅ | 0 unexpected |

## 4. Freshness SLA

| Freshness | Baseline |
| --- | --- |
| Total rows | 24 |
| Stale rows (age > threshold) | 1 |
| Stale ratio | 0.042 |
| Max stale ratio (SLA) | 0.250 |
| Latest published | 2026-07-22 |
| Oldest published | 2026-03-28 |
| is_fresh | ✅ True |

## 5. Kết luận

- Quality Gate ✅ PASS và Freshness ✅ Fresh (stale ratio 0.042 ≤ 0.250 là đạt SLA).
- Retrieval Hit Rate = 1.000, Mean Token F1 = 1.000 trên 10 câu hỏi cố định. Đây là mốc chuẩn (baseline) dùng để so sánh với trạng thái Corrupted và Repaired.
