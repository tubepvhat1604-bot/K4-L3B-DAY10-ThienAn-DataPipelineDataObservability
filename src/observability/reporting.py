from __future__ import annotations

from pathlib import Path
from typing import Any

from core.utils import now_utc, write_text

METRIC_KEYS = [
    ("retrieval_hit_rate", "Retrieval Hit Rate"),
    ("mean_token_f1", "Mean Token F1"),
    ("judge_accuracy", "Judge Accuracy"),
    ("mean_judge_score", "Mean Judge Score (1-5)"),
]
TYPE_ORDER = ["summary", "authors", "date", "categories"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "✅ True" if value else "❌ False"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _num(value: Any) -> Any:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else value


def _delta(new: Any, old: Any) -> str:
    if not isinstance(new, (int, float)) or not isinstance(old, (int, float)):
        return "—"
    diff = float(new) - float(old)
    return f"{diff:+.3f}"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(cell) for cell in row) + " |")
    return "\n".join(lines)


def _gate(quality: dict[str, Any] | None) -> str:
    if not quality:
        return "—"
    return "✅ PASS" if quality.get("success") else "❌ FAIL"


def _fresh(freshness: dict[str, Any] | None) -> str:
    if not freshness:
        return "—"
    return "✅ Fresh" if freshness.get("is_fresh") else "❌ Stale"


def _quality_section(quality: dict[str, Any]) -> str:
    rows = []
    for check in quality.get("checks", []):
        detail = check.get("observed_value")
        if detail is None and check.get("unexpected_count") is not None:
            detail = f"{check['unexpected_count']} unexpected"
        rows.append([check["expectation"], check.get("column") or "(table)", "✅" if check["success"] else "❌", detail])
    header = (
        f"- Great Expectations version: `{quality.get('great_expectations_version')}`\n"
        f"- Suite: `{quality.get('suite_name')}` — {quality.get('expectations_passed')}/"
        f"{quality.get('expectations_total')} expectations pass\n"
        f"- **Quality Gate: {_gate(quality)}**\n\n"
    )
    return header + _table(["Expectation", "Column", "Pass", "Observed"], rows)


def _freshness_rows(states: list[tuple[str, dict[str, Any] | None]]) -> str:
    keys = [
        ("total_rows", "Total rows"),
        ("stale_rows", "Stale rows (age > threshold)"),
        ("stale_ratio", "Stale ratio"),
        ("max_stale_ratio", "Max stale ratio (SLA)"),
        ("latest_published", "Latest published"),
        ("oldest_published", "Oldest published"),
        ("is_fresh", "is_fresh"),
    ]
    rows = [[label] + [(fr or {}).get(key) for _, fr in states] for key, label in keys]
    return _table(["Freshness"] + [name for name, _ in states], rows)


def _by_type_table(states: list[tuple[str, dict[str, Any]]]) -> str | None:
    if not all(metrics.get("by_question_type") for _, metrics in states):
        return None
    rows = []
    for qtype in TYPE_ORDER:
        row = [qtype]
        for _, metrics in states:
            item = metrics["by_question_type"].get(qtype, {})
            row.append(f"{_fmt(item.get('retrieval_hit_rate'), 2)} / {_fmt(item.get('mean_token_f1'), 2)}")
        rows.append(row)
    return _table(["Question type"] + [f"{name} (Hit / F1)" for name, _ in states], rows)


