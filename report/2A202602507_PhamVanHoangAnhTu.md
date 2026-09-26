# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Phạm Văn Hoàng Anh Tú |
| MSSV | 2A202602507 |
| Khóa/Lớp | K4 — L3B |
| Tên nhóm | ThienAn |
| Vai trò chính | Trưởng nhóm — Pipeline Lead & Integration |
| Repository | https://github.com/tubepvhat1604-bot/K4-L3B-DAY10-ThienAn-DataPipelineDataObservability |
| Ngày hoàn thành | 2026-09-26 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Baseline orchestration | `src/pipelines/phase1.py::main` | Settings, records, clean df | `baseline_metrics.json`, `phase1_report.md` | Hoàn thành |
| Corruption & repair flow | `src/pipelines/corruption_flow.py::main`, `repair_from_raw` | Clean df, raw records, test set | corrupted/repaired metrics, `corruption_report.md` | Hoàn thành |
| Helper dùng chung | `src/pipelines/common.py` (`evaluate_state`, `fingerprint`, `save_dataframe`) | Dataframe, đường dẫn | Metrics mở rộng, hash dataset | Hoàn thành |
| Vector index | `src/retrieval/index.py` (manifest tương đối) | Clean df | 3 collection ChromaDB | Hoàn thành |
| Cấu hình & artifacts | `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`, `data/` | — | Môi trường thống nhất, artifacts commit | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Hướng dẫn clone/commit, sửa lỗi commit lên nhánh phụ | Lê Văn Sang — ingestion | Code ingestion lên đúng `main`, test 30/30 pass |
| Chạy tích hợp cuối và kiểm tra `judge_backend` | Cả nhóm | Artifacts thật với `openai/gpt-4o-mini` |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Nối luồng ingest → clean → gate → index → evaluate → report | `phase1.py` | Baseline 1.000 / 1.000 / 1.000 / 5.0 | `uv run python script/run_phase1.py` |
| Chặn index khi Quality Gate FAIL | `phase1.py` | `SystemExit` trước khi ghi ChromaDB | `tests/test_pipelines_e2e.py::test_phase1_stops_when_quality_gate_fails` |
| Tự kích hoạt repair khi gate/freshness cảnh báo (Bonus B2) | `corruption_flow.py` | Log `[repair] Tự động kích hoạt vì Quality Gate FAIL (3 expectations); Freshness SLA vi phạm` | `corruption_report.md` mục 5 |
| Kiểm chứng idempotent bằng SHA-256 | `common.py::fingerprint` | `idempotent=True`, `matches_baseline=True` | Console corruption flow |

Output cụ thể: bảng đối chiếu trong `data/reports/corruption_report.md` — Hit Rate 1.000 → 0.700 → 1.000, Judge Accuracy 1.000 → 0.600 → 1.000.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Các module riêng lẻ chỉ có giá trị khi được nối đúng thứ tự và cùng một "hợp đồng" dữ liệu. Phần của tôi đảm bảo: dữ liệu xấu không lọt vào vector store, cả 3 trạng thái được đo trên cùng test set, và có bằng chứng rằng repair thực sự phục hồi chứ không che lỗi.

### Cách triển khai

- `phase1.py` chạy Quality Gate ngay sau cleaning; FAIL thì dừng với thông báo expectation vi phạm. Test set chỉ sinh lại khi chưa có hoặc không khớp dataset để kết quả tái lập được.
- `corruption_flow.py` cố ý index dữ liệu hỏng vào `papers-corrupted` để đo tác hại nếu không có gate, rồi đếm silent failure (trả lời nhưng sai nội dung hoặc sai nguồn).
- Repair gọi lại `build_clean_dataframe` trên raw records hai lần và so SHA-256; so thêm với baseline trên các cột nội dung (bỏ `age_days` vì phụ thuộc ngày chạy). Dữ liệu repaired phải qua lại gate trước khi index.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `Settings`, `data/raw/crossref_records.json`, `data/clean/papers_clean.json`, `data/eval/test_set.json` |
| Output | `data/results/*_metrics.json`, `*_answers.json`, `data/reports/*.md`, `run_history.json` |
| Module phụ thuộc | `ingestion/*`, `observability/*`, `evaluation/*`, `retrieval/index.py` |
| Module sử dụng output | Dashboard, báo cáo nhóm, live demo |
| Điều kiện lỗi cần xử lý | Thiếu artifact pha 1, test set lệch dataset, gate FAIL, repair vẫn FAIL gate |

### Cách xác minh

