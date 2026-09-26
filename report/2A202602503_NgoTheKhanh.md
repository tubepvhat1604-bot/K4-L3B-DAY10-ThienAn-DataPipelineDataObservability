# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Ngô Thế Khanh |
| MSSV | 2A202602503 |
| Khóa/Lớp | K4 — L3B |
| Tên nhóm | ThienAn |
| Vai trò chính | Observability & Testing |
| Repository | https://github.com/tubepvhat1604-bot/K4-L3B-DAY10-ThienAn-DataPipelineDataObservability |
| Ngày hoàn thành | 2026-09-26 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Quality Gate GX 1.x | `src/observability/quality.py::run_data_quality_checks` | Clean/corrupted/repaired df | `data/quality/*_quality_report.json` | Hoàn thành |
| Freshness SLA | `quality.py::build_freshness_report`, `compute_freshness` | `age_days` | `freshness_report*.json` | Hoàn thành |
| Reporting | `src/observability/reporting.py` | Metrics, quality, freshness, log | `phase1_report.md`, `corruption_report.md` | Hoàn thành |
| Dashboard (Bonus B1) | `src/observability/dashboard.py`, `script/build_dashboard.py` | Artifacts `data/` | `data/reports/dashboard.html`, `run_history.json` | Hoàn thành |
| Test & CI (Bonus B3) | `tests/*.py`, `script/run_tests.py`, `.github/workflows/tests.yml` | Code toàn repo | 30 test, coverage ~95% | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Test end-to-end hai pipeline trong thư mục tạm | Tú — pipelines | Phát hiện sớm lỗi tích hợp (ImportError khi thiếu code ingestion) |
| Test ingestion giả lập 429/mất mạng | Sang — `crossref.py` | Xác nhận fallback không ghi đè snapshot |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Gate GX 1.x: ephemeral context → `add_pandas` → dataframe asset → batch definition → `batch.validate(suite)` | `quality.py` | Baseline 7/7 pass; corrupted 4/7 | CP1: `Quality check status = True` |
| Freshness: `is_fresh = False` khi > 25% bài có `age_days > 180` | `quality.py` | Baseline 0,042 Fresh; corrupted 0,261 Stale | `freshness_report*.json` |
| Báo cáo 3 trạng thái + phân tích tự động (suy giảm tương đối, silent failure, idempotent) | `reporting.py` | `corruption_report.md` | Mở file trên GitHub |
| Dashboard + cảnh báo drift > 10% | `dashboard.py` | `dashboard.html` tự sinh sau mỗi lần chạy | `uv run python script/build_dashboard.py` |
| 30 test + CI | `tests/`, `.github/workflows/tests.yml` | 30 passed, 94,8% coverage | `uv run python script/run_tests.py` |

Output cụ thể: bảng expectation trong `corruption_report.md` — `unique(paper_id)` 8 lỗi, `title` length 5 lỗi, `summary` length 5 lỗi ở trạng thái corrupted; tất cả ✅ ở baseline và repaired.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Silent failure không tạo exception, nên cần một "trạm kiểm dịch" đo được chất lượng dữ liệu trước khi index, và một lớp báo cáo biến số liệu thành bằng chứng dễ đọc cho người vận hành.

### Cách triển khai

- Chỉ đưa các cột scalar vào GX (cột list như `authors` không hash được, làm `unique` lỗi); chuỗi rỗng/khoảng trắng được chuyển thành `None` để `not_null` bắt được summary/title bị xóa trắng.
- 4 nhóm expectation bắt buộc + 1 mở rộng (`title` ≥ 8 ký tự) để bắt truncate_title.
- `success` chỉ phản ánh GX; freshness nằm trong key riêng và `overall_healthy = success AND is_fresh`, vì freshness đổi theo ngày chạy và không nên làm baseline tự nhiên FAIL gate.
- Báo cáo so sánh suy giảm theo **% tương đối** vì metric khác thang đo (Judge Score 1–5 so với các metric 0–1).
- Test chạy trên bản sao project trong thư mục tạm, embedding giả lập bằng hashing, `LLM_PROVIDER=mock` ⇒ không đụng `data/` thật, không gọi API.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | DataFrame có `paper_id`, `title`, `summary`, `text_for_embedding`, `age_days`, `published` |
| Output | Dict `{success, checks[], failed_expectations, freshness, overall_healthy}` + JSON; Markdown; HTML |
| Module phụ thuộc | `great_expectations` 1.18, `core/config.py` |
| Module sử dụng output | `phase1.py` (quyết định dừng), `corruption_flow.py` (kích hoạt repair), dashboard |
| Điều kiện lỗi cần xử lý | DataFrame rỗng, cột list, chuỗi rỗng, artifact chưa tồn tại khi build dashboard |

### Cách xác minh

