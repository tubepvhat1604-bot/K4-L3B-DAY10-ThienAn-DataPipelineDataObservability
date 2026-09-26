# Danh Sách Thành Viên & Báo Cáo Phân Công Nhóm

- **Tên Nhóm:** `ThienAn`
- **Mã Nhóm / Lớp:** `K4-L3B-DAY10`
- **Tên Repository Nộp Bài:** `K4-L3B-DAY10-ThienAn-DataPipelineDataObservability`
- **Link Repository:** https://github.com/tubepvhat1604-bot/K4-L3B-DAY10-ThienAn-DataPipelineDataObservability

---

## # Thành viên

| STT | Họ và tên | MSSV | Email | Vai trò & Phân công công việc | Báo cáo cá nhân |
|---:|---|---|---|---|---|
| 1 | Phạm Văn Hoàng Anh Tú | 2A202602507 | tubepvhat1604@gmail.com | Trưởng nhóm / Pipeline Lead & Integration (`src/pipelines/phase1.py`, `corruption_flow.py`, `common.py`, `src/retrieval/index.py`, cấu hình dự án, chạy tích hợp & artifacts) | `report/2A202602507_PhamVanHoangAnhTu.md` |
| 2 | Lê Văn Sang | 2A202602391 | lesang08092005@gmail.com | Data Foundation & Evaluation (`src/ingestion/crossref.py`, `cleaning.py`, `corruption.py`, `src/evaluation/testset.py`, `metrics.py`) | `report/2A202602391_LeVanSang.md` |
| 3 | Ngô Thế Khanh | 2A202602503 | khanhksnb4562@gmail.com | Observability & Testing (`src/observability/quality.py` GX 1.x, `reporting.py`, `dashboard.py`, bộ `tests/`, CI) | `report/2A202602503_NgoTheKhanh.md` |

### Phân công theo Checkpoint

| Checkpoint | Nội dung | Owner chính | Hỗ trợ |
|---|---|---|---|
| CP0 | Fork repo, môi trường `uv`, `.env`, ingestion raw (`crossref.py`) | Tú (repo, môi trường) · Sang (`crossref.py`) | Khanh |
| CP1 | Cleaning (`cleaning.py`) + Quality Gate GX 1.x & Freshness (`quality.py`) | Sang (cleaning) · Khanh (quality) | Tú |
| CP2 | Test set (`testset.py`) + index ChromaDB `papers-baseline` (`index.py`) | Sang (test set) · Tú (index) | Khanh |
| CP3 | Baseline end-to-end (`phase1.py`), `phase1_report.md` (`reporting.py`) | Tú (phase1) · Khanh (report) | Sang |
| CP4 | Tiêm 6 lỗi (`corruption.py`), đo suy giảm | Sang (corruption) · Tú (flow) | Khanh |
| CP5 | Idempotent repair + báo cáo 3 trạng thái (`corruption_flow.py`, `reporting.py`) | Tú (flow) · Khanh (report, dashboard) | Sang |
| CP6 | Live demo, Q&A, nộp LMS | Cả nhóm | — |
| Bonus | B1 dashboard (Khanh) · B2 auto-repair (Tú) · B3 pytest + CI (Khanh) | | |

---

## # Cá nhân

### ## PhamVanHoangAnhTu-2A202602507
- **Vai trò:** Trưởng nhóm & Pipeline Integration.
- **Công việc chi tiết đã hoàn thành:**
  - Điều phối luồng baseline trong `src/pipelines/phase1.py`: ingest → clean → Quality Gate (dừng pipeline nếu gate FAIL) → index → evaluate → report.
  - Điều phối `src/pipelines/corruption_flow.py`: tiêm lỗi → đo silent failure → tự kích hoạt repair khi gate/freshness cảnh báo → kiểm chứng idempotent bằng hash → báo cáo 3 trạng thái.
  - Viết helper dùng chung `src/pipelines/common.py`; sửa `src/retrieval/index.py` để manifest lưu đường dẫn tương đối.
  - Cấu hình dự án (`pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`), chạy pipeline thật với `openai/gpt-4o-mini` và commit artifacts trong `data/`.
- **Điều học được / Đóng góp chính:**
  - Thiết kế pipeline idempotent và vai trò của Quality Gate như "chốt chặn" trước vector store.

### ## LeVanSang-2A202602391
- **Vai trò:** Data Foundation & Evaluation.
- **Công việc chi tiết đã hoàn thành:**
  - `src/ingestion/crossref.py`: parse payload Crossref (bóc thẻ JATS, ghép tác giả, parse date-parts), chế độ offline/live có retry 429/5xx và fallback snapshot không ghi đè raw.
  - `src/ingestion/cleaning.py`: chuẩn hóa text, `age_days`, dedupe theo `paper_id`, `text_for_embedding` 5 dòng.
  - `src/ingestion/corruption.py`: 6 kịch bản lỗi với seed cố định, nhóm dòng tách biệt, ghi `corruption_log.json`.
  - `src/evaluation/testset.py` (10 câu, 4 loại) và cơ chế judge dự phòng trong `metrics.py`.
- **Điều học được / Đóng góp chính:**
  - Bảo toàn raw snapshot (data lineage) để repair luôn có nguồn tin cậy.

### ## NgoTheKhanh-2A202602503
- **Vai trò:** Observability & Testing.
- **Công việc chi tiết đã hoàn thành:**
  - `src/observability/quality.py`: Quality Gate chuẩn **Great Expectations 1.x** (ephemeral context, 7 expectations) và Freshness SLA (> 25% bài quá 180 ngày ⇒ stale).
  - `src/observability/reporting.py`: báo cáo pha 1 và báo cáo đối chiếu 3 trạng thái kèm phân tích tự động.
  - `src/observability/dashboard.py` (Bonus B1): dashboard HTML + lịch sử chạy + cảnh báo drift.
  - Bộ `tests/` 30 test, coverage ~95%, `script/run_tests.py` và GitHub Actions (Bonus B3).
- **Điều học được / Đóng góp chính:**
  - Phân biệt quality check (tính đúng của dữ liệu) và freshness monitoring (độ mới), và cách cả hai bắt được silent failure.
