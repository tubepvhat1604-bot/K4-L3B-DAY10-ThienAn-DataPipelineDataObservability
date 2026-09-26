"""Fixtures dung chung cho bo test (Bonus B3).

- Embedding MiniLM duoc thay bang embedder hashing tat dinh -> test nhanh, khong can tai model/GPU.
- Moi test chay tren 1 ban sao project trong thu muc tam -> KHONG ghi de artifacts that trong `data/`.
- LLM_PROVIDER=mock -> khong goi API, khong ton tien.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class FakeSentenceTransformer:
    """Bag-of-words hashing 384 chieu (cung so chieu voi all-MiniLM-L6-v2)."""

    def __init__(self, name: str = "fake"):
        self.name = name

    def encode(self, texts, normalize_embeddings=True):
        vectors = []
        for text in texts:
            vector = np.zeros(384)
            for token in re.findall(r"[a-z0-9]+", str(text).lower()):
                vector[int(hashlib.md5(token.encode()).hexdigest(), 16) % 384] += 1.0
            norm = np.linalg.norm(vector)
            vectors.append(vector / norm if norm else vector)
        return np.array(vectors)


try:  # May khong cai sentence-transformers (vd CI nhe) van chay duoc test
    import sentence_transformers  # noqa: F401
except ImportError:  # pragma: no cover
    stub = types.ModuleType("sentence_transformers")
    stub.SentenceTransformer = FakeSentenceTransformer
    sys.modules["sentence_transformers"] = stub

import retrieval.embeddings as embeddings_module  # noqa: E402
from core.config import load_settings  # noqa: E402


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    monkeypatch.setattr(embeddings_module, "_load_model", lambda name: FakeSentenceTransformer(name))


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Ban sao project toi thieu (chi raw snapshot) trong thu muc tam."""
    for key in ["REFRESH_SOURCE", "REFRESH_TEST_SET", "RUN_RAGAS", "OPENAI_API_KEY", "GOOGLE_API_KEY"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MODEL", "mock-model")
    root = tmp_path / "proj"
    (root / "data").mkdir(parents=True)
    shutil.copytree(ROOT / "data" / "raw", root / "data" / "raw")
    return root


@pytest.fixture
def settings(project):
    return load_settings(project)


@pytest.fixture
def records(settings):
    from ingestion.crossref import fetch_source_records

    return fetch_source_records(settings)


@pytest.fixture
def clean_df(records) -> pd.DataFrame:
    from datetime import datetime, timezone

    from ingestion.cleaning import build_clean_dataframe

    return build_clean_dataframe(records, datetime(2026, 9, 25, tzinfo=timezone.utc))


@pytest.fixture
def patch_settings(monkeypatch, project):
    """Buoc cac pipeline dung project tam thay vi repo that."""
    import pipelines.corruption_flow as corruption_flow
    import pipelines.phase1 as phase1

    monkeypatch.setattr(phase1, "load_settings", lambda: load_settings(project))
    monkeypatch.setattr(corruption_flow, "load_settings", lambda: load_settings(project))
    return project
