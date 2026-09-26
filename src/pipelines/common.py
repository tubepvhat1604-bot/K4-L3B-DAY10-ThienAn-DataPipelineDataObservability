"""Helper dung chung cho phase1 va corruption_flow."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

import pandas as pd

from core.config import Settings, normalized_provider
from core.utils import read_json, write_csv, write_json
from evaluation.metrics import EvaluationBundle, evaluate_pipeline
from retrieval.index import LocalEmbeddingIndex

LIST_COLUMNS = ["authors", "categories"]
# Cot noi dung dung de so sanh repaired vs baseline (bo age_days vi phu thuoc ngay chay)
CONTENT_COLUMNS = [
    "paper_id", "title", "summary", "authors_joined", "categories_joined", "published", "text_for_embedding",
]


def configure_console() -> None:
    """Ep stdout UTF-8 de Windows PowerShell/cmd khong crash khi in tieng Viet hoac ky tu Δ."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def save_dataframe(df: pd.DataFrame, csv_path: Path, json_path: Path) -> None:
    write_json(json_path, df.to_dict(orient="records"))
    csv_df = df.copy()
    for column in LIST_COLUMNS:
        if column in csv_df.columns:
            csv_df[column] = csv_df[column].apply(lambda items: "; ".join(items) if isinstance(items, list) else items)
    write_csv(csv_df, csv_path)


def load_dataframe(json_path: Path) -> pd.DataFrame:
    return pd.DataFrame(read_json(json_path))


def fingerprint(df: pd.DataFrame, columns: list[str] | None = None) -> str:
    frame = df[columns] if columns else df
    payload = json.dumps(frame.to_dict(orient="records"), sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_set_matches(test_set_path: Path, df: pd.DataFrame) -> bool:
    if not test_set_path.exists():
        return False
    ids = set(df["paper_id"].astype(str))
    items = read_json(test_set_path)
    return bool(items) and all(doc_id in ids for item in items for doc_id in item["ground_truth_doc_ids"])


def _by_question_type(answers: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in answers:
        groups.setdefault(item["question_type"], []).append(item)
    return {
        qtype: {
            "samples": len(items),
            "retrieval_hit_rate": mean(1.0 if i["retrieval_hit"] else 0.0 for i in items),
            "mean_token_f1": mean(i["token_f1"] for i in items),
        }
        for qtype, items in groups.items()
    }


def _judge_backend(settings: Settings, answers: list[dict[str, Any]]) -> str:
    fallback = sum(1 for item in answers if str(item["judge"].get("reasoning", "")).startswith("Fallback"))
    llm = f"llm:{normalized_provider(settings)}/{settings.model_name}"
    if fallback == 0:
        return llm
    if fallback == len(answers):
        return "heuristic_fallback (LLM judge unavailable)"
    return f"mixed ({len(answers) - fallback} {llm}, {fallback} heuristic_fallback)"


def evaluate_state(
    settings: Settings,
    df: pd.DataFrame,
    embeddings_path: Path,
    metrics_path: Path,
    answers_path: Path,
) -> tuple[LocalEmbeddingIndex, EvaluationBundle, dict[str, Any]]:
    """Build Chroma collection cho 1 trang thai, evaluate tren test set chung va bo sung metrics phu."""
    index = LocalEmbeddingIndex.build(df, settings, embeddings_path)
    bundle = evaluate_pipeline(settings, index, settings.paths.eval_testset, metrics_path, answers_path)
    summary = dict(bundle.summary)
    summary["collection_name"] = index.collection_name
    summary["indexed_documents"] = len(index.documents)
    summary["judge_backend"] = _judge_backend(settings, bundle.answers)
    summary["by_question_type"] = _by_question_type(bundle.answers)
    write_json(metrics_path, summary)
    return index, bundle, summary


def print_metrics(title: str, metrics: dict[str, Any]) -> None:
    print(f"\n[{title}]")
    for key in ["samples", "retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score", "judge_backend"]:
        value = metrics.get(key)
        print(f"  {key:<20} {value:.3f}" if isinstance(value, float) else f"  {key:<20} {value}")


def update_dashboard(settings: Settings, runs: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any] | None]]) -> None:
    """Bonus B1: ghi lich su chay + sinh lai dashboard. Loi dashboard khong lam hong pipeline."""
    try:
        from observability.dashboard import build_dashboard, record_run

        for stage, quality, freshness, metrics in runs:
            record_run(settings, stage, quality, freshness, metrics)
        path = build_dashboard(settings)
        print(f"[dashboard] -> {path.relative_to(settings.paths.project_dir)}")
    except Exception as exc:  # pragma: no cover - dashboard la tien ich phu
        print(f"[dashboard] Bo qua do loi: {exc}")