# ---------------------------------------------------------------------------
# Phase 1 report
# ---------------------------------------------------------------------------
def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Viet markdown report cho baseline phase."""
    source_rows = [[key, value] for key, value in source_summary.items()]
    metric_rows = [[label, _num(metrics.get(key))] for key, label in METRIC_KEYS]
    metric_rows.insert(0, ["Samples", metrics.get("samples")])
    if metrics.get("judge_backend"):
        metric_rows.append(["Judge backend", metrics["judge_backend"]])

    by_type = _by_type_table([("Baseline", metrics)])
    hit = metrics.get("retrieval_hit_rate") or 0.0
    f1 = metrics.get("mean_token_f1") or 0.0
    conclusion = [
        f"- Quality Gate {_gate(quality)} và Freshness {_fresh(freshness)} "
        f"(stale ratio {_fmt(freshness.get('stale_ratio'))} ≤ {_fmt(freshness.get('max_stale_ratio'))} là đạt SLA).",
        f"- Retrieval Hit Rate = {_fmt(hit)}, Mean Token F1 = {_fmt(f1)} trên {metrics.get('samples')} câu hỏi cố định. "
        "Đây là mốc chuẩn (baseline) dùng để so sánh với trạng thái Corrupted và Repaired.",
    ]

    sections = [
        "# Phase 1 Report — Baseline Pipeline",
        f"_Generated at {now_utc().isoformat()} bởi `script/run_phase1.py` (số liệu sinh tự động, không sửa tay)._",
        "## 1. Nguồn dữ liệu & cấu hình",
        _table(["Thuộc tính", "Giá trị"], source_rows),
        "## 2. Baseline metrics",
        _table(["Metric", "Baseline"], metric_rows),
    ]
    if by_type:
        sections += ["### Theo loại câu hỏi", by_type]
    sections += [
        "## 3. Data Quality Gate (Great Expectations 1.x)",
        _quality_section(quality),
        "## 4. Freshness SLA",
        _freshness_rows([("Baseline", freshness)]),
        "## 5. Kết luận",
        "\n".join(conclusion),
    ]
    write_text(Path(report_path), "\n\n".join(sections) + "\n")


# ---------------------------------------------------------------------------
# Corruption comparison report
# ---------------------------------------------------------------------------
def build_comparison_rows(
    baseline_metrics: dict[str, Any], corrupted_metrics: dict[str, Any], repaired_metrics: dict[str, Any]
) -> list[list[Any]]:
    rows = []
    for key, label in METRIC_KEYS:
        base, corr, rep = (_num(m.get(key)) for m in (baseline_metrics, corrupted_metrics, repaired_metrics))
        rows.append([label, base, corr, rep, _delta(corr, base), _delta(rep, base)])
    return rows


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    baseline_quality: dict[str, Any] | None = None,
    baseline_freshness: dict[str, Any] | None = None,
    corruption_log: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Viet markdown report so sanh baseline/corrupted/repaired."""
    extra = extra or {}
    headers = ["Metric", "Baseline", "Corrupted", "Repaired", "Δ Corrupted", "Δ Repaired"]
    comparison = _table(headers, build_comparison_rows(baseline_metrics, corrupted_metrics, repaired_metrics))
    status_rows = [
        ["Rows", baseline_quality.get("row_count") if baseline_quality else None,
         corrupted_quality.get("row_count"), repaired_quality.get("row_count"), "", ""],
        ["Quality Gate (GX 1.x)", _gate(baseline_quality), _gate(corrupted_quality), _gate(repaired_quality), "", ""],
        ["Freshness SLA", _fresh(baseline_freshness), _fresh(corrupted_freshness), _fresh(repaired_freshness), "", ""],
    ]
    status = _table(headers, status_rows)

    # Bang expectations theo 3 trang thai
    exp_rows = []
    checks = {
        name: {(c["expectation"], c.get("column")): c for c in (q or {}).get("checks", [])}
        for name, q in [("baseline", baseline_quality), ("corrupted", corrupted_quality), ("repaired", repaired_quality)]
    }
    for key, check in checks["corrupted"].items():
        row = [check["expectation"], key[1] or "(table)"]
        for name in ["baseline", "corrupted", "repaired"]:
            item = checks[name].get(key)
            if item is None:
                row.append("—")
            else:
                note = f" ({item['unexpected_count']} lỗi)" if item.get("unexpected_count") else ""
                row.append(("✅" if item["success"] else "❌") + note)
        exp_rows.append(row)
    expectations = _table(["Expectation", "Column", "Baseline", "Corrupted", "Repaired"], exp_rows)

    # Corruption log
    log_rows = []
    for scenario in (corruption_log or {}).get("scenarios", []):
        log_rows.append([scenario["scenario"], scenario["description"], scenario["affected_rows"]])
    log_table = _table(["Scenario", "Mô tả", "Rows ảnh hưởng"], log_rows) if log_rows else "_Không có corruption log._"

    # Phan tich tu dong dua tren so lieu
    analysis: list[str] = []
    drops = []
    for key, label in METRIC_KEYS:
        base, corr = baseline_metrics.get(key), corrupted_metrics.get(key)
        if isinstance(base, (int, float)) and isinstance(corr, (int, float)) and float(base) > 0:
            # So sanh theo % tuong doi vi cac metric khac thang do (0-1 va 1-5)
            drops.append(((float(base) - float(corr)) / float(base), label, float(base), float(corr)))
    if drops:
        worst = max(drops)
        analysis.append(
            f"- **Suy giảm lớn nhất (tương đối):** {worst[1]} giảm từ {_fmt(worst[2])} xuống {_fmt(worst[3])} "
            f"(-{worst[0] * 100:.1f}%) khi dữ liệu bị tiêm lỗi. Mức giảm các metric khác: "
            + ", ".join(f"{label} -{drop * 100:.1f}%" for drop, label, _, _ in drops if label != worst[1])
            + "."
        )
    silent = extra.get("silent_failures")
    if silent is not None:
        analysis.append(
            f"- **Silent failure:** trên dữ liệu lỗi, pipeline không crash và không có exception nào; agent trả lời "
            f"{extra.get('corrupted_non_empty_answers')}/{corrupted_metrics.get('samples')} câu một cách bình thường. "
            f"Tuy nhiên {silent} câu là thất bại thầm lặng: {extra.get('wrong_content', 0)} câu sai nội dung "
            f"(Token F1 < 0.5) và {extra.get('wrong_source', 0)} câu không truy xuất được tài liệu gốc "
            f"(trả lời dựa trên tài liệu khác). Ngoài ra {extra.get('empty_answers', 0)} câu trả lời rỗng. "
            "Lỗi chỉ lộ ra khi đo metrics hoặc nhờ Quality Gate."
        )
    analysis.append(
        f"- **Observability:** Quality Gate trên dữ liệu lỗi = {_gate(corrupted_quality)} "
        f"(vi phạm: {', '.join(corrupted_quality.get('failed_expectations') or []) or 'không có'}); "
        f"Freshness = {_fresh(corrupted_freshness)} (stale ratio {_fmt(corrupted_freshness.get('stale_ratio'))})."
    )
    recovered = all(
        isinstance(repaired_metrics.get(k), (int, float))
        and abs(float(repaired_metrics[k]) - float(baseline_metrics.get(k, 0))) < 1e-9
        for k, _ in METRIC_KEYS
        if isinstance(baseline_metrics.get(k), (int, float))
    )
    analysis.append(
        "- **Repair:** "
        + ("các metrics sau repair trùng khớp hoàn toàn với baseline." if recovered
           else "metrics sau repair chưa trùng hoàn toàn với baseline — xem bảng trên để biết chênh lệch.")
        + f" Quality Gate sau repair = {_gate(repaired_quality)}, Freshness = {_fresh(repaired_freshness)}."
    )
    if "repair_idempotent" in extra:
        analysis.append(
            f"- **Idempotent:** chạy repair 2 lần liên tiếp cho dataset giống hệt nhau = {_fmt(extra['repair_idempotent'])}; "
            f"repaired dataset trùng với baseline clean dataset = {_fmt(extra.get('repaired_matches_baseline'))}."
        )
    if extra.get("repair_trigger"):
        analysis.append(f"- **Kích hoạt repair:** {extra['repair_trigger']}")

    sections = [
        "# Corruption & Repair Report — Baseline vs Corrupted vs Repaired",
        f"_Generated at {now_utc().isoformat()} bởi `script/run_corruption_flow.py` (số liệu sinh tự động, không sửa tay)._",
        "Cả 3 trạng thái được đánh giá trên **cùng một** `data/eval/test_set.json`, cùng embedding model và cùng `top_k`.",
        "## 1. Bảng đối chiếu 3 trạng thái",
        comparison,
        "### Trạng thái dữ liệu",
        status,
    ]
    by_type = _by_type_table([("Baseline", baseline_metrics), ("Corrupted", corrupted_metrics), ("Repaired", repaired_metrics)])
    if by_type:
        sections += ["### Theo loại câu hỏi", by_type]
    sections += [
        "## 2. Các kịch bản lỗi đã tiêm",
        log_table,
        "## 3. Data Quality Gate theo từng expectation",
        expectations,
        "## 4. Freshness SLA",
        _freshness_rows([("Baseline", baseline_freshness), ("Corrupted", corrupted_freshness), ("Repaired", repaired_freshness)]),
        "## 5. Phân tích",
        "\n".join(analysis),
    ]
    write_text(Path(report_path), "\n\n".join(sections) + "\n")
