from __future__ import annotations

import random
from typing import Any

import pandas as pd

from core.utils import now_utc, write_json
from ingestion.cleaning import refresh_derived_columns

# Tham so co dinh -> moi lan chay tiem loi giong het nhau (tai lap duoc).
CORRUPTION_SEED = 42
DROP_LATEST_RATIO = 0.20
BLANK_SUMMARY_RATIO = 0.20
NOISE_RATIO = 0.20
TRUNCATE_TITLE_RATIO = 0.20
STALE_DATE_RATIO = 0.30
DUPLICATE_RATIO = 0.20
TRUNCATED_TITLE_CHARS = 6  # < 8 ky tu
STALE_SHIFT_DAYS = 365
NOISE_TOKENS = ["#@!", "lorem", "\u00ff\u00fe", "%%%", "null", "0xDEAD", "~~~", "<br/>", "asdf", "\ufffd"]


def _count(ratio: float, total: int) -> int:
    return max(1, int(round(ratio * total))) if total else 0


def _inject_noise(text: str, rng: random.Random) -> str:
    """Chen 1 token rac sau moi tu that (giu nguyen thu tu tu goc)."""
    noisy: list[str] = []
    for word in str(text).split():
        noisy.extend([word, rng.choice(NOISE_TOKENS)])
    return " ".join(noisy)


def _entry(name: str, description: str, df: pd.DataFrame, index: list[int], **params: Any) -> dict[str, Any]:
    return {
        "scenario": name,
        "description": description,
        "affected_rows": len(index),
        "affected_paper_ids": [str(df.at[i, "paper_id"]) for i in index],
        "params": params,
    }


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Gia lap 6 loai data corruption thuong gap tren cleaned dataframe.

    Thu tu: (1) drop latest -> (2) blank summary -> (3) inject noise -> (4) truncate title
    -> (5) stale date -> (6) duplicate rows; sau do rebuild `text_for_embedding`.
    Cac nhom row cho kich ban (2)-(5) la TACH BIET nhau de de quy trach nhiem tung loi.
    Dung seed co dinh -> tai lap duoc. Khong sua `df` goc.
    """
    rng = random.Random(CORRUPTION_SEED)
    original_rows = len(df)
    data = df.copy().reset_index(drop=True)
    log: list[dict[str, Any]] = []

    # 1. Drop latest records (mat du lieu tuoi)
    drop_n = _count(DROP_LATEST_RATIO, len(data))
    latest_idx = (
        data.assign(_p=pd.to_datetime(data["published"], errors="coerce"))
        .sort_values(["_p", "paper_id"], ascending=[False, True], kind="stable")
        .index[:drop_n]
        .tolist()
    )
    log.append(_entry("drop_latest_records", "Bỏ rơi các bài báo mới nhất (ingestion fail)", data, latest_idx,
                      ratio=DROP_LATEST_RATIO))
    data = data.drop(index=latest_idx).reset_index(drop=True)

    # Chia cac row con lai thanh nhom tach biet cho kich ban 2-5
    pool = list(range(len(data)))
    rng.shuffle(pool)
    sizes = {
        "blank": _count(BLANK_SUMMARY_RATIO, len(data)),
        "noise": _count(NOISE_RATIO, len(data)),
        "truncate": _count(TRUNCATE_TITLE_RATIO, len(data)),
        "stale": _count(STALE_DATE_RATIO, len(data)),
    }
    groups: dict[str, list[int]] = {}
    cursor = 0
    for name, size in sizes.items():
        chunk = pool[cursor: cursor + size]
        if len(chunk) < size:  # du lieu qua it -> cho phep chong lan
            chunk = sorted(rng.sample(range(len(data)), min(size, len(data))))
        groups[name] = sorted(chunk)
        cursor += size

    # 2. Blank summary (scraper tra ve rong)
    idx = groups["blank"]
    log.append(_entry("blank_summary", "Xóa trắng summary (scrape rỗng)", data, idx, ratio=BLANK_SUMMARY_RATIO))
    data.loc[idx, "summary"] = ""

    # 3. Inject noise vao summary
    idx = groups["noise"]
    log.append(_entry("inject_noise", "Chèn ký tự rác vào summary (lỗi encoding/HTML)", data, idx,
                      ratio=NOISE_RATIO, tokens=NOISE_TOKENS))
    for i in idx:
        data.at[i, "summary"] = _inject_noise(data.at[i, "summary"], rng)

    # 4. Truncate title (< 8 ky tu)
    idx = groups["truncate"]
    log.append(_entry("truncate_title", f"Cắt title còn {TRUNCATED_TITLE_CHARS} ký tự", data, idx,
                      ratio=TRUNCATE_TITLE_RATIO, max_chars=TRUNCATED_TITLE_CHARS))
    for i in idx:
        data.at[i, "title"] = str(data.at[i, "title"])[:TRUNCATED_TITLE_CHARS]

    # 5. Stale date (lui ngay xuat ban 365 ngay)
    idx = groups["stale"]
    log.append(_entry("stale_date", f"Lùi published về {STALE_SHIFT_DAYS} ngày trước", data, idx,
                      ratio=STALE_DATE_RATIO, shift_days=STALE_SHIFT_DAYS))
    for i in idx:
        shifted = pd.Timestamp(data.at[i, "published"]) - pd.Timedelta(days=STALE_SHIFT_DAYS)
        data.at[i, "published"] = shifted.strftime("%Y-%m-%d")
        data.at[i, "age_days"] = int(data.at[i, "age_days"]) + STALE_SHIFT_DAYS

    # 6. Duplicate rows (index trung lap)
    dup_n = _count(DUPLICATE_RATIO, len(data))
    idx = sorted(rng.sample(range(len(data)), min(dup_n, len(data))))
    log.append(_entry("duplicate_rows", "Nhân bản dòng (ingest 2 lần)", data, idx, ratio=DUPLICATE_RATIO))
    data = pd.concat([data, data.loc[idx]], ignore_index=True)

    # 7. Rebuild cot dan xuat (text_for_embedding phan anh du lieu da bi hong)
    data = refresh_derived_columns(data)

    # 8. Ghi corruption log
    write_json(
        output_log_path,
        {
            "generated_at": now_utc().isoformat(),
            "seed": CORRUPTION_SEED,
            "rows_before": original_rows,
            "rows_after": len(data),
            "scenario_count": len(log),
            "scenarios": log,
        },
    )
    return data
