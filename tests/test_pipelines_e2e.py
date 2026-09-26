from __future__ import annotations

import pandas as pd
import pytest

from core.config import load_settings
from core.utils import read_json
from observability.dashboard import build_dashboard, detect_drift
from observability.reporting import generate_corruption_report
from pipelines import corruption_flow, phase1


def test_end_to_end_phase1_and_corruption_flow(patch_settings, capsys):
    settings = load_settings(patch_settings)
    paths = settings.paths

    phase1.main()
    for path in [paths.clean_csv, paths.clean_json, paths.eval_testset, paths.baseline_metrics,
                 paths.baseline_report, paths.baseline_quality_report, paths.freshness_report]:
        assert path.exists(), path
    baseline = read_json(paths.baseline_metrics)
    assert baseline["samples"] == 10 and baseline["retrieval_hit_rate"] == 1.0
    assert "Phase 1 Report" in paths.baseline_report.read_text(encoding="utf-8")

    corruption_flow.main()
    corrupted = read_json(paths.corrupted_metrics)
    repaired = read_json(paths.repaired_metrics)
    assert corrupted["mean_token_f1"] < baseline["mean_token_f1"]
    for key in ["retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"]:
        assert repaired[key] == baseline[key]
    assert read_json(paths.corrupted_quality_report)["success"] is False
    assert read_json(paths.corruption_log)["scenario_count"] == 6
    report = paths.comparison_report.read_text(encoding="utf-8")
    assert "| Metric | Baseline | Corrupted | Repaired |" in report and "Idempotent" in report

    dashboard = (paths.baseline_report.parent / "dashboard.html").read_text(encoding="utf-8")
    assert "Baseline" in dashboard and "Corrupted" in dashboard and "Repaired" in dashboard
    history = read_json(paths.quality_dir / "run_history.json")
    assert [row["stage"] for row in history] == ["baseline", "corrupted", "repaired"]
    assert "Retrieval Hit Rate" in capsys.readouterr().out

    test_set_before = read_json(paths.eval_testset)
    phase1.main()  # chay lai: dung lai test set co dinh, metrics giong het (tai lap duoc)
    rerun = read_json(paths.baseline_metrics)
    assert read_json(paths.eval_testset) == test_set_before
    assert {k: rerun[k] for k in ["retrieval_hit_rate", "mean_token_f1"]} == {
        k: baseline[k] for k in ["retrieval_hit_rate", "mean_token_f1"]}


def test_phase1_stops_when_quality_gate_fails(patch_settings, monkeypatch):
    import pipelines.phase1 as module

    def bad_clean(records, run_date):
        return pd.DataFrame([{
            "paper_id": "x", "title": "t", "summary": "", "text_for_embedding": "t", "age_days": 1,
            "published": "2026-01-01", "authors": [], "categories": [],
        }])

    monkeypatch.setattr(module, "build_clean_dataframe", bad_clean)
    with pytest.raises(SystemExit):
        module.main()
    assert not load_settings(patch_settings).paths.embeddings_json.exists()  # du lieu xau khong vao ChromaDB


def test_corruption_flow_requires_phase1(patch_settings):
    with pytest.raises(SystemExit):
        corruption_flow.main()


def test_dashboard_and_drift_without_artifacts(settings):
    path = build_dashboard(settings)
    assert "Chưa có lần chạy nào" in path.read_text(encoding="utf-8")
    history = [
        {"timestamp": "t0", "stage": "baseline", "gate_pass": True, "failed_expectations": 0, "is_fresh": True,
         "stale_ratio": 0.0, "retrieval_hit_rate": 1.0, "mean_token_f1": 1.0},
        {"timestamp": "t1", "stage": "corrupted", "gate_pass": False, "failed_expectations": 3, "is_fresh": False,
         "stale_ratio": 0.3, "retrieval_hit_rate": 0.5, "mean_token_f1": 0.6},
    ]
    alerts = detect_drift(history)
    assert len(alerts) == 4 and detect_drift([]) == []


def test_corruption_report_handles_missing_optional_inputs(tmp_path):
    metrics = {"samples": 1, "retrieval_hit_rate": 1.0, "mean_token_f1": 1.0, "judge_accuracy": 1.0, "mean_judge_score": 5}
    quality = {"success": True, "row_count": 1, "checks": [], "failed_expectations": []}
    fresh = {"is_fresh": True, "stale_ratio": 0.0}
    out = tmp_path / "r.md"
    generate_corruption_report(out, metrics, metrics, metrics, quality, quality, fresh, fresh)
    text = out.read_text(encoding="utf-8")
    assert "Không có corruption log" in text and "trùng khớp hoàn toàn" in text
