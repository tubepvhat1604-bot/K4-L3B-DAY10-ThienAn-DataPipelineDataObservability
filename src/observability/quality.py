from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import great_expectations as gx
import pandas as pd

from core.config import Settings
from core.utils import now_utc, write_json

# Nguong cua Quality Gate (dat 1 cho de ca nhom thong nhat va de doi khi can)
MIN_ROWS = 5
MAX_ROWS = 5000
MIN_SUMMARY_CHARS = 30
MIN_TITLE_CHARS = 8
MAX_STALE_RATIO = 0.25  # > 25% bai bao qua han -> is_fresh = False
REQUIRED_NOT_NULL = ["paper_id", "title", "text_for_embedding"]

logging.getLogger("great_expectations").setLevel(logging.ERROR)


def _prepare_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Chi dua cac cot scalar can kiem tra vao GX (cot list nhu `authors` khong hash duoc)."""
    frame = pd.DataFrame(index=df.index)
    for column in ["paper_id", "title", "summary", "text_for_embedding"]:
        frame[column] = df[column] if column in df.columns else None
    frame["age_days"] = pd.to_numeric(df.get("age_days"), errors="coerce")
    # Chuoi rong/khoang trang duoc coi la NULL: day chinh la loi "silent" hay gap nhat.
    for column in ["paper_id", "title", "text_for_embedding"]:
        frame[column] = frame[column].where(frame[column].astype(str).str.strip() != "", None)
    return frame.reset_index(drop=True)


def _disable_progress_bars(context: Any) -> None:
    try:
        from great_expectations.data_context.types.base import ProgressBarsConfig

        context.variables.progress_bars = ProgressBarsConfig(globally=False, metric_calculations=False)
    except Exception:  # pragma: no cover - chi la tien ich hien thi
        pass


def _build_expectations() -> list[Any]:
    expectations: list[Any] = [
        # 1. Row count trong nguong hop le
        gx.expectations.ExpectTableRowCountToBeBetween(min_value=MIN_ROWS, max_value=MAX_ROWS),
    ]
    # 2. Cot quan trong khong duoc null
    for column in REQUIRED_NOT_NULL:
        expectations.append(gx.expectations.ExpectColumnValuesToNotBeNull(column=column))
    expectations += [
        # 3. Moi paper_id la duy nhat (chan duplicate index)
        gx.expectations.ExpectColumnValuesToBeUnique(column="paper_id"),
        # 4. Summary du dai de AI doc hieu (chan blank summary)
        gx.expectations.ExpectColumnValueLengthsToBeBetween(column="summary", min_value=MIN_SUMMARY_CHARS),
        # (Mo rong) Title khong bi cat ngan
        gx.expectations.ExpectColumnValueLengthsToBeBetween(column="title", min_value=MIN_TITLE_CHARS),
    ]
    return expectations


def _summarize_result(result: Any) -> dict[str, Any]:
    config = result.expectation_config
    kwargs = {key: value for key, value in dict(config.kwargs).items() if key not in {"batch_id"}}
    raw = dict(result.result or {})
    return {
        "expectation": config.type,
        "column": kwargs.get("column"),
        "kwargs": kwargs,
        "success": bool(result.success),
        "observed_value": raw.get("observed_value"),
        "element_count": raw.get("element_count"),
        "unexpected_count": raw.get("unexpected_count"),
        "unexpected_percent": raw.get("unexpected_percent"),
        "partial_unexpected_list": [str(item)[:80] for item in (raw.get("partial_unexpected_list") or [])[:5]],
    }


def compute_freshness(df: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    """Freshness SLA: ti le bai co age_days > threshold khong duoc vuot MAX_STALE_RATIO."""
    total_rows = int(len(df))
    threshold = int(settings.freshness_threshold_days)
    age_days = pd.to_numeric(df.get("age_days", pd.Series(dtype=float)), errors="coerce")
    stale_rows = int((age_days > threshold).sum())
    stale_ratio = stale_rows / total_rows if total_rows else 1.0
    published = pd.to_datetime(df.get("published", pd.Series(dtype=str)), errors="coerce")
    return {
        "freshness_threshold_days": threshold,
        "max_stale_ratio": MAX_STALE_RATIO,
        "total_rows": total_rows,
        "stale_rows": stale_rows,
        "stale_ratio": round(stale_ratio, 4),
        "latest_published": published.max().strftime("%Y-%m-%d") if published.notna().any() else None,
        "oldest_published": published.min().strftime("%Y-%m-%d") if published.notna().any() else None,
        "min_age_days": int(age_days.min()) if age_days.notna().any() else None,
        "max_age_days": int(age_days.max()) if age_days.notna().any() else None,
        "is_fresh": bool(total_rows > 0 and stale_ratio <= MAX_STALE_RATIO),
    }


def quality_report_path(settings: Settings, report_name: str) -> Path:
    mapping = {
        "baseline": settings.paths.baseline_quality_report,
        "corrupted": settings.paths.corrupted_quality_report,
    }
    return mapping.get(report_name, settings.paths.quality_dir / f"{report_name}_quality_report.json")


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Quality Gate chuan Great Expectations 1.x (ephemeral context, pandas data source).

    `success` = tat ca expectations deu pass. Freshness duoc tinh kem trong key `freshness`
    (SLA van hanh, khong chan gate) va `overall_healthy` = success AND is_fresh.
    Ket qua ghi vao `data/quality/<report_name>_quality_report.json`.
    """
    frame = _prepare_frame(df)

    context = gx.get_context(mode="ephemeral")
    _disable_progress_bars(context)
    data_source = context.data_sources.add_pandas(name="papers_source")
    data_asset = data_source.add_dataframe_asset(name="papers_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe("papers_batch")
    batch = batch_def.get_batch(batch_parameters={"dataframe": frame})

    suite = context.suites.add(gx.ExpectationSuite(name=f"papers_quality_suite_{report_name}"))
    for expectation in _build_expectations():
        suite.add_expectation(expectation)

    validation = batch.validate(suite)
    checks = [_summarize_result(item) for item in validation.results]
    freshness = compute_freshness(df, settings)
    gx_success = bool(validation.success)

    report = {
        "report_name": report_name,
        "evaluated_at": now_utc().isoformat(),
        "great_expectations_version": gx.__version__,
        "suite_name": suite.name,
        "row_count": int(len(df)),
        "success": gx_success,
        "expectations_total": len(checks),
        "expectations_passed": sum(1 for check in checks if check["success"]),
        "failed_expectations": [
            f"{check['expectation']}({check['column'] or 'table'})" for check in checks if not check["success"]
        ],
        "checks": checks,
        "freshness": freshness,
        "overall_healthy": bool(gx_success and freshness["is_fresh"]),
    }
    write_json(quality_report_path(settings, report_name), report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Tong hop freshness report va ghi JSON ra `report_path`."""
    payload = {"generated_at": now_utc().isoformat(), **compute_freshness(df, settings)}
    write_json(Path(report_path), payload)
    return payload
