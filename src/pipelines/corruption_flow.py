from __future__ import annotations

from typing import Any

from core.config import load_settings
from core.utils import now_utc, read_json
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import build_comparison_rows, generate_corruption_report
from pipelines.common import (
    configure_console,
    CONTENT_COLUMNS,
    evaluate_state,
    fingerprint,
    load_dataframe,
    print_metrics,
    save_dataframe,
    test_set_matches,
    update_dashboard,
)


def _read_optional(path) -> dict[str, Any] | None:
    return read_json(path) if path.exists() else None


def repair_from_raw(settings, run_date):
    """Idempotent repair: tai tao clean dataset tu raw records (nguon tin cay duy nhat)."""
    return build_clean_dataframe(load_raw_records(settings.paths.raw_records_json), run_date)


def main() -> None:
    """Corruption -> evaluate -> detect -> repair -> evaluate -> compare (3 trang thai)."""
    configure_console()
    settings = load_settings()
    paths = settings.paths
    run_date = now_utc()

    # 1. Load baseline artifacts (bat buoc chay phase1 truoc)
    required = [paths.clean_json, paths.eval_testset, paths.baseline_metrics, paths.raw_records_json]
    missing = [str(p.relative_to(paths.project_dir)) for p in required if not p.exists()]
    if missing:
        raise SystemExit(f"[corruption] Thieu artifact {missing}. Hay chay `python script/run_phase1.py` truoc.")
    baseline_df = load_dataframe(paths.clean_json)
    if not test_set_matches(paths.eval_testset, baseline_df):
        raise SystemExit("[corruption] test_set.json khong khop clean dataset. Chay lai run_phase1.py.")
    baseline_metrics = read_json(paths.baseline_metrics)
    baseline_quality = _read_optional(paths.baseline_quality_report)
    baseline_freshness = _read_optional(paths.freshness_report)

    # 2-3. Tiem loi + luu artifact
    corrupted_df = corrupt_clean_dataframe(baseline_df, paths.corruption_log)
    save_dataframe(corrupted_df, paths.corrupted_clean_csv, paths.corrupted_clean_json)
    corruption_log = read_json(paths.corruption_log)
    print(f"[corruption] Tiem {corruption_log['scenario_count']} loai loi: {len(baseline_df)} -> {len(corrupted_df)} rows")

    # 5. Observability tren du lieu loi
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    corrupted_freshness = build_freshness_report(
        corrupted_df, settings, paths.freshness_report.with_name("freshness_report_corrupted.json")
    )
    print(f"[corruption] Quality Gate: {'PASS' if corrupted_quality['success'] else 'FAIL'} "
          f"{corrupted_quality['failed_expectations']} | Freshness: "
          f"{'FRESH' if corrupted_freshness['is_fresh'] else 'STALE'} (stale ratio {corrupted_freshness['stale_ratio']})")

    # 4. Co y bo qua gate de do tac hai neu du lieu loi lot vao vector store (silent failure)
    _, corrupted_bundle, corrupted_metrics = evaluate_state(
        settings, corrupted_df, paths.corrupted_embeddings_json, paths.corrupted_metrics, paths.corrupted_answers
    )
    print_metrics("Corrupted metrics", corrupted_metrics)
    answered = [item for item in corrupted_bundle.answers if str(item["answer"]).strip()]
    wrong_content = sum(1 for item in answered if item["token_f1"] < 0.5)
    wrong_source = sum(1 for item in answered if not item["retrieval_hit"])
    silent_failures = sum(1 for item in answered if item["token_f1"] < 0.5 or not item["retrieval_hit"])

    # 6. Tu dong kich hoat repair khi observability phat hien van de
    alerts = []
    if not corrupted_quality["success"]:
        alerts.append(f"Quality Gate FAIL ({len(corrupted_quality['failed_expectations'])} expectations)")
    if not corrupted_freshness["is_fresh"]:
        alerts.append(f"Freshness SLA vi pham (stale ratio {corrupted_freshness['stale_ratio']})")
    trigger = (
        "Tự động kích hoạt vì " + "; ".join(alerts) + "."
        if alerts else "Observability không phát hiện lỗi — repair chạy theo lịch (không có cảnh báo)."
    )
    print(f"[repair] {trigger}")

    repaired_df = repair_from_raw(settings, run_date)
    repaired_again = repair_from_raw(settings, run_date)
    idempotent = fingerprint(repaired_df) == fingerprint(repaired_again)
    matches_baseline = fingerprint(repaired_df, CONTENT_COLUMNS) == fingerprint(baseline_df, CONTENT_COLUMNS)
    save_dataframe(repaired_df, paths.repaired_clean_csv, paths.repaired_clean_json)
    print(f"[repair] Rebuild tu raw: {len(repaired_df)} rows | idempotent={idempotent} | matches_baseline={matches_baseline}")

    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    repaired_freshness = build_freshness_report(
        repaired_df, settings, paths.freshness_report.with_name("freshness_report_repaired.json")
    )
    if not repaired_quality["success"]:
        raise SystemExit(f"[repair] Du lieu repair van FAIL quality gate: {repaired_quality['failed_expectations']}")

    # 7. Evaluate repaired
    _, _, repaired_metrics = evaluate_state(
        settings, repaired_df, paths.repaired_embeddings_json, paths.repaired_metrics, paths.repaired_answers
    )
    print_metrics("Repaired metrics", repaired_metrics)

    # 8. Comparison report
    generate_corruption_report(
        paths.comparison_report,
        baseline_metrics,
        corrupted_metrics,
        repaired_metrics,
        corrupted_quality,
        repaired_quality,
        corrupted_freshness,
        repaired_freshness,
        baseline_quality=baseline_quality,
        baseline_freshness=baseline_freshness,
        corruption_log=corruption_log,
        extra={
            "silent_failures": silent_failures,
            "wrong_content": wrong_content,
            "wrong_source": wrong_source,
            "empty_answers": len(corrupted_bundle.answers) - len(answered),
            "corrupted_non_empty_answers": len(answered),
            "repair_idempotent": idempotent,
            "repaired_matches_baseline": matches_baseline,
            "repair_trigger": trigger,
        },
    )

    update_dashboard(settings, [
        ("corrupted", corrupted_quality, corrupted_freshness, corrupted_metrics),
        ("repaired", repaired_quality, repaired_freshness, repaired_metrics),
    ])

    print("\n" + "=" * 86)
    print(f"{'Metric':<24}{'Baseline':>12}{'Corrupted':>12}{'Repaired':>12}{'Δ Corr':>13}{'Δ Rep':>13}")
    print("-" * 86)
    for label, base, corr, rep, d_corr, d_rep in build_comparison_rows(baseline_metrics, corrupted_metrics, repaired_metrics):
        print(f"{label:<24}{base:>12.3f}{corr:>12.3f}{rep:>12.3f}{d_corr:>13}{d_rep:>13}")
    print("=" * 86)
    print(f"[corruption] DONE -> {paths.comparison_report.relative_to(paths.project_dir)}")
