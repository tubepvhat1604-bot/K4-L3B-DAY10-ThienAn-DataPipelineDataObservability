"""Bonus B1 — Observability dashboard + drift monitor.

Sinh 1 file HTML tu chua (`data/reports/dashboard.html`), khong can server hay CDN:
- 3 "ong nghiem" trang thai du lieu Baseline / Corrupted / Repaired (gate, freshness, metrics).
- Bieu do so sanh metrics, phan bo `age_days` voi nguong Freshness SLA.
- Ma tran Great Expectations theo tung trang thai, bang kich ban corruption.
- Lich su cac lan chay (`data/quality/run_history.json`) + canh bao drift so voi baseline gan nhat.
Dashboard duoc tu sinh lai cuoi moi lan chay pipeline; trang tu refresh 30 giay khi dang mo.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import now_utc, read_json, write_json, write_text

HISTORY_LIMIT = 50
DRIFT_TOLERANCE = 0.10  # metric giam > 10% so voi baseline gan nhat -> canh bao drift
AGE_BIN_DAYS = 30
STATES = [
    ("baseline", "Baseline", "Dữ liệu sạch sau pha 1"),
    ("corrupted", "Corrupted", "Sau khi tiêm 6 loại lỗi"),
    ("repaired", "Repaired", "Dựng lại từ raw snapshot"),
]
COLORS = {"baseline": "#1C7C93", "corrupted": "#8C6A43", "repaired": "#2E7D5B"}
METRICS = [
    ("retrieval_hit_rate", "Hit rate", 1.0),
    ("mean_token_f1", "Token F1", 1.0),
    ("judge_accuracy", "Judge accuracy", 1.0),
    ("mean_judge_score", "Judge score /5", 5.0),
]


# ---------------------------------------------------------------------------
# Run history (drift monitor)
# ---------------------------------------------------------------------------
def history_path(settings: Settings) -> Path:
    return settings.paths.quality_dir / "run_history.json"


def dashboard_path(settings: Settings) -> Path:
    return settings.paths.baseline_report.parent / "dashboard.html"


def record_run(
    settings: Settings,
    stage: str,
    quality: dict[str, Any],
    freshness: dict[str, Any],
    metrics: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Ghi 1 dong vao lich su chay de theo doi drift qua thoi gian."""
    path = history_path(settings)
    history: list[dict[str, Any]] = read_json(path) if path.exists() else []
    metrics = metrics or {}
    history.append(
        {
            "timestamp": now_utc().isoformat(timespec="seconds"),
            "stage": stage,
            "rows": quality.get("row_count"),
            "gate_pass": bool(quality.get("success")),
            "failed_expectations": len(quality.get("failed_expectations") or []),
            "is_fresh": bool(freshness.get("is_fresh")),
            "stale_ratio": freshness.get("stale_ratio"),
            "retrieval_hit_rate": metrics.get("retrieval_hit_rate"),
            "mean_token_f1": metrics.get("mean_token_f1"),
        }
    )
    history = history[-HISTORY_LIMIT:]
    write_json(path, history)
    return history


def detect_drift(history: list[dict[str, Any]]) -> list[str]:
    """So lan chay moi nhat voi baseline gan nhat truoc do."""
    if not history:
        return []
    latest = history[-1]
    alerts: list[str] = []
    if not latest["gate_pass"]:
        alerts.append(f"Lần chạy mới nhất ({latest['stage']}) không qua Quality Gate: "
                      f"{latest['failed_expectations']} expectation bị vi phạm.")
    if not latest["is_fresh"]:
        alerts.append(f"Lần chạy mới nhất ({latest['stage']}) vi phạm Freshness SLA "
                      f"(tỉ lệ bài quá hạn {_pct(latest['stale_ratio'])}).")
    reference = next((row for row in reversed(history[:-1]) if row["stage"] == "baseline"), None)
    if reference is None and latest["stage"] != "baseline":
        reference = next((row for row in history if row["stage"] == "baseline"), None)
    if reference is not None and reference is not latest:
        for key, label in [("retrieval_hit_rate", "Hit rate"), ("mean_token_f1", "Token F1")]:
            ref, cur = reference.get(key), latest.get(key)
            if isinstance(ref, (int, float)) and isinstance(cur, (int, float)) and ref > 0:
                if (ref - cur) / ref > DRIFT_TOLERANCE:
                    alerts.append(f"Drift: {label} ở lần chạy {latest['stage']} giảm từ {ref:.3f} "
                                  f"xuống {cur:.3f} so với baseline lúc {reference['timestamp']}.")
    return alerts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _read(path: Path) -> Any:
    try:
        return read_json(path) if path.exists() else None
    except Exception:
        return None


