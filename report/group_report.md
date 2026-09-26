# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin         | Nội dung |
| ------------------ | -------- |
| Khóa/Lớp          | K4 — L3B |
| Tên nhóm          | ThienAn |
| Repository         | https://github.com/tubepvhat1604-bot/K4-L3B-DAY10-ThienAn-DataPipelineDataObservability |
| Ngày hoàn thành   | 2026-09-26 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Phạm Văn Hoàng Anh Tú | 2A202602507 | Pipeline Lead & Integration | `src/pipelines/phase1.py`, `corruption_flow.py`, `common.py`, `src/retrieval/index.py`, cấu hình dự án, artifacts `data/` |
| 2 | Lê Văn Sang | 2A202602391 | Data Foundation & Evaluation | `src/ingestion/crossref.py`, `cleaning.py`, `corruption.py`, `src/evaluation/testset.py`, `metrics.py` |
| 3 | Ngô Thế Khanh | 2A202602503 | Observability & Testing | `src/observability/quality.py`, `reporting.py`, `dashboard.py`, `tests/`, CI |

## 2. Tóm tắt kết quả

**Tóm tắt của nhóm:**

Nhóm hoàn thành toàn bộ 11 hàm `TODO(student)` và cả hai luồng pipeline. Pha 1 thu thập 24 bài báo Crossref từ snapshot offline, làm sạch thành 24 dòng, qua Quality Gate Great Expectations 1.x (7/7 expectations pass, freshness 4,2% bài quá hạn), nạp vào ChromaDB `papers-baseline` và đạt baseline Hit Rate = Token F1 = Judge Accuracy = 1.000, Judge Score 5.0 trên 10 câu hỏi cố định (LLM judge `openai/gpt-4o-mini`).

Pha 2 tiêm 6 loại lỗi (24 → 23 dòng). Quality Gate phát hiện ngay 3 expectation vi phạm (trùng `paper_id`, summary quá ngắn, title bị cắt) và Freshness chuyển sang Stale (26,1% > 25%). Nếu vẫn để dữ liệu lỗi vào vector store, pipeline không báo lỗi gì nhưng chất lượng giảm rõ: Hit Rate 0.700, Token F1 0.674, Judge Accuracy 0.600 (giảm 40%), Judge Score 3.9. Hai lỗi tác động mạnh nhất là **drop latest records** (mất tài liệu gốc) và **blank summary** (câu trả lời rỗng).

Repair dựng lại dữ liệu từ raw snapshot, được tự kích hoạt khi gate/freshness cảnh báo, chạy 2 lần cho cùng hash (idempotent) và trùng khớp baseline: cả 4 metrics phục hồi 100%. Giới hạn chính: LLM judge không tất định và có thể chấm sai câu trả lời rỗng; bộ dữ liệu nhỏ (24 bài) nên mỗi câu hỏi chiếm 10% metric.

**Công cụ hỗ trợ:** nhóm sử dụng trợ lý AI (Claude) để gợi ý và sinh code theo chính sách AI của lab; mọi module đã được nhóm review, chạy kiểm chứng bằng 2 pipeline và 30 test tự động.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref snapshot (data/raw/crossref_response.json) | Live API khi REFRESH_SOURCE=1
    -> parse + raw records (data/raw/crossref_records.json)
    -> cleaning + data model (data/clean/papers_clean.*)
    -> Quality Gate GX 1.x + Freshness SLA (data/quality/)   ── FAIL ⇒ dừng, không index
    -> MiniLM embedding + ChromaDB papers-baseline
    -> evaluation baseline trên data/eval/test_set.json
    -> corruption 6 kịch bản (seed 42) -> quality/freshness FAIL -> index papers-corrupted -> evaluate
    -> auto-repair từ raw records (idempotent) -> index papers-repaired -> evaluate
    -> corruption_report.md + dashboard.html
