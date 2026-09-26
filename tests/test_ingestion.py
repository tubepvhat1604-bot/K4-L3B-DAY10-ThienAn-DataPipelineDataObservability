from __future__ import annotations

import json

import pytest
import requests

import ingestion.crossref as crossref
from ingestion.crossref import PaperRecord, clean_text, fetch_source_records, load_raw_records, parse_crossref_payload


def _item(doi="10.1/A", **overrides):
    item = {
        "DOI": doi,
        "title": ["  Hello <i>World</i>  Paper "],
        "abstract": "<jats:p>Some &amp; long abstract text, enough characters here.</jats:p>",
        "author": [{"given": "An", "family": "Le"}, {"name": "Org X"}],
        "subject": ["AI", "IR"],
        "published": {"date-parts": [[2026, 5]]},
        "URL": f"https://doi.org/{doi}",
    }
    item.update(overrides)
    return item


def test_clean_text_strips_jats_and_entities():
    assert clean_text("<jats:p>A &amp;   B</jats:p>") == "A & B"
    assert clean_text(None) == ""
    assert clean_text(["a", "b"]) == "a b"


def test_parse_payload_normalizes_and_filters():
    payload = {"message": {"items": [
        _item(),
        _item(doi="10.1/a"),  # trung DOI khac hoa thuong
        _item(doi="10.1/B", title=[]),  # thieu title
        _item(doi="10.1/C", abstract=None),  # thieu abstract
        _item(doi="10.1/D", published=None, created={"date-time": "2026-01-02T00:00:00Z"},
              link=[{"content-type": "application/pdf", "URL": "https://x/pdf"}], subject=None),
    ]}}
    records = parse_crossref_payload(payload)
    assert [r.paper_id for r in records] == ["10.1/A", "10.1/D"]
    first = records[0]
    assert first.title == "Hello World Paper"
    assert first.summary.startswith("Some & long")
    assert first.authors == ["An Le", "Org X"]
    assert first.published == "2026-05-01"
    assert records[1].pdf_url == "https://x/pdf"
    assert records[1].published == "2026-01-02"
    assert records[1].categories == [] and records[1].primary_category == ""


def test_offline_snapshot_returns_24_and_preserves_raw(settings):
    before = settings.paths.raw_api_response.read_text(encoding="utf-8")
    records = fetch_source_records(settings)
    assert len(records) == 24
    assert crossref.LAST_FETCH_INFO["mode"] == "offline_snapshot"
    assert settings.paths.raw_api_response.read_text(encoding="utf-8") == before
    assert len(json.loads(settings.paths.raw_records_json.read_text())) == 24


def test_load_raw_records_roundtrip(records, settings):
    loaded = load_raw_records(settings.paths.raw_records_json)
    assert loaded == records
    assert all(isinstance(r, PaperRecord) for r in loaded)


class _Resp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code, self._payload, self.headers = status, payload, headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def _live_settings(project, monkeypatch):
    from core.config import load_settings

    monkeypatch.setenv("REFRESH_SOURCE", "1")
    monkeypatch.setattr(crossref.time, "sleep", lambda s: None)
    return load_settings(project)


def test_live_api_retries_429_then_saves_raw(project, monkeypatch):
    settings = _live_settings(project, monkeypatch)
    payload = {"message": {"items": [_item(doi=f"10.9/{i}") for i in range(6)]}}
    responses = iter([_Resp(429, headers={"Retry-After": "1"}), _Resp(200, payload)])
    monkeypatch.setattr(crossref.requests, "get", lambda *a, **k: next(responses))
    records = fetch_source_records(settings)
    assert len(records) == 6
    assert crossref.LAST_FETCH_INFO["mode"] == "live_api"
    assert json.loads(settings.paths.raw_api_response.read_text()) == payload


def test_live_api_failure_falls_back_without_overwriting(project, monkeypatch):
    settings = _live_settings(project, monkeypatch)
    before = settings.paths.raw_api_response.read_text(encoding="utf-8")

    def boom(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(crossref.requests, "get", boom)
    records = fetch_source_records(settings)
    assert len(records) == 24
    assert crossref.LAST_FETCH_INFO["mode"] == "fallback_snapshot"
    assert settings.paths.raw_api_response.read_text(encoding="utf-8") == before


def test_live_api_too_few_records_falls_back(project, monkeypatch):
    settings = _live_settings(project, monkeypatch)
    monkeypatch.setattr(crossref.requests, "get", lambda *a, **k: _Resp(200, {"message": {"items": [_item()]}}))
    assert len(fetch_source_records(settings)) == 24
    assert crossref.LAST_FETCH_INFO["mode"] == "fallback_snapshot"


def test_missing_snapshot_raises(settings):
    settings.paths.raw_api_response.unlink()
    with pytest.raises(FileNotFoundError):
        fetch_source_records(settings)
