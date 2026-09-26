from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pandas as pd

from core.utils import read_json
from ingestion.cleaning import CLEAN_COLUMNS, build_clean_dataframe
from ingestion.corruption import TRUNCATED_TITLE_CHARS, corrupt_clean_dataframe

RUN_DATE = datetime(2026, 9, 25, tzinfo=timezone.utc)


def test_clean_dataframe_schema(clean_df):
    assert len(clean_df) == 24
    assert list(clean_df.columns) == CLEAN_COLUMNS
    assert clean_df["paper_id"].is_unique
    row = clean_df.iloc[0]
    lines = row["text_for_embedding"].split("\n")
    assert [line.split(":")[0] for line in lines] == ["Title", "Authors", "Published", "Categories", "Summary"]
    assert row["age_days"] == (RUN_DATE.date() - datetime.strptime(row["published"], "%Y-%m-%d").date()).days
    assert list(clean_df["published"]) == sorted(clean_df["published"], reverse=True)


def test_clean_dedupes_and_drops_bad_rows(records):
    dirty = records + [
        replace(records[0], paper_id=records[0].paper_id.upper(), title="Older copy", updated="2000-01-01"),
        replace(records[1], title="   "),
        replace(records[2], paper_id="10.9/bad-date", published="not-a-date"),
        replace(records[3], paper_id="10.9/no-summary", summary="<jats:p> </jats:p>"),
    ]
    df = build_clean_dataframe(dirty, datetime(2026, 9, 25))  # naive datetime cung duoc
    assert len(df) == 24
    assert "Older copy" not in set(df["title"])


def test_clean_is_idempotent_and_handles_empty(records):
    first = build_clean_dataframe(records, RUN_DATE)
    second = build_clean_dataframe(records, RUN_DATE)
    pd.testing.assert_frame_equal(first, second)
    assert build_clean_dataframe([], RUN_DATE).empty


def test_corruption_injects_six_scenarios(clean_df, tmp_path):
    original = clean_df.copy(deep=True)
    log_path = tmp_path / "corruption_log.json"
    corrupted = corrupt_clean_dataframe(clean_df, log_path)
    log = read_json(log_path)

    assert [s["scenario"] for s in log["scenarios"]] == [
        "drop_latest_records", "blank_summary", "inject_noise", "truncate_title", "stale_date", "duplicate_rows",
    ]
    assert all(s["affected_rows"] > 0 for s in log["scenarios"])
    pd.testing.assert_frame_equal(clean_df, original)  # khong sua input

    newest = clean_df.sort_values("published", ascending=False)["paper_id"].head(5)
    assert not set(newest) & set(corrupted["paper_id"])
    assert (corrupted["summary"] == "").sum() >= 4
    assert (corrupted["title"].str.len() <= TRUNCATED_TITLE_CHARS).sum() >= 4
    assert corrupted["paper_id"].duplicated().any()
    assert (corrupted["age_days"] > 365).sum() >= 6
    assert corrupted["text_for_embedding"].str.contains("#@!|lorem|asdf|%%%|~~~|null|0xDEAD|<br/>").any()


def test_corruption_is_deterministic(clean_df, tmp_path):
    a = corrupt_clean_dataframe(clean_df, tmp_path / "a.json")
    b = corrupt_clean_dataframe(clean_df, tmp_path / "b.json")
    pd.testing.assert_frame_equal(a, b)


def test_corruption_small_dataset_overlaps(clean_df, tmp_path):
    small = clean_df.head(4)
    corrupted = corrupt_clean_dataframe(small, tmp_path / "log.json")
    assert len(corrupted) >= 3