```

### Trách nhiệm của từng khối

| Khối | Input | Xử lý chính | Output/artifact | Owner |
| --- | --- | --- | --- | --- |
| Ingestion | Snapshot/Crossref API | Offline mặc định; live có retry 429/5xx; fallback không ghi đè raw; parse JATS, authors, date-parts | `data/raw/crossref_records.json` | Sang |
| Cleaning | Raw records | Chuẩn hóa text, dedupe `paper_id`, `age_days`, `text_for_embedding` | `data/clean/papers_clean.csv/json` | Sang |
| Embedding/index | Clean dataframe | all-MiniLM-L6-v2, 3 collection Chroma riêng, manifest đường dẫn tương đối | `data/chroma/`, `data/embeddings/` | Tú |
| Evaluation | Clean dataframe, index | 10 câu cố định; Hit Rate, Token F1, LLM judge | `data/eval/test_set.json`, `data/results/*_metrics.json` | Sang |
| Observability | Dataframe | 7 expectations GX 1.x, Freshness SLA, report, dashboard | `data/quality/`, `data/reports/` | Khanh |
| Corruption/repair | Clean dataframe / raw records | 6 lỗi seed 42; repair dựng lại từ raw, kiểm tra hash | `corruption_log.json`, `papers_clean_*` | Sang (corruption) · Tú (repair) |
| Orchestration | Settings | Thứ tự chạy, gate, auto-repair, so sánh 3 trạng thái | `phase1_report.md`, `corruption_report.md` | Tú |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình | Giá trị sử dụng |
| --- | --- |
| `LLM_PROVIDER` | `openai` |
| `LLM_MODEL` | `gpt-4o-mini` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 (snapshot offline) |
| Retrieval `top_k` | 4 |
| Freshness threshold | 180 ngày, tối đa 25% bài quá hạn |
| Random seed | 42 (corruption) |

### Lệnh cài đặt

```bash
uv sync --extra dev
```

### Lệnh chạy

```bash
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
uv run python script/run_tests.py        # 30 test, coverage ≥ 80%
```

### Kết quả tái hiện

| Lệnh | Trạng thái | Thời điểm chạy gần nhất | Bằng chứng |
| --- | --- | --- | --- |
| Baseline pipeline | Thành công (exit 0) | 2026-09-26 | `data/reports/phase1_report.md`, `data/results/baseline_metrics.json` |
| Corruption flow | Thành công (exit 0) | 2026-09-26 | `data/reports/corruption_report.md`, `data/results/corruption_log.json` |
| Test suite | 30 passed, coverage 94,8% | 2026-09-26 | `script/run_tests.py`, GitHub Actions |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính | Giá trị |
| --- | --- |
| Source | Crossref REST API `/works` (snapshot `data/raw/crossref_response.json`) |
| Query/filter | `agentic retrieval augmented generation large language model`; `from-pub-date` 180 ngày, `has-abstract:true` |
| Thời điểm lấy dữ liệu | Snapshot cung cấp sẵn; parse lại mỗi lần chạy (2026-09-26) |
| Số record nhận được | 24 items → 24 records hợp lệ |
| Cơ chế retry/backoff | 4 lần, backoff 2^n giây, tôn trọng `Retry-After` cho 429/5xx; lỗi hoặc < 5 record ⇒ fallback snapshot |

### Raw và clean schema

| Trường | Kiểu dữ liệu | Bắt buộc? | Ý nghĩa | Xử lý khi thiếu/sai |
| --- | --- | --- | --- | --- |
| `paper_id` | str (DOI) | Có | Định danh tài liệu | Thiếu ⇒ loại; trùng (không phân biệt hoa thường) ⇒ giữ bản `updated` mới nhất |
| `title` | str | Có | Tiêu đề | Rỗng ⇒ loại; GX yêu cầu ≥ 8 ký tự |
| `summary` | str | Có | Tóm tắt (đã bỏ thẻ JATS) | Rỗng ⇒ loại; GX yêu cầu ≥ 30 ký tự |
| `authors` / `authors_joined` | list[str] / str | Không | Tác giả `given family` | Thiếu ⇒ danh sách rỗng |
| `categories` / `categories_joined` | list[str] / str | Không | Subject Crossref | Thiếu ⇒ rỗng, loại trùng |
| `published` | str `YYYY-MM-DD` | Có | Ngày xuất bản | Thiếu tháng/ngày ⇒ 01; không parse được ⇒ loại |
| `age_days` | int | Có | `run_date − published` | Tính lại mỗi lần chạy |
| `text_for_embedding` | str | Có | Ngữ cảnh để embed | Luôn tính lại từ các cột trên |

### Quy tắc cleaning

| Quy tắc | Quality dimension | Số record bị tác động (snapshot) | Cách xác minh |
| --- | --- | ---: | --- |
| Bỏ thẻ JATS/HTML, decode entity, gom khoảng trắng | Validity | 24 (mọi abstract có `<jats:p>`) | `tests/test_ingestion.py` |
| Loại record thiếu `paper_id`/title/summary/ngày | Completeness | 0 | `tests/test_cleaning_corruption.py` (dữ liệu bẩn giả lập) |
| Dedupe theo `paper_id` không phân biệt hoa thường | Uniqueness | 0 | GX `unique(paper_id)` pass |
| Chuẩn hóa ngày `YYYY-MM-DD`, tính `age_days` | Validity / Timeliness | 24 | `freshness_report.json` |

`text_for_embedding` ghép 5 dòng `Title / Authors / Published / Categories / Summary` để embedding nắm cả nội dung lẫn metadata. Document ID là DOI (ổn định giữa các lần chạy). `age_days = (run_date − published).days` theo UTC; `published` lưu dạng chuỗi vì ChromaDB không nhận metadata kiểu Timestamp.

## 6. Evaluation setup

| Thành phần | Cấu hình thực tế |
| --- | --- |
| Số câu hỏi | 10 |
| Các `question_type` | summary (3), authors (3), date (2), categories (2) |
| Ground-truth document ID | DOI của bài được hỏi; chọn 10 bài trải đều theo thời gian |
| Embedding model | all-MiniLM-L6-v2 |
| Vector store/collection | ChromaDB: `papers-baseline`, `papers-corrupted`, `papers-repaired` |
| Retrieval `top_k` | 4 |
| LLM provider/model | openai / gpt-4o-mini (judge + agent demo) |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json` |

Test set được giữ nguyên để mọi thay đổi metric chỉ đến từ dữ liệu. Pipeline chỉ sinh lại test set khi chưa có, khi không khớp dataset, hoặc khi đặt `REFRESH_TEST_SET=1`; corruption flow từ chối chạy nếu test set không khớp clean dataset.

## 7. Kết quả baseline

### Artifact checklist

| Artifact | Đường dẫn thực tế | Trạng thái | Ghi chú |
| --- | --- | --- | --- |
| Raw response/records | `data/raw/` | Có | 24 records |
| Cleaned dataset | `data/clean/` | Có | 24 dòng, 16 cột |
| Embedding manifest/index | `data/embeddings/`, `data/chroma/` | Có | 3 collection |
| Evaluation set | `data/eval/test_set.json` | Có | 10 câu |
| Baseline metrics | `data/results/baseline_metrics.json` | Có | kèm breakdown theo loại câu |
| Quality/freshness | `data/quality/` | Có | baseline/corrupted/repaired |
| Baseline report | `data/reports/phase1_report.md` | Có | + `dashboard.html` |

### Baseline metrics

| Metric | Giá trị | Diễn giải |
| --- | ---: | --- |
| `retrieval_hit_rate` | 1.000 | Cả 10 câu đều truy xuất đúng tài liệu gốc (lookup theo title + tìm kiếm ngữ nghĩa) |
| `mean_token_f1` | 1.000 | Câu trả lời trùng khớp ground truth |
| `judge_accuracy` | 1.000 | GPT-4o-mini chấm đúng cả 10 câu |
| `mean_judge_score` | 5.0 | Điểm tối đa |
| Ragas | N/A | Không bật `RUN_RAGAS` để giữ chi phí và thời gian thấp |

## 8. Data quality và freshness

### Quality checks

| Check | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline | Bằng chứng |
| --- | --- | --- | --- | --- |
| `ExpectTableRowCountToBeBetween` | Completeness | 5–5000 dòng | Pass (24) | `baseline_quality_report.json` |
| `ExpectColumnValuesToNotBeNull` × 3 | Completeness | `paper_id`, `title`, `text_for_embedding` không rỗng | Pass (0 lỗi) | như trên |
| `ExpectColumnValuesToBeUnique` | Uniqueness | `paper_id` duy nhất | Pass | như trên |
| `ExpectColumnValueLengthsToBeBetween` | Validity | `summary` ≥ 30 ký tự | Pass | như trên |
| `ExpectColumnValueLengthsToBeBetween` | Validity | `title` ≥ 8 ký tự | Pass | như trên |

### Freshness

| Thuộc tính | Giá trị |
| --- | --- |
| Freshness được đo tại | Clean dataset (`age_days`) |
| Timestamp mới nhất | 2026-07-22 |
| Ngưỡng freshness | 180 ngày; tối đa 25% bài quá hạn |
| Trạng thái baseline | Fresh |
| Lý do | 1/24 bài (4,2%) quá 180 ngày, dưới ngưỡng 25% |

## 9. Corruption scenarios và repair

| Corruption | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair |
| --- | --- | ---: | --- | --- | --- |
| drop_latest_records | Bỏ 20% bài mới nhất | 5 | Row count giảm, freshness xấu đi | Latest published 2026-07-22 → 2026-06-11; mất tài liệu gốc của câu hỏi | Dựng lại từ raw |
| blank_summary | Xóa trắng summary | 4 | `summary` length fail | 2 câu summary trả lời rỗng | Dựng lại từ raw |
| inject_noise | Chèn token rác sau mỗi từ | 4 | Không có GX riêng (tín hiệu qua metric) | Làm nhiễu câu trả lời và embedding | Dựng lại từ raw |
| truncate_title | Cắt title còn 6 ký tự | 4 | `title` length fail | Lookup theo title thất bại, phải dựa vào tìm kiếm ngữ nghĩa | Dựng lại từ raw |
| stale_date | Lùi `published` 365 ngày | 6 | Freshness Stale | Stale ratio 0,261 > 0,25; câu hỏi ngày trả lời sai năm | Dựng lại từ raw |
| duplicate_rows | Nhân bản dòng | 4 | `unique(paper_id)` fail | Bản trùng chiếm chỗ trong top-k | Dựng lại từ raw |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: log ghi đủ 6 kịch bản, số dòng và danh sách `paper_id` bị ảnh hưởng, tham số (tỉ lệ, số ngày lùi, số ký tự cắt) và seed 42.

Repair không vá từng lỗi trên dữ liệu hỏng mà dựng lại toàn bộ dataset từ `data/raw/crossref_records.json` — nguồn không bao giờ bị ghi đè (kể cả khi API live lỗi). Hàm cleaning thuần túy nên chạy repair 2 lần cho cùng hash SHA-256; dataset repaired cũng trùng nội dung với baseline. Dữ liệu repaired phải qua lại Quality Gate trước khi được index.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.000 | 0.700 | 1.000 | −0.300 (−30%) | 100% | 3 câu mất tài liệu gốc |
| `mean_token_f1` | 1.000 | 0.674 | 1.000 | −0.326 (−32,6%) | 100% | Summary giảm mạnh nhất (F1 0,25) |
| `judge_accuracy` | 1.000 | 0.600 | 1.000 | −0.400 (−40%) | 100% | Giảm mạnh nhất theo tỉ lệ |
| `mean_judge_score` | 5.0 | 3.9 | 5.0 | −1.1 (−22%) | 100% | |
| Quality checks pass/fail | 7/7 Pass | 4/7 Fail | 7/7 Pass | −3 expectations | 100% | unique, title, summary |
| Freshness status | Fresh (0,042) | Stale (0,261) | Fresh (0,042) | vượt SLA | 100% | do stale_date + drop latest |

Kết luận nhân quả:

1. **drop_latest + stale_date → Freshness Stale (0,261) → câu hỏi ngày sai.** Ở câu eval_003, tài liệu gốc bị drop nên agent lấy bài "Advanced Perspectives…" gần giống, bài này lại bị lùi ngày ⇒ trả lời `2025-06-02` thay vì `2026-06-12`, hoàn toàn tự tin, không có exception.
2. **blank_summary + duplicate_rows → GX fail (summary length, unique paper_id) → Token F1 summary 1.00 → 0.25.** Hai câu summary trả lời rỗng; bản trùng chiếm 2 trong 4 vị trí top-k (eval_010).
3. **Repair từ raw → Quality Gate 7/7 và Fresh → cả 4 metrics về đúng baseline**, hash repaired trùng baseline.

Silent failure: pipeline không crash; agent trả lời bình thường 8/10 câu nhưng 3 câu là thất bại thầm lặng (1 sai nội dung, 3 lấy từ sai tài liệu, trong đó eval_002 đúng tác giả chỉ vì bài "anh em" có cùng tác giả). Câu eval_001 có Token F1 0,74 nhưng LLM judge chấm sai — ví dụ cho thấy cần judge bên cạnh Token F1.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** sau khi ghép code của 3 thành viên, `run_tests.py` báo `ImportError: cannot import name 'CLEAN_COLUMNS' from 'ingestion.cleaning'`.
- **Nguyên nhân:** phần ingestion được commit trên nhánh cá nhân `Le-Van-Sang-2A202602391` và bản đầu tiên vẫn là file starter, nên `main` thiếu code cleaning mà test và pipeline phụ thuộc.
- **Cách xử lý:** kiểm tra nội dung (`Select-String CLEAN_COLUMNS`), commit lại bản hoàn thiện trên nhánh, mở Pull Request #1 và merge vào `main` bằng merge commit để giữ đúng tác giả.
- **Cách xác minh:** `git log` trên `main` có commit `feat(ingestion)` của Lê Văn Sang và merge commit PR #1; `uv run python script/run_tests.py` → 30 passed; hai pipeline exit 0.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng | Hướng cải thiện có thể kiểm chứng |
| --- | --- | --- |
| LLM judge không tất định (Judge Score corrupted 3.8 → 3.9 giữa 2 lần chạy) và chấm 2 điểm cho câu trả lời rỗng | Judge metric dao động nhẹ, có thể "ảo giác" | Chạy judge nhiều lần lấy trung bình; ép score = 1 khi câu trả lời rỗng; đối chiếu với Token F1 |
| Chỉ 24 bài, 10 câu hỏi | Mỗi câu = 10% metric | Mở rộng live API và test set 30+ câu |
| `inject_noise` không có expectation riêng | Chỉ phát hiện qua metric | Thêm expectation tỉ lệ ký tự không phải chữ cái trong summary |
| Freshness phụ thuộc ngày chạy | Baseline có thể tự chuyển Stale theo thời gian | Lịch refresh tự động `REFRESH_SOURCE=1` + cảnh báo drift trên dashboard |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [ ] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
