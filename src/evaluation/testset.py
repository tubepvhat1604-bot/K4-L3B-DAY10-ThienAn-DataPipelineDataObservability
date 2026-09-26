from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import compact_join, first_sentence, write_json

TEST_SET_SIZE = 10
MIN_DOCUMENTS = 4
# 10 cau chia vong tron qua 4 nhom -> summary 3, authors 3, date 2, categories 2
QUESTION_TYPES = ["summary", "authors", "date", "categories"]

# Cau hoi dung dung cum tu ma `retrieval/qa.py::_extract_answer` nhan dien,
# va dat title trong dau nhay don de `index.lookup` tim chinh xac tai lieu.
QUESTION_TEMPLATES = {
    "summary": "What is the summary of the paper '{title}'?",
    "authors": "Who authored the paper '{title}'?",
    "date": "When was the paper '{title}' published?",
    "categories": "What categories does the paper '{title}' belong to?",
}


def _as_text_list(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return compact_join(value)
    return "" if value is None else str(value)


def _ground_truth(row: pd.Series, question_type: str) -> str:
    if question_type == "summary":
        return first_sentence(str(row["summary"]))
    if question_type == "authors":
        return str(row.get("authors_joined") or _as_text_list(row.get("authors")))
    if question_type == "date":
        return str(row["published"])[:10]
    return str(row.get("categories_joined") or _as_text_list(row.get("categories")))


def _pick_rows(df: pd.DataFrame, size: int) -> list[int]:
    """Chon `size` paper trai deu tren truc thoi gian (moi cau 1 paper khac nhau, tat dinh)."""
    ordered = df.sort_values(["published", "paper_id"], ascending=[False, True], kind="stable")
    positions = ordered.index.tolist()
    n = len(positions)
    if size >= n:
        return positions[:size]
    step = n / size
    return [positions[int(i * step)] for i in range(size)]


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Tao bo evaluation set tat dinh (deterministic) tu cleaned dataframe va ghi JSON."""
    if len(df) < MIN_DOCUMENTS:
        raise ValueError(f"Can it nhat {MIN_DOCUMENTS} document de tao test set, hien co {len(df)}.")
    if df["title"].astype(str).str.contains("'").any():
        # Title co dau nhay don se pha regex trich title trong qa.py -> bo khoi tap ung vien.
        df = df[~df["title"].astype(str).str.contains("'")]

    size = min(TEST_SET_SIZE, len(df))
    test_set: list[dict[str, Any]] = []
    for number, row_index in enumerate(_pick_rows(df, size), start=1):
        row = df.loc[row_index]
        question_type = QUESTION_TYPES[(number - 1) % len(QUESTION_TYPES)]
        test_set.append(
            {
                "id": f"eval_{number:03d}",
                "question_type": question_type,
                "question": QUESTION_TEMPLATES[question_type].format(title=row["title"]),
                "ground_truth": _ground_truth(row, question_type),
                "ground_truth_doc_ids": [str(row["paper_id"])],
            }
        )
    write_json(output_path, test_set)
    return test_set
