from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from core.utils import compact_join
from ingestion.crossref import PaperRecord, clean_text

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "age_days",
    "abs_url",
    "pdf_url",
    "comment",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "text_for_embedding",
]


def build_text_for_embedding(row: dict[str, Any] | pd.Series) -> str:
    """Ghep 5 phan (Title/Authors/Published/Categories/Summary) thanh ngu canh de embed."""
    return "\n".join(
        [
            f"Title: {row['title']}",
            f"Authors: {row['authors_joined']}",
            f"Published: {row['published']}",
            f"Categories: {row['categories_joined']}",
            f"Summary: {row['summary']}",
        ]
    )


def refresh_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Tinh lai cac cot phu thuoc (dung chung cho cleaning va corruption)."""
    df = df.copy()
    df["authors_joined"] = df["authors"].apply(lambda items: compact_join(items or []))
    df["categories_joined"] = df["categories"].apply(lambda items: compact_join(items or []))
    df["summary_chars"] = df["summary"].fillna("").astype(str).str.len().astype(int)
    df["text_for_embedding"] = df.apply(build_text_for_embedding, axis=1)
    return df


def _to_utc_date(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clean_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [part for part in values.split(",")]
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        if text and text.lower() not in seen:
            seen.add(text.lower())
            cleaned.append(text)
    return cleaned


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records thanh dataframe san sang de embed.

    Quy tac:
    1. Chuan hoa text: bo tag JATS/HTML, decode entity, gom khoang trang.
    2. Parse `published`/`updated` -> 'YYYY-MM-DD' (luu dang string de ChromaDB nhan metadata).
    3. `age_days = (run_date - published).days`.
    4. Tao cot helper `authors_joined`, `categories_joined`, `summary_chars`, `text_for_embedding`.
    5. Loai row thieu paper_id/title/summary/published hop le; khu trung theo `paper_id`
       (khong phan biet hoa thuong, giu ban `updated` moi nhat).
    6. Sort theo published giam dan, paper_id tang dan.
    Ham thuan tuy (khong side effect) -> chay lai nhieu lan cho ket qua giong nhau (idempotent).
    """
    run_day = _to_utc_date(run_date).date()
    rows = [asdict(record) if isinstance(record, PaperRecord) else dict(record) for record in records]
    df = pd.DataFrame(rows, columns=[c for c in CLEAN_COLUMNS if c not in {
        "age_days", "authors_joined", "categories_joined", "summary_chars", "text_for_embedding"}])
    if df.empty:
        return pd.DataFrame(columns=CLEAN_COLUMNS)

    for column in ["paper_id", "title", "summary", "primary_category", "abs_url", "pdf_url", "comment"]:
        df[column] = df[column].apply(clean_text)
    df["authors"] = df["authors"].apply(_clean_list)
    df["categories"] = df["categories"].apply(_clean_list)
    df["primary_category"] = df.apply(
        lambda row: row["primary_category"] or (row["categories"][0] if row["categories"] else ""), axis=1
    )

    published = pd.to_datetime(df["published"], errors="coerce", utc=True)
    updated = pd.to_datetime(df["updated"], errors="coerce", utc=True).fillna(published)
    df["published"] = published.dt.strftime("%Y-%m-%d")
    df["updated"] = updated.dt.strftime("%Y-%m-%d")

    # Filter row xau
    valid = (
        (df["paper_id"] != "")
        & (df["title"] != "")
        & (df["summary"] != "")
        & published.notna()
    )
    df = df[valid].copy()

    # Khu trung lap theo paper_id: giu ban cap nhat moi nhat
    df["_key"] = df["paper_id"].str.lower()
    df = df.sort_values(["_key", "updated"], ascending=[True, False], kind="stable")
    df = df.drop_duplicates(subset="_key", keep="first").drop(columns="_key")

    df["age_days"] = df["published"].apply(
        lambda value: (run_day - datetime.strptime(value, "%Y-%m-%d").date()).days
    ).astype(int)
    df = refresh_derived_columns(df)

    df = df.sort_values(["published", "paper_id"], ascending=[False, True], kind="stable").reset_index(drop=True)
    return df[CLEAN_COLUMNS]