def _pct(value: Any) -> str:
    return f"{float(value) * 100:.1f}%" if isinstance(value, (int, float)) else "—"


def _num(value: Any, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}" if isinstance(value, (int, float)) and not isinstance(value, bool) else "—"


def _age_bins(df: pd.DataFrame | None) -> list[int]:
    if df is None or df.empty or "age_days" not in df:
        return []
    ages = pd.to_numeric(df["age_days"], errors="coerce").dropna().astype(int)
    return ages.tolist()


def _load_state(settings: Settings, key: str) -> dict[str, Any]:
    paths = settings.paths
    files = {
        "baseline": (paths.clean_json, paths.baseline_quality_report, paths.freshness_report, paths.baseline_metrics),
        "corrupted": (paths.corrupted_clean_json, paths.corrupted_quality_report,
                      paths.freshness_report.with_name("freshness_report_corrupted.json"), paths.corrupted_metrics),
        "repaired": (paths.repaired_clean_json, paths.quality_dir / "repaired_quality_report.json",
                     paths.freshness_report.with_name("freshness_report_repaired.json"), paths.repaired_metrics),
    }[key]
    data = _read(files[0])
    return {
        "df": pd.DataFrame(data) if data else None,
        "quality": _read(files[1]),
        "freshness": _read(files[2]),
        "metrics": _read(files[3]),
    }


# ---------------------------------------------------------------------------
# SVG pieces
# ---------------------------------------------------------------------------
def _vial_svg(key: str, state: dict[str, Any]) -> str:
    """Ong nghiem: muc chat long = so dong, do duc = ti le expectation fail."""
    quality = state["quality"] or {}
    rows = quality.get("row_count") or 0
    total = quality.get("expectations_total") or 1
    failed = total - (quality.get("expectations_passed") or 0) if quality else 0
    level = 0.25 + 0.65 * min(rows / 30, 1.0) if quality else 0.0
    murk = min(failed / total, 1.0)
    color = COLORS[key]
    top = 12 + (1 - level) * 136
    sediment = "".join(
        f'<circle cx="{18 + (i * 13) % 28}" cy="{top + 12 + (i * 29) % max(8, int(148 - top - 18))}" r="{1.4 + (i % 3) * 0.6}" '
        f'fill="#5A4127" opacity="0.7"/>'
        for i in range(int(murk * 26))
    )
    empty = '' if quality else '<text x="32" y="92" text-anchor="middle" font-size="10" fill="#5B6B77">chưa chạy</text>'
    return (
        f'<svg class="vial" viewBox="0 0 64 172" role="img" aria-label="Mẫu dữ liệu {key}">'
        f'<defs><clipPath id="tube-{key}"><path d="M14 8 H50 V146 A18 18 0 0 1 14 146 Z"/></clipPath></defs>'
        f'<g clip-path="url(#tube-{key})">'
        f'<rect x="0" y="{top:.1f}" width="64" height="172" fill="{color}" opacity="{0.28 + 0.5 * murk:.2f}"/>'
        f'<rect x="0" y="{top:.1f}" width="64" height="3" fill="{color}" opacity="0.9"/>{sediment}</g>'
        f'<path d="M14 8 H50 V146 A18 18 0 0 1 14 146 Z" fill="none" stroke="#16232E" stroke-width="1.6"/>'
        f'<path d="M8 8 H56" stroke="#16232E" stroke-width="2.4" stroke-linecap="round"/>{empty}</svg>'
    )


