from __future__ import annotations

from collections import Counter

import pandas as pd
import pytest

from core.utils import read_json
from evaluation.testset import build_test_set
from ingestion.corruption import corrupt_clean_dataframe
from observability.quality import build_freshness_report, compute_freshness, run_data_quality_checks


def test_gx_gate_passes_on_clean_data(clean_df, settings):
    report = run_data_quality_checks(clean_df, settings, "baseline")
    assert report["success"] is True
    assert report["great_expectations_version"].startswith("1.")
    types = {check["expectation"] for check in report["checks"]}
    assert {
        "expect_table_row_count_to_be_between",
        "expect_column_values_to_not_be_null",
        "expect_column_values_to_be_unique",
        "expect_column_value_lengths_to_be_between",
    } <= types
    assert settings.paths.baseline_quality_report.exists()
    assert report["freshness"]["is_fresh"] is True


def test_gx_gate_fails_on_corrupted_data(clean_df, settings, tmp_path):
    corrupted = corrupt_clean_dataframe(clean_df, tmp_path / "log.json")
    report = run_data_quality_checks(corrupted, settings, "corrupted")
    assert report["success"] is False
    failed = " ".join(report["failed_expectations"])
    assert "unique(paper_id)" in failed and "(summary)" in failed and "(title)" in failed
    assert report["overall_healthy"] is False
    assert read_json(settings.paths.corrupted_quality_report)["success"] is False


def test_gx_gate_treats_blank_as_null_and_checks_row_count(clean_df, settings):
    tiny = clean_df.head(3).copy()
    tiny.loc[tiny.index[0], "paper_id"] = "  "
    report = run_data_quality_checks(tiny, settings, "tiny")
    assert "expect_table_row_count_to_be_between(table)" in report["failed_expectations"]
    assert "expect_column_values_to_not_be_null(paper_id)" in report["failed_expectations"]
    assert (settings.paths.quality_dir / "tiny_quality_report.json").exists()


def test_freshness_sla(clean_df, settings):
    report = build_freshness_report(clean_df, settings, settings.paths.freshness_report)
    assert report["total_rows"] == 24 and report["stale_rows"] == 1 and report["is_fresh"] is True
    assert report["latest_published"] == "2026-07-22"
    stale = clean_df.assign(age_days=clean_df["age_days"] + 365)
    assert compute_freshness(stale, settings)["is_fresh"] is False
    empty = compute_freshness(pd.DataFrame(columns=clean_df.columns), settings)
    assert empty["is_fresh"] is False and empty["latest_published"] is None


def test_build_test_set(clean_df, settings):
    test_set = build_test_set(clean_df, settings.paths.eval_testset)
    assert len(test_set) == 10
    assert Counter(item["question_type"] for item in test_set) == {"summary": 3, "authors": 3, "date": 2, "categories": 2}
    ids = set(clean_df["paper_id"])
    assert len({item["ground_truth_doc_ids"][0] for item in test_set}) == 10
    for item in test_set:
        assert set(item) == {"id", "question_type", "question", "ground_truth", "ground_truth_doc_ids"}
        assert item["ground_truth_doc_ids"][0] in ids and item["ground_truth"]
    assert read_json(settings.paths.eval_testset) == test_set


def test_build_test_set_edge_cases(clean_df, settings):
    with pytest.raises(ValueError):
        build_test_set(clean_df.head(3), settings.paths.eval_testset)
    quoted = clean_df.copy()
    quoted.loc[quoted.index[0], "title"] = "It's quoted"
    items = build_test_set(quoted, settings.paths.eval_testset)
    assert all("It's" not in item["question"] for item in items)
    assert len(build_test_set(clean_df.head(6), settings.paths.eval_testset)) == 6
