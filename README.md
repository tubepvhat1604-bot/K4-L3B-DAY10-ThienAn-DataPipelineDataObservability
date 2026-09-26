# K4-L3B-Day10 — Data Pipeline & Data Observability for RAG

> **Hình thức:** Teamwork | **Thời lượng:** 240 phút  
> **Lịch học (Lớp B - Ca Sáng):** Thứ 7 (26/09/2026) 09:00 – 13:00  
> ⏰ **Hạn nộp LMS:** 23:59:59 cùng ngày

---

## 🧭 Đọc gì, theo thứ tự nào?

| # | Tài liệu | Mô tả |
|:---:|---|---|
| 1️⃣ | **Codelab trên VLearn LMS** | Hướng dẫn từng bước + nộp bài (mở trên trình duyệt) |
| 2️⃣ | [CHECKPOINTS.md](docs/CHECKPOINTS.md) | Phân bổ thời gian 240 phút & deliverables từng mốc |
| 3️⃣ | [RUBRIC.md](docs/RUBRIC.md) | Tiêu chí chấm điểm (100 chuẩn + 10 bonus) |
| 4️⃣ | [SUBMISSION.md](docs/SUBMISSION.md) | Nội quy, deadline, bảo mật & checklist nộp bài |
| 5️⃣ | [TEAM.md](docs/TEAM.md) | Điền thông tin nhóm & báo cáo cá nhân |

---

## Repo có sẵn gì? (Scaffolded Baseline)

- `data/raw/` — Snapshot offline Crossref API (`crossref_response.json`)
- `src/` — Khung pipeline thu thập, embedding MiniLM, đánh giá metrics (có `TODO(student)`)
- `script/` — Entrypoints: `run_phase1.py`, `run_corruption_flow.py`

## Học viên cần làm gì?

1. Hoàn thiện **Data Quality Gate** (Great Expectations 1.x) trong `src/observability/quality.py`
2. Tích hợp **Freshness Check** (`age_days`) vào Quality Gate
3. Chạy **Baseline → Corruption → Repair** → xuất bảng đối chiếu 3 trạng thái
4. **Live Demo** trên bảng & nộp link repo lên VLearn LMS

---

## Hướng dẫn chạy bài làm của nhóm

```bash
python -m pip install -e ".[dev]"        # hoặc: uv sync --extra dev
cp .env.example .env                      # điền OPENAI_API_KEY (không commit .env)

python script/run_phase1.py               # Pha 1: baseline -> data/reports/phase1_report.md
python script/run_corruption_flow.py      # Pha 2: corrupt -> detect -> repair -> data/reports/corruption_report.md
python script/build_dashboard.py          # (B1) tạo lại data/reports/dashboard.html, mở bằng trình duyệt
python script/run_tests.py                # (B3) pytest + coverage >= 80%, CI: .github/workflows/tests.yml
```

- Mặc định đọc snapshot offline `data/raw/crossref_response.json`; đặt `REFRESH_SOURCE=1` để gọi Crossref API live (tự fallback về snapshot khi lỗi mạng/429, không ghi đè snapshot).
- Test set cố định tại `data/eval/test_set.json`; đặt `REFRESH_TEST_SET=1` nếu muốn sinh lại.
- Không có API key: đặt `LLM_PROVIDER=mock` (judge dùng heuristic, ghi rõ trong `judge_backend` của metrics).
- **Bonus B1:** dashboard HTML tự sinh sau mỗi lần chạy (trạng thái Quality Gate, phân bố tuổi bài báo so với Freshness SLA, lịch sử chạy + cảnh báo drift).
- **Bonus B2:** `run_corruption_flow.py` tự kích hoạt repair từ raw khi Quality Gate/Freshness phát hiện lỗi và kiểm chứng idempotent bằng hash.
- **Bonus B3:** 30 test (ingestion, cleaning, GX gate, retrieval, agent, pipelines end-to-end) chạy trên thư mục tạm, embedding giả lập, không gọi API.
