from __future__ import annotations

import os

from core.config import load_settings, normalized_provider
from core.utils import now_utc, read_json, write_json
from evaluation.testset import build_test_set
from ingestion import crossref
from ingestion.cleaning import build_clean_dataframe
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from pipelines.common import configure_console, evaluate_state, update_dashboard, print_metrics, save_dataframe, test_set_matches


def _run_agent_demo(settings, index, test_set) -> None:
    """Demo LangChain agent (tool-calling) tren 2 cau hoi; loi khong lam hong pipeline."""
    if normalized_provider(settings) == "mock" or os.getenv("RUN_AGENT_DEMO", "1").lower() in {"0", "false", "no"}:
        print("[phase1] Bo qua agent demo (LLM_PROVIDER=mock hoac RUN_AGENT_DEMO=0).")
        return
    from retrieval.agent import build_agent, run_agent_question

    answers = []
    try:
        agent = build_agent(settings, index)
        for item in test_set[:2]:
            answers.append({"question": item["question"], "answer": run_agent_question(agent, item["question"]),
                            "ground_truth": item["ground_truth"]})
    except Exception as exc:
        answers.append({"error": f"{exc.__class__.__name__}: {exc}"[:500]})
    write_json(settings.paths.demo_answers, answers)
    print(f"[phase1] Agent demo -> {settings.paths.demo_answers.relative_to(settings.paths.project_dir)}")


def main() -> None:
    """Baseline pipeline end-to-end: ingest -> clean -> quality gate -> index -> evaluate -> report."""
    configure_console()
    # 1. Settings
    settings = load_settings()
    paths = settings.paths
    run_date = now_utc()
    print(f"[phase1] Run date: {run_date.isoformat()} | LLM: {settings.llm_provider}/{settings.model_name}")

    # 2. Ingestion (offline snapshot mac dinh, REFRESH_SOURCE=1 de goi live API)
    records = crossref.fetch_source_records(settings)
    fetch_info = dict(crossref.LAST_FETCH_INFO)
    print(f"[phase1] Ingestion: {len(records)} records ({fetch_info.get('mode')})")

    # 3-4. Clean + save
    df = build_clean_dataframe(records, run_date)
    save_dataframe(df, paths.clean_csv, paths.clean_json)
    print(f"[phase1] Clean: {len(df)} rows -> {paths.clean_csv.relative_to(paths.project_dir)}")

    # Quality Gate: chan du lieu xau TRUOC khi vao vector store
    quality = run_data_quality_checks(df, settings, "baseline")
    freshness = build_freshness_report(df, settings, paths.freshness_report)
    print(f"[phase1] Quality Gate: {'PASS' if quality['success'] else 'FAIL'} | "
          f"Freshness: {'FRESH' if freshness['is_fresh'] else 'STALE'} (stale ratio {freshness['stale_ratio']})")
    if not quality["success"]:
        update_dashboard(settings, [("baseline", quality, freshness, None)])
        raise SystemExit(
            f"[phase1] Quality Gate FAIL ({', '.join(quality['failed_expectations'])}) -> dung pipeline, "
            "khong nap du lieu xau vao ChromaDB."
        )
    if not freshness["is_fresh"]:
        print("[phase1] CANH BAO: du lieu vi pham Freshness SLA, can cap nhat nguon (REFRESH_SOURCE=1).")

    # 6. Test set co dinh: chi tao moi khi chua co, khong khop dataset, hoac REFRESH_TEST_SET=1
    if settings.refresh_test_set or not test_set_matches(paths.eval_testset, df):
        test_set = build_test_set(df, paths.eval_testset)
        print(f"[phase1] Tao test set moi: {len(test_set)} cau hoi")
    else:
        test_set = read_json(paths.eval_testset)
        print(f"[phase1] Dung lai test set co san: {len(test_set)} cau hoi")

    # 5 + 7. Index Chroma `papers-baseline` + evaluate
    index, _, metrics = evaluate_state(settings, df, paths.embeddings_json, paths.baseline_metrics, paths.baseline_answers)
    print_metrics("Baseline metrics", metrics)

    # 10. Demo agent (tuy chon)
    _run_agent_demo(settings, index, test_set)

    # 9. Report
    source_summary = {
        "Source": settings.source_api,
        "Ingestion mode": fetch_info.get("mode"),
        "Ingestion note": fetch_info.get("note"),
        "Query": settings.source_query,
        "Raw items / parsed records": f"{fetch_info.get('raw_items')} / {fetch_info.get('parsed_records')}",
        "Clean rows": len(df),
        "Run date (UTC)": run_date.strftime("%Y-%m-%d"),
        "Embedding model": settings.embedding_model,
        "Chroma collection": metrics["collection_name"],
        "Indexed documents": metrics["indexed_documents"],
        "Retrieval top_k": settings.top_k,
        "LLM provider / model": f"{settings.llm_provider} / {settings.model_name}",
        "Test set": f"{len(test_set)} câu ({paths.eval_testset.relative_to(paths.project_dir).as_posix()})",
    }
    generate_phase1_report(paths.baseline_report, source_summary, metrics, quality, freshness)
    update_dashboard(settings, [("baseline", quality, freshness, metrics)])
    print(f"\n[phase1] DONE -> {paths.baseline_report.relative_to(paths.project_dir)}")
