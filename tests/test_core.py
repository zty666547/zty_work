"""无外部依赖的单元测试（不连 Neo4j、不调 LLM）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_load_structured():
    from src.data.loader import load_structured

    path = Path(__file__).resolve().parent.parent / "data/raw/movies_structured.json"
    graph = load_structured(path)
    assert "Movie" in graph.entities
    assert graph.relations, "关系列表不应为空"
    assert "Christopher Nolan" in graph.entity_names()


def test_load_documents():
    from src.data.loader import load_documents

    path = Path(__file__).resolve().parent.parent / "data/raw/movie_docs.txt"
    docs = load_documents(path)
    assert len(docs) >= 5, f"应至少有 5 条文档，实际 {len(docs)}"


def test_context_text_formatting():
    from src.rag.prompts import build_context_text

    triples = [
        {"source": "Christopher Nolan", "rel": "DIRECTED", "target": "Inception"}
    ]
    text = build_context_text(triples)
    assert "Christopher Nolan" in text
    assert "DIRECTED" in text
    assert "Inception" in text


def test_prompt_builder():
    from src.rag.prompts import build_rag_user_prompt

    prompt = build_rag_user_prompt("问题", "上下文")
    assert "上下文" in prompt and "问题" in prompt