```bash
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** exit 0, bảng 3 trạng thái, repaired = baseline.
- **Kết quả thực tế:** đúng như mong đợi; `judge_backend = llm:openai/gpt-4o-mini` ở cả 3 trạng thái.
- **Artifact/log:** `data/reports/corruption_report.md`, `data/quality/run_history.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Khi Quality Gate pha 1 FAIL, nên cảnh báo rồi chạy tiếp hay dừng hẳn?
- **Các phương án đã cân nhắc:** (1) chỉ log cảnh báo và vẫn index; (2) dừng pipeline (`SystemExit`) trước khi ghi ChromaDB.
- **Phương án đã chọn:** (2) cho pha 1; riêng corruption flow cố ý bỏ qua gate để đo tác hại.
- **Lý do:** mục tiêu của gate là chặn dữ liệu xấu trước serving layer; cảnh báo mà vẫn index thì silent failure vẫn xảy ra. Freshness chỉ cảnh báo, không chặn, vì nó phụ thuộc ngày chạy.
- **Bằng chứng:** test `test_phase1_stops_when_quality_gate_fails` xác nhận không có manifest embeddings nào được ghi; số liệu corrupted cho thấy nếu không chặn thì Judge Accuracy giảm 40%.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** pipeline chạy xong nhưng `judge_backend = heuristic_fallback`; lý do trong `baseline_answers.json`: `RuntimeError: OPENAI_API_KEY is required when LLM_PROVIDER=openai.`
- **Lệnh tái hiện:** `uv run python -c "from core.config import load_settings; ..."` in `openai gpt-4o-mini THIEU KEY`.
- **Nguyên nhân gốc:** file `.env` có hai dòng `OPENAI_API_KEY`; dòng trống phía sau ghi đè dòng có key.
- **Cách xử lý:** giữ đúng một dòng `OPENAI_API_KEY`, kiểm tra bằng script chỉ in tên biến và trạng thái (không in giá trị key).
- **Cách xác minh sau khi sửa:** in `key OK`; chạy lại pipeline cho `judge_backend = llm:openai/gpt-4o-mini`.
- **Điều học được:** metric phải ghi rõ nguồn gốc (judge nào chấm) — nếu không, một lỗi cấu hình sẽ tạo ra số liệu trông bình thường nhưng sai bản chất, chính là một silent failure.

## 7. Hiểu biết về luồng end-to-end

1. Snapshot Crossref được parse thành raw records, clean thành 24 dòng có `text_for_embedding`, qua gate, rồi được MiniLM embed vào ChromaDB.
2. Mỗi câu hỏi mang `ground_truth_doc_ids`; Hit Rate kiểm tra DOI đó có trong top-4, Token F1 và LLM judge so câu trả lời với ground truth.
3. Quality checks kiểm tra tính đúng của từng dòng/cột (null, unique, độ dài); freshness kiểm tra độ mới của cả tập (tỉ lệ bài quá 180 ngày).
4. Dùng cùng test set để chênh lệch metric chỉ đến từ dữ liệu, không phải do đề thi khác.
5. Repair thành công khi gate 7/7, freshness Fresh, hash trùng baseline và 4 metrics về bằng baseline.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.000 | 0.700 | 1.000 | 3 câu mất tài liệu gốc do drop/truncate |
| `mean_token_f1` | 1.000 | 0.674 | 1.000 | Kéo xuống chủ yếu bởi câu summary rỗng |
| `judge_accuracy` | 1.000 | 0.600 | 1.000 | Giảm mạnh nhất theo tỉ lệ (−40%) |
| `mean_judge_score` | 5.0 | 3.9 | 5.0 | Dao động nhẹ giữa các lần chạy (3.8/3.9) |
| Quality checks | 7/7 | 4/7 | 7/7 | Gate phát hiện 3/6 kịch bản trực tiếp |
| Freshness status | Fresh | Stale | Fresh | 0,261 vượt ngưỡng 0,25 |

### Kết luận từ số liệu

1. drop_latest + duplicate_rows → row count/unique fail → Hit Rate 0.700 vì tài liệu gốc mất và bản trùng chiếm chỗ top-k.
2. Repair từ raw → gate 7/7 + Fresh → 4 metrics phục hồi 100%.

Corruption ảnh hưởng rõ nhất là drop_latest_records: không expectation nào bắt được việc mất "đúng những bài mới nhất" (row count vẫn 23 hợp lệ), chỉ freshness và metric mới lộ ra.

Kết quả khác kỳ vọng: câu hỏi authors vẫn đạt F1 1.00 dù hit rate 0.67 — do bài "Advanced Perspectives…" có cùng tác giả với bài gốc, agent đúng nhờ may mắn.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Pipeline phải idempotent và luôn dựng lại được từ raw — đó là "nguồn nước dự phòng".
2. Gate nên chặn trước serving layer; observability phải ghi cả nguồn gốc metric.
3. RAG agent không báo lỗi khi dữ liệu hỏng — nó chỉ trả lời sai một cách tự tin.

### Nếu có thêm thời gian

Thêm bước "gate trước khi index" cho corruption flow ở chế độ production (chỉ bypass khi bật cờ thử nghiệm) và đo thời gian phục hồi (MTTR) trên dashboard.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Phạm Văn Hoàng Anh Tú
**Ngày xác nhận:** 2026-09-26
