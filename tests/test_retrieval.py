from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

import retrieval.agent as agent_module
from core.config import load_settings, require_llm_credentials
from evaluation.metrics import _judge_answer, _token_f1
from retrieval.index import LocalEmbeddingIndex
from retrieval.llm import build_llm
from retrieval.qa import answer_question


@pytest.fixture
def index(clean_df, settings):
    return LocalEmbeddingIndex.build(clean_df, settings)


def test_index_build_search_lookup_load(index, clean_df, settings):
    assert index.collection_name == "papers-baseline" and len(index.documents) == 24
    results = index.search(clean_df.iloc[0]["title"], top_k=3)
    assert len(results) == 3 and results[0].paper_id == clean_df.iloc[0]["paper_id"]
    assert index.lookup(clean_df.iloc[1]["title"].upper())["paper_id"] == clean_df.iloc[1]["paper_id"]
    assert index.lookup("nothing") is None
    manifest = settings.paths.embeddings_json.read_text()
    assert str(settings.paths.project_dir) not in manifest  # khong luu duong dan tuyet doi
    reloaded = LocalEmbeddingIndex.load(settings)
    assert reloaded.persist_path == settings.paths.chroma_dir


def test_qa_extracts_answer_by_question_type(index, clean_df, settings):
    row = clean_df.iloc[2]
    title = row["title"]
    assert answer_question(f"Who authored the paper '{title}'?", settings, index).answer == row["authors_joined"]
    assert answer_question(f"When was the paper '{title}' published?", settings, index).answer == row["published"]
    cats = answer_question(f"What categories does the paper '{title}' belong to?", settings, index)
    assert cats.answer == row["categories_joined"] and cats.retrieved_doc_ids[0] == row["paper_id"]


def test_llm_router(settings, monkeypatch, project):
    assert build_llm(settings) is not None  # mock
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert build_llm(load_settings(project)).__class__.__name__ == "ChatOpenAI"
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    with pytest.raises(RuntimeError):
        require_llm_credentials(load_settings(project))
    monkeypatch.setenv("LLM_PROVIDER", "not-a-provider")
    with pytest.raises(RuntimeError):
        build_llm(load_settings(project))


def test_metrics_helpers(settings):
    assert _token_f1("a b c", "a b c") == 1.0
    assert _token_f1("a b", "") == 0.0 and _token_f1("a", "b") == 0.0
    verdict = _judge_answer(settings, "q", "same answer", "same answer")  # mock -> heuristic fallback
    assert verdict.correct and verdict.score == 5


class _ToolFake(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_agent_uses_tools(index, settings, monkeypatch):
    fake = _ToolFake(responses=[
        AIMessage(content="", tool_calls=[{"name": "semantic_search_papers", "args": {"query": "quality"}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "lookup_paper", "args": {"paper_id_or_title": "missing"}, "id": "2"}]),
        AIMessage(content="", tool_calls=[{"name": "lookup_paper", "args": {"paper_id_or_title": index.documents[0]["paper_id"]}, "id": "3"}]),
        AIMessage(content="final answer"),
    ])
    monkeypatch.setattr(agent_module, "build_llm", lambda settings, temperature=0.0: fake)
    agent = agent_module.build_agent(settings, index)
    assert agent_module.run_agent_question(agent, "Which papers discuss quality gates?") == "final answer"