```bash
uv run python script/run_tests.py
uv run python -c "from core.config import load_settings; from observability.quality import run_data_quality_checks; import pandas as pd; s=load_settings(); df=pd.read_json(s.paths.clean_json); res=run_data_quality_checks(df, s, 'test'); print(f'Tín hiệu hoàn thành: Quality check status = {res[\"success\"]}')"
```

- **Kết quả mong đợi:** 30 passed; `Quality check status = True`.
- **Kết quả thực tế:** đúng như mong đợi.
- **Artifact/log:** `data/quality/baseline_quality_report.json`, `data/reports/dashboard.html`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Freshness có nên là một phần của Quality Gate (chặn pipeline) hay không.
- **Các phương án đã cân nhắc:** (1) `success = GX AND is_fresh`; (2) tách freshness thành tín hiệu riêng, gate chỉ dựa vào GX.
- **Phương án đã chọn:** (2), kèm `overall_healthy` tổng hợp và freshness vẫn kích hoạt repair ở corruption flow.
- **Lý do:** tỉ lệ bài quá hạn tăng tự nhiên theo ngày chạy; gộp vào gate sẽ khiến baseline tự FAIL mà không có lỗi dữ liệu nào (false positive), làm mất niềm tin vào gate.
- **Bằng chứng:** baseline 1/24 bài quá hạn (0,042) vẫn Fresh; corrupted 0,261 bị đánh dấu Stale và vẫn kích hoạt repair.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** phần phân tích tự động ban đầu kết luận "Mean Judge Score giảm mạnh nhất (Δ −1.2)".
- **Lệnh tái hiện:** chạy `run_corruption_flow.py`, đọc mục 5 của `corruption_report.md`.
- **Nguyên nhân gốc:** so sánh chênh lệch tuyệt đối giữa các metric khác thang đo (1–5 và 0–1).
- **Cách xử lý:** đổi sang suy giảm tương đối `(baseline − corrupted) / baseline` và liệt kê % của mọi metric.
- **Cách xác minh sau khi sửa:** báo cáo xác định đúng Judge Accuracy giảm mạnh nhất (−40%); 30 test vẫn pass.
- **Điều học được:** báo cáo tự động cũng có thể "nói sai" nếu logic phân tích không kiểm tra đơn vị đo.

## 7. Hiểu biết về luồng end-to-end

1. Crossref → raw records → clean df → gate của tôi → MiniLM → ChromaDB.
2. Test set gắn DOI ground truth; Hit Rate đo retrieval, Token F1/judge đo câu trả lời.
3. Quality checks kiểm tra từng dòng/cột; freshness kiểm tra phân bố tuổi cả tập so với SLA 180 ngày / 25%.
4. Cùng test set để quy khác biệt về dữ liệu.
5. Repair thành công khi báo cáo của tôi hiển thị gate 7/7, Fresh, idempotent = True và 4 metrics trở về baseline.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.000 | 0.700 | 1.000 | |
| `mean_token_f1` | 1.000 | 0.674 | 1.000 | |
| `judge_accuracy` | 1.000 | 0.600 | 1.000 | Judge khắt khe hơn Token F1 (bắt được eval_001 F1 0,74 nhưng sai nguồn) |
| `mean_judge_score` | 5.0 | 3.9 | 5.0 | Judge chấm 2 điểm cho câu trả lời rỗng — hạn chế của LLM judge |
| Quality checks | 7/7 | 4/7 | 7/7 | 3/6 kịch bản bị bắt trực tiếp |
| Freshness status | Fresh | Stale | Fresh | Bắt thêm stale_date và drop_latest |

### Kết luận từ số liệu

1. duplicate_rows → `unique(paper_id)` fail (8 giá trị) → bản trùng chiếm chỗ top-k (eval_010) → retrieval kém ổn định.
2. Repair → gate 7/7 và Fresh → dashboard chuyển cả 3 ống nghiệm về trạng thái hợp lệ, metrics về 1.000.

Kết hợp GX + freshness phát hiện 5/6 kịch bản (trừ inject_noise), trong khi metric của agent vẫn trông "bình thường" ở nhiều câu — đó là lý do cần observability ở tầng dữ liệu.

Kết quả khác kỳ vọng: inject_noise không bị gate bắt vì summary nhiễu dài hơn ngưỡng 30 ký tự.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Kiểm tra dữ liệu phải chạy trước vector store, không phải sau khi người dùng phàn nàn.
2. Quality và freshness là hai tín hiệu khác nhau, cần ngưỡng và hành động khác nhau.
3. Test tự động phát hiện lỗi tích hợp nhanh hơn chạy tay cả pipeline.

### Nếu có thêm thời gian

Thêm expectation phát hiện nhiễu ký tự và gửi cảnh báo drift từ dashboard qua webhook; đo số kịch bản phát hiện được (mục tiêu 6/6).

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Ngô Thế Khanh
**Ngày xác nhận:** 2026-09-26
