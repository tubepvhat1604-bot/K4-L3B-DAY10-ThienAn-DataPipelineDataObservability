from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import html
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 4
REQUEST_TIMEOUT_SECONDS = 30
MIN_RECORDS_FROM_LIVE = 5  # Duoi nguong nay coi nhu API tra ve bat thuong -> dung snapshot

_TAG_RE = re.compile(r"<[^>]+>")

# Thong tin lan fetch gan nhat (offline/live/fallback) de pipeline ghi vao report.
LAST_FETCH_INFO: dict[str, Any] = {}


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clean_text(value: Any) -> str:
    """Bo the JATS/HTML (vd `<jats:p>`), decode HTML entity va gom khoang trang."""
    if value is None:
        return ""
    if isinstance(value, list):
        value = " ".join(str(item) for item in value if item)
    text = html.unescape(str(value))
    text = _TAG_RE.sub(" ", text)
    return normalize_whitespace(text)


def _first(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _date_from_parts(date_obj: Any) -> str | None:
    """Crossref date: {"date-parts": [[YYYY, MM, DD]]} -> 'YYYY-MM-DD' (thieu thang/ngay -> 01)."""
    if not isinstance(date_obj, dict):
        return None
    parts = _first(date_obj.get("date-parts") or [])
    if not parts or parts[0] is None:
        date_time = date_obj.get("date-time")
        return str(date_time)[:10] if date_time else None
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 and parts[1] else 1
    day = int(parts[2]) if len(parts) > 2 and parts[2] else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def _parse_authors(raw_authors: Any) -> list[str]:
    authors: list[str] = []
    for author in raw_authors or []:
        if not isinstance(author, dict):
            continue
        name = " ".join(part for part in (author.get("given"), author.get("family")) if part)
        name = clean_text(name or author.get("name"))
        if name:
            authors.append(name)
    return authors


def _parse_item(item: dict[str, Any]) -> PaperRecord | None:
    doi = clean_text(item.get("DOI"))
    title = clean_text(_first(item.get("title")))
    summary = clean_text(item.get("abstract"))
    published = (
        _date_from_parts(item.get("published"))
        or _date_from_parts(item.get("published-online"))
        or _date_from_parts(item.get("published-print"))
        or _date_from_parts(item.get("issued"))
        or _date_from_parts(item.get("created"))
    )
    # Record khong hop le: thieu khoa dinh danh, tieu de, tom tat hoac ngay xuat ban.
    if not doi or not title or not summary or not published:
        return None

    updated = (
        _date_from_parts(item.get("updated"))
        or _date_from_parts(item.get("created"))
        or published
    )
    categories = [clean_text(subject) for subject in item.get("subject") or [] if clean_text(subject)]
    abs_url = clean_text(item.get("URL")) or f"https://doi.org/{doi}"
    pdf_url = abs_url
    for link in item.get("link") or []:
        if isinstance(link, dict) and "pdf" in str(link.get("content-type", "")).lower() and link.get("URL"):
            pdf_url = str(link["URL"])
            break

    return PaperRecord(
        paper_id=doi,
        title=title,
        summary=summary,
        authors=_parse_authors(item.get("author")),
        categories=categories,
        primary_category=categories[0] if categories else "",
        published=published,
        updated=updated,
        abs_url=abs_url,
        pdf_url=pdf_url,
        comment=f"Crossref record {doi}",
    )


def _records_to_json(records: list[PaperRecord]) -> list[dict[str, Any]]:
    return [asdict(record) for record in records]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref `/works` payload thanh list PaperRecord (bo record loi, khu trung DOI)."""
    items = (payload or {}).get("message", {}).get("items", []) or []
    records: list[PaperRecord] = []
    seen: set[str] = set()
    for item in items:
        record = _parse_item(item)
        if record is None:
            continue
        key = record.paper_id.lower()
        if key in seen:
            continue
        seen.add(key)
        records.append(record)
    return records


def _request_live_payload(settings: Settings) -> dict[str, Any]:
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        "select": "DOI,title,abstract,author,subject,published,published-online,published-print,issued,created,URL,link",
    }
    headers = {"User-Agent": "K4-Day10-DataPipeline-Lab/0.1 (educational use)"}
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                CROSSREF_WORKS_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
            )
            if response.status_code in RETRYABLE_STATUS:
                retry_after = response.headers.get("Retry-After", "")
                wait = float(retry_after) if retry_after.isdigit() else 2 ** attempt
                print(f"[ingestion] Crossref tra ve {response.status_code}, thu lai sau {wait:.0f}s ({attempt}/{MAX_RETRIES})")
                last_error = RuntimeError(f"HTTP {response.status_code}")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            wait = 2 ** attempt
            print(f"[ingestion] Loi goi Crossref: {exc.__class__.__name__}, thu lai sau {wait}s ({attempt}/{MAX_RETRIES})")
            time.sleep(wait)
    raise RuntimeError(f"Crossref API unavailable after {MAX_RETRIES} retries: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Lay du lieu nguon theo 2 che do (Dual-Mode).

    - Offline (mac dinh): doc snapshot `data/raw/crossref_response.json`.
    - Live (`REFRESH_SOURCE=1`): goi Crossref API co retry 429/5xx; neu that bai
      hoac tra ve qua it record thi fallback ve snapshot. Snapshot KHONG bi ghi de
      khi live that bai (bao toan raw lineage).
    Ca 2 che do deu ghi lai `crossref_records.json` tu raw response.
    """
    paths = settings.paths
    payload: dict[str, Any] | None = None
    mode = "offline_snapshot"
    note = "REFRESH_SOURCE chua bat -> doc snapshot local."

    if settings.refresh_source:
        try:
            live_payload = _request_live_payload(settings)
            live_records = parse_crossref_payload(live_payload)
            if len(live_records) >= MIN_RECORDS_FROM_LIVE:
                payload = live_payload
                mode = "live_api"
                note = f"Crossref API tra ve {len(live_records)} record hop le."
                write_json(paths.raw_api_response, payload)  # raw preservation truoc khi bien doi
            else:
                note = f"Live API chi co {len(live_records)} record hop le -> fallback snapshot."
                mode = "fallback_snapshot"
        except Exception as exc:  # mat mang, 429 lien tuc, JSON loi...
            note = f"Live API loi ({exc}) -> fallback snapshot."
            mode = "fallback_snapshot"
        print(f"[ingestion] {note}")

    if payload is None:
        if not paths.raw_api_response.exists():
            raise FileNotFoundError(
                f"Khong tim thay snapshot {paths.raw_api_response}. Bat REFRESH_SOURCE=1 khi co mang de tai du lieu."
            )
        payload = read_json(paths.raw_api_response)

    records = parse_crossref_payload(payload)
    write_json(paths.raw_records_json, _records_to_json(records))

    LAST_FETCH_INFO.clear()
    LAST_FETCH_INFO.update(
        {
            "mode": mode,
            "note": note,
            "raw_items": len(payload.get("message", {}).get("items", []) or []),
            "parsed_records": len(records),
            "raw_response_path": str(paths.raw_api_response.relative_to(paths.project_dir)),
            "raw_records_path": str(paths.raw_records_json.relative_to(paths.project_dir)),
        }
    )
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Doc `crossref_records.json` va map thanh `PaperRecord` (bo qua field la)."""
    payload = read_json(Path(path))
    allowed = {field.name for field in fields(PaperRecord)}
    records: list[PaperRecord] = []
    for item in payload:
        data = {key: value for key, value in item.items() if key in allowed}
        data.setdefault("authors", [])
        data.setdefault("categories", [])
        for key in allowed - {"authors", "categories"}:
            data.setdefault(key, "")
        data["authors"] = list(data["authors"] or [])
        data["categories"] = list(data["categories"] or [])
        records.append(PaperRecord(**data))
    return records