def _metrics_chart(states: dict[str, dict[str, Any]]) -> str:
    width, height, left, bottom = 520, 250, 40, 200
    group_w = (width - left - 10) / len(METRICS)
    bar_w = group_w / 4.6
    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="So sánh metrics 3 trạng thái">']
    for tick in [0, 0.25, 0.5, 0.75, 1.0]:
        y = bottom - tick * 170
        parts.append(f'<line x1="{left}" x2="{width - 10}" y1="{y:.1f}" y2="{y:.1f}" stroke="#C9D3DA" stroke-width="1"/>')
        parts.append(f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end" class="tick">{int(tick * 100)}%</text>')
    for m_index, (metric, label, scale) in enumerate(METRICS):
        gx0 = left + m_index * group_w + group_w * 0.12
        for s_index, (key, name, _) in enumerate(STATES):
            value = ((states[key]["metrics"] or {}).get(metric))
            if not isinstance(value, (int, float)):
                continue
            ratio = max(0.0, min(float(value) / scale, 1.0))
            x = gx0 + s_index * (bar_w + 3)
            h = ratio * 170
            parts.append(
                f'<rect x="{x:.1f}" y="{bottom - h:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{COLORS[key]}">'
                f'<title>{name} — {label}: {_num(value)}</title></rect>'
            )
        parts.append(f'<text x="{left + m_index * group_w + group_w / 2:.1f}" y="{bottom + 20}" text-anchor="middle" '
                     f'class="axis">{escape(label)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _age_histogram(key: str, ages: list[int], threshold: int, axis_max: int) -> str:
    width, height, bottom = 300, 150, 118
    if not ages:
        return f'<p class="empty">Chưa có dữ liệu {key}. Chạy pipeline để sinh artifact.</p>'
    max_age = max(axis_max, threshold + AGE_BIN_DAYS)  # truc X chung cho 3 trang thai
    bins = [0] * (max_age // AGE_BIN_DAYS + 1)
    for age in ages:
        bins[max(age, 0) // AGE_BIN_DAYS] += 1
    peak = max(bins) or 1
    bw = (width - 20) / len(bins)
    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="Phân bố tuổi bài báo {key}">']
    for index, count in enumerate(bins):
        h = count / peak * 96
        stale = index * AGE_BIN_DAYS >= threshold
        parts.append(
            f'<rect x="{10 + index * bw + 1:.1f}" y="{bottom - h:.1f}" width="{max(bw - 2, 1):.1f}" height="{h:.1f}" '
            f'fill="{"#B42318" if stale else COLORS[key]}" opacity="{0.85 if count else 0}">'
            f'<title>{index * AGE_BIN_DAYS}–{(index + 1) * AGE_BIN_DAYS - 1} ngày: {count} bài</title></rect>'
        )
    tx = 10 + threshold / AGE_BIN_DAYS * bw
    parts.append(f'<line x1="{tx:.1f}" x2="{tx:.1f}" y1="14" y2="{bottom}" stroke="#16232E" stroke-dasharray="3 3"/>')
    parts.append(f'<text x="{tx + 4:.1f}" y="22" class="tick">SLA {threshold} ngày</text>')
    parts.append(f'<line x1="10" x2="{width - 10}" y1="{bottom}" y2="{bottom}" stroke="#16232E"/>')
    parts.append(f'<text x="10" y="{bottom + 16}" class="tick">0</text>')
    parts.append(f'<text x="{width - 10}" y="{bottom + 16}" text-anchor="end" class="tick">{len(bins) * AGE_BIN_DAYS} ngày</text>')
    parts.append("</svg>")
    return "".join(parts)


def _history_chart(history: list[dict[str, Any]]) -> str:
    rows = [row for row in history if isinstance(row.get("retrieval_hit_rate"), (int, float))][-20:]
    if len(rows) < 2:
        return '<p class="empty">Cần ít nhất 2 lần chạy có metrics để vẽ xu hướng.</p>'
    width, height, left, bottom = 520, 180, 40, 150
    step = (width - left - 20) / (len(rows) - 1)
    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="Xu hướng hit rate và F1 qua các lần chạy">']
    for tick in [0, 0.5, 1.0]:
        y = bottom - tick * 130
        parts.append(f'<line x1="{left}" x2="{width - 20}" y1="{y:.1f}" y2="{y:.1f}" stroke="#C9D3DA"/>')
        parts.append(f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end" class="tick">{tick:.1f}</text>')
    for metric, dash in [("retrieval_hit_rate", ""), ("mean_token_f1", "5 4")]:
        points = " ".join(f"{left + i * step:.1f},{bottom - float(r[metric] or 0) * 130:.1f}" for i, r in enumerate(rows))
        parts.append(f'<polyline points="{points}" fill="none" stroke="#16232E" stroke-width="1.6" stroke-dasharray="{dash}"/>')
    for i, row in enumerate(rows):
        color = COLORS.get(row["stage"], "#5B6B77")
        parts.append(
            f'<circle cx="{left + i * step:.1f}" cy="{bottom - float(row["retrieval_hit_rate"]) * 130:.1f}" r="4.5" fill="{color}">'
            f'<title>{row["timestamp"]} · {row["stage"]} · hit {_num(row["retrieval_hit_rate"])} · F1 {_num(row["mean_token_f1"])}</title></circle>'
        )
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
CSS = """
:root{--bench:#E9EEF1;--panel:#F7F9FA;--ink:#16232E;--muted:#5B6B77;--rule:#C9D3DA;
--clear:#1C7C93;--murk:#8C6A43;--restored:#2E7D5B;--alarm:#B42318}
*{box-sizing:border-box}
body{margin:0;background:var(--bench);color:var(--ink);
font-family:"Public Sans","Segoe UI",system-ui,-apple-system,sans-serif;font-size:15px;line-height:1.5}
main{max-width:1120px;margin:0 auto;padding:32px 24px 64px}
header{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;
border-bottom:2px solid var(--ink);padding-bottom:14px}
h1{font-size:28px;line-height:1.15;margin:0;font-weight:650;letter-spacing:-.01em;max-width:32ch}
h2{font-size:18px;margin:0 0 4px;font-weight:650}
.sub{color:var(--muted);margin:4px 0 0}
.stamp{color:var(--muted);font-size:13px;text-align:right;font-variant-numeric:tabular-nums}
.alerts{margin:20px 0 0;border-left:4px solid var(--alarm);background:#FBEDEB;padding:12px 16px}
.alerts p{margin:2px 0}
.ok{margin:20px 0 0;border-left:4px solid var(--restored);background:#EAF4EE;padding:12px 16px}
.bench{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin-top:28px;background:var(--panel);
border:1px solid var(--rule)}
.sample{display:flex;gap:18px;padding:22px 20px;border-right:1px solid var(--rule)}
.sample:last-child{border-right:0}
.vial{width:64px;height:172px;flex:none}
.sample h2{display:flex;align-items:center;gap:8px}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block}
dl{display:grid;grid-template-columns:auto auto;gap:3px 14px;margin:10px 0 0;font-size:14px}
dt{color:var(--muted)}dd{margin:0;font-variant-numeric:tabular-nums;font-weight:600}
.pass{color:var(--restored)}.fail{color:var(--alarm)}
.row{display:grid;grid-template-columns:1.1fr .9fr;gap:28px;margin-top:36px}
section{margin-top:36px}
.chart{width:100%;height:auto;display:block}
.tick{font-size:10px;fill:var(--muted)}.axis{font-size:12px;fill:var(--ink)}
.legend{display:flex;gap:16px;font-size:13px;color:var(--muted);margin:6px 0 10px;flex-wrap:wrap}
.legend span{display:inline-flex;align-items:center;gap:6px}
.hist{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.hist h3{font-size:14px;margin:0 0 4px;font-weight:600}
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px;margin-top:10px;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--rule);vertical-align:top}
th{font-weight:600;color:var(--muted);border-bottom:1.5px solid var(--ink)}
td.c{text-align:center}
.empty{color:var(--muted);font-style:italic}
footer{margin-top:40px;color:var(--muted);font-size:13px;border-top:1px solid var(--rule);padding-top:12px}
@media (max-width:860px){.stamp{text-align:left}.bench,.hist,.row{grid-template-columns:1fr}.sample{border-right:0;border-bottom:1px solid var(--rule)}}
"""


def _sample_block(key: str, name: str, caption: str, state: dict[str, Any]) -> str:
    quality, freshness, metrics = state["quality"], state["freshness"], state["metrics"] or {}
    if quality:
        gate = '<dd class="pass">Đạt</dd>' if quality.get("success") else \
            f'<dd class="fail">Không đạt ({len(quality.get("failed_expectations") or [])})</dd>'
    else:
        gate = "<dd>—</dd>"
    if freshness:
        fresh = f'<dd class="{"pass" if freshness.get("is_fresh") else "fail"}">{_pct(freshness.get("stale_ratio"))} quá hạn</dd>'
    else:
        fresh = "<dd>—</dd>"
    return (
        f'<div class="sample">{_vial_svg(key, state)}<div>'
        f'<h2><span class="dot" style="background:{COLORS[key]}"></span>{name}</h2>'
        f'<p class="sub">{caption}</p><dl>'
        f'<dt>Số dòng</dt><dd>{(quality or {}).get("row_count", "—")}</dd>'
        f'<dt>Quality gate</dt>{gate}<dt>Freshness</dt>{fresh}'
        f'<dt>Hit rate</dt><dd>{_num(metrics.get("retrieval_hit_rate"))}</dd>'
        f'<dt>Token F1</dt><dd>{_num(metrics.get("mean_token_f1"))}</dd>'
        f"</dl></div></div>"
    )


def _expectation_table(states: dict[str, dict[str, Any]]) -> str:
    keys: list[tuple[str, str]] = []
    lookup: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for key, _, _ in STATES:
        checks = (states[key]["quality"] or {}).get("checks", [])
        lookup[key] = {(c["expectation"], c.get("column") or "(table)"): c for c in checks}
        for check_key in lookup[key]:
            if check_key not in keys:
                keys.append(check_key)
    if not keys:
        return '<p class="empty">Chưa có báo cáo Great Expectations.</p>'
    rows = []
    for expectation, column in keys:
        cells = []
        for key, _, _ in STATES:
            check = lookup[key].get((expectation, column))
            if check is None:
                cells.append('<td class="c">—</td>')
            elif check["success"]:
                cells.append('<td class="c pass">Đạt</td>')
            else:
                cells.append(f'<td class="c fail">{check.get("unexpected_count") or ""} lỗi</td>')
        rows.append(f"<tr><td>{escape(expectation)}</td><td>{escape(column)}</td>{''.join(cells)}</tr>")
    head = "".join(f'<th class="c">{name}</th>' for _, name, _ in STATES)
    return (f'<div class="table-wrap"><table><thead><tr><th>Expectation</th><th>Cột</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def _corruption_table(log: dict[str, Any] | None) -> str:
    if not log:
        return '<p class="empty">Chưa chạy corruption flow.</p>'
    rows = "".join(
        f"<tr><td>{escape(s['scenario'])}</td><td>{escape(s['description'])}</td><td>{s['affected_rows']}</td></tr>"
        for s in log.get("scenarios", [])
    )
    return (f'<div class="table-wrap"><table><thead><tr><th>Kịch bản</th><th>Mô tả</th><th>Dòng bị ảnh hưởng</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div><p class=\"sub\">Seed {log.get('seed')}: "
            f"{log.get('rows_before')} → {log.get('rows_after')} dòng.</p>")


def _history_table(history: list[dict[str, Any]]) -> str:
    if not history:
        return '<p class="empty">Chưa có lần chạy nào được ghi lại.</p>'
    rows = "".join(
        f"<tr><td>{escape(r['timestamp'].replace('T', ' ')[:19])}</td><td>{escape(r['stage'])}</td><td>{r.get('rows', '—')}</td>"
        f'<td class="{"pass" if r["gate_pass"] else "fail"}">{"Đạt" if r["gate_pass"] else "Không đạt"}</td>'
        f'<td class="{"pass" if r["is_fresh"] else "fail"}">{_pct(r.get("stale_ratio"))}</td>'
        f"<td>{_num(r.get('retrieval_hit_rate'))}</td><td>{_num(r.get('mean_token_f1'))}</td></tr>"
        for r in reversed(history[-12:])
    )
    return ('<div class="table-wrap"><table><thead><tr><th>Thời điểm (UTC)</th><th>Giai đoạn</th><th>Dòng</th>'
            '<th>Gate</th><th>Quá hạn</th><th>Hit rate</th><th>Token F1</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div>")


def build_dashboard(settings: Settings) -> Path:
    """Doc toan bo artifacts hien co va ghi `data/reports/dashboard.html`."""
    states = {key: _load_state(settings, key) for key, _, _ in STATES}
    history = _read(history_path(settings)) or []
    log = _read(settings.paths.corruption_log)
    alerts = detect_drift(history)
    threshold = settings.freshness_threshold_days

    if alerts:
        alert_html = '<div class="alerts" role="alert">' + "".join(f"<p>{escape(a)}</p>" for a in alerts) + "</div>"
    elif history:
        alert_html = '<div class="ok"><p>Lần chạy mới nhất đạt Quality Gate, Freshness SLA và không có drift.</p></div>'
    else:
        alert_html = '<div class="ok"><p>Chưa có lần chạy nào. Chạy <code>python script/run_phase1.py</code> để bắt đầu.</p></div>'

    legend = "".join(
        f'<span><i class="dot" style="background:{COLORS[k]}"></i>{n}</span>' for k, n, _ in STATES
    )
    ages = {key: _age_bins(states[key]["df"]) for key, _, _ in STATES}
    axis_max = max([max(values) for values in ages.values() if values] or [threshold])
    hists = "".join(
        f"<div><h3>{name}</h3>{_age_histogram(key, ages[key], threshold, axis_max)}</div>"
        for key, name, _ in STATES
    )
    html = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>Data observability — Crossref RAG pipeline</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600;650&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body><main>
<header><div><h1>Chất lượng dữ liệu cho RAG agent</h1>
<p class="sub">Crossref → clean → Great Expectations → ChromaDB → đánh giá. Trang tự làm mới mỗi 30 giây.</p></div>
<div class="stamp">Cập nhật {escape(now_utc().strftime("%Y-%m-%d %H:%M:%S"))} UTC<br>Ngưỡng freshness {threshold} ngày, tối đa 25% quá hạn</div></header>
{alert_html}
<div class="bench">{"".join(_sample_block(k, n, c, states[k]) for k, n, c in STATES)}</div>
<div class="row">
<section style="margin-top:0"><h2>Metrics trên cùng một test set</h2>
<div class="legend">{legend}</div>{_metrics_chart(states)}</section>
<section style="margin-top:0"><h2>Xu hướng qua các lần chạy</h2>
<div class="legend"><span>Nét liền: hit rate</span><span>Nét đứt: token F1</span><span>Màu điểm: giai đoạn</span></div>
{_history_chart(history)}</section></div>
<section><h2>Tuổi bài báo so với Freshness SLA</h2>
<p class="sub">Cột đỏ là bài vượt {threshold} ngày. Kịch bản stale date đẩy một phần dữ liệu sang vùng đỏ.</p>
<div class="hist">{hists}</div></section>
<section><h2>Great Expectations theo từng trạng thái</h2>{_expectation_table(states)}</section>
<section><h2>Các lỗi đã tiêm</h2>{_corruption_table(log)}</section>
<section><h2>Lịch sử chạy</h2>{_history_table(history)}</section>
<footer>Sinh tự động bởi <code>src/observability/dashboard.py</code> từ artifacts trong <code>data/</code>.
Tạo lại thủ công: <code>python script/build_dashboard.py</code>.</footer>
</main></body></html>
"""
    path = dashboard_path(settings)
    write_text(path, html)
    return path
