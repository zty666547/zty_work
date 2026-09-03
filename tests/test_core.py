"""无外部依赖的单元测试（不连 Neo4j、不调 LLM）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_load_structured():
    from src.data.loader import load_structured

    path = Path(__file__).resolve().parent.parent / "data/raw/curriculum_structured.json"
    graph = load_structured(path)
    assert "Course" in graph.entities
    assert graph.relations, "关系列表不应为空"
    assert "知识工程" in graph.entity_names()
    assert "第4学期" in graph.entity_names()
    assert sum(map(len, graph.entities.values())) >= 60


def test_load_documents():
    from src.data.loader import load_documents

    path = Path(__file__).resolve().parent.parent / "data/raw/curriculum_docs.txt"
    docs = load_documents(path)
    assert len(docs) >= 5, f"应至少有 5 条文档，实际 {len(docs)}"


def test_context_text_formatting():
    from src.rag.prompts import build_context_text

    triples = [
        {
            "source": "知识工程",
            "source_props": {"credits": 3.5, "name": "知识工程"},
            "rel": "OFFERED_IN",
            "rel_props": {"term": "常规学期"},
            "target": "第4学期",
            "target_props": {"order": 4},
        }
    ]
    text = build_context_text(triples)
    assert "知识工程" in text
    assert "credits=3.5" in text
    assert "OFFERED_IN" in text
    assert "第4学期" in text


def test_prompt_builder():
    from src.rag.prompts import build_rag_user_prompt

    prompt = build_rag_user_prompt("问题", "上下文")
    assert "上下文" in prompt and "问题" in prompt


def test_entity_linking_supports_aliases():
    from src.rag.retriever import GraphRetriever

    class FakeClient:
        def run(self, query, parameters=None):
            assert "aliases" in query
            return [
                {"name": "第4学期", "aliases": ["第四学期", "大二下"]},
                {"name": "机器学习与深度学习", "aliases": ["机器学习", "深度学习"]},
            ]

    retriever = GraphRetriever(FakeClient())
    assert retriever.link_entities("大二下有哪些机器学习相关课程？") == [
        "机器学习与深度学习",
        "第4学期",
    ]


def test_relation_properties_are_written():
    from config.settings import Settings
    from src.graph.builder import GraphBuilder

    class FakeClient:
        def __init__(self):
            self.calls = []

        def run(self, query, parameters=None):
            self.calls.append((query, parameters or {}))
            return []

    client = FakeClient()
    builder = GraphBuilder(Settings(), client)
    builder._merge_relation(
        "知识工程综合实践",
        "第4学期",
        "OFFERED_IN",
        {"term": "暑期学期"},
        None,
        None,
    )
    query, parameters = client.calls[-1]
    assert "r.term = $rel_prop_term" in query
    assert parameters["rel_prop_term"] == "暑期学期"


def test_memory_graph_retrieves_course_properties():
    from src.data.loader import load_structured
    from src.graph.memory_client import MemoryGraphClient
    from src.rag.retriever import GraphRetriever

    root = Path(__file__).resolve().parent.parent
    graph = load_structured(root / "data/raw/curriculum_structured.json")
    retriever = GraphRetriever(MemoryGraphClient(graph))
    result = retriever.retrieve("知识工程是多少学分，第四学期修读吗？")

    assert "知识工程" in result["entities"]
    assert "第4学期" in result["entities"]
    assert "credits=3.5" in result["context_text"]
    assert "OFFERED_IN" in result["context_text"]

    intersection = retriever.retrieve("第六学期有哪些专业选修课？")
    assert "知识图谱" in intersection["context_text"]
    assert "信息检索与智能问答" in intersection["context_text"]
    assert "并行计算" not in intersection["context_text"]


def test_offline_answer_is_scoped_and_readable():
    from src.rag.offline_answerer import build_offline_answer

    assert "2023 级" in build_offline_answer("未知问题", [])
    answer = build_offline_answer(
        "知识工程是多少学分？",
        [
            {
                "source": "知识工程",
                "source_props": {"entity_type": "Course", "credits": 3.5},
                "rel": "OFFERED_IN",
                "target": "第4学期",
                "target_props": {},
            }
        ],
    )
    assert "3.5 学分" in answer
    assert "第4学期" in answer
    refusal = build_offline_answer("2025级知识工程是多少学分？", [])
    assert "只收录 2023 级" in refusal
    assert "无法可靠回答2025级" in refusal


def test_course_overview_rows():
    from app import build_course_rows
    from src.data.loader import load_structured
    from src.graph.memory_client import MemoryGraphClient

    root = Path(__file__).resolve().parent.parent
    graph = load_structured(root / "data/raw/curriculum_structured.json")
    rows = build_course_rows(MemoryGraphClient(graph))
    assert len(rows) == 39
    knowledge_engineering = next(row for row in rows if row["课程"] == "知识工程")
    assert knowledge_engineering["建议学期"] == "第4学期"
    assert knowledge_engineering["课程类别"] == "专业核心课"
