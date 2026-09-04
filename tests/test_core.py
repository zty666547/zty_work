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


def test_load_knowledge_base_merges_rules():
    from src.data.loader import load_knowledge_base

    root = Path(__file__).resolve().parent.parent
    graph = load_knowledge_base(
        root / "data/raw/curriculum_structured.json",
        root / "data/raw/curriculum_rules.json",
    )
    assert "Rule" in graph.entities
    assert "四史类课程" in graph.entity_names()
    assert "文化素质选修课" in graph.entity_names()
    assert len(graph.relations) >= 200


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
    assert "[E1]" in prompt


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


def test_builder_validates_before_clearing_graph():
    from config.settings import Settings
    from src.graph.builder import GraphBuilder

    class FakeClient:
        def __init__(self):
            self.calls = []

        def run(self, query, parameters=None):
            self.calls.append(query)
            return []

    client = FakeClient()
    builder = GraphBuilder(Settings(), client)
    entities = [
        {"name": "知识工程", "type": "Course"},
        {"name": "第4学期", "type": "Semester"},
    ]
    invalid_relations = [
        {"source": "第4学期", "target": "知识工程", "type": "OFFERED_IN"}
    ]
    try:
        builder.build(entities, invalid_relations, clear_first=True)
    except ValueError as exc:
        assert "关系方向不符合 Schema" in str(exc)
    else:
        raise AssertionError("反向关系应被拒绝")
    assert not client.calls, "校验失败时不应先清空数据库"


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
    assert intersection["intents"] == ["semester", "category"]
    assert intersection["relation_filter"] == [
        "BELONGS_TO_CATEGORY",
        "OFFERED_IN",
    ]
    assert intersection["triples"][0]["evidence_id"] == "E1"


def test_baseline_and_enhanced_retrieval_are_comparable():
    from src.data.loader import load_structured
    from src.graph.memory_client import MemoryGraphClient
    from src.rag.retriever import GraphRetriever

    root = Path(__file__).resolve().parent.parent
    retriever = GraphRetriever(
        MemoryGraphClient(load_structured(root / "data/raw/curriculum_structured.json"))
    )
    baseline = retriever.retrieve("NLP属于什么类型的课程？", strategy="baseline")
    enhanced = retriever.retrieve("NLP属于什么类型的课程？", strategy="enhanced")
    assert baseline["entities"] == []
    assert enhanced["entities"] == ["自然语言处理"]
    assert all(t["rel"] == "BELONGS_TO_CATEGORY" for t in enhanced["triples"])


def test_graph_rag_chain_injects_source_and_evidence():
    from config.settings import Settings
    from src.data.loader import load_structured
    from src.graph.memory_client import MemoryGraphClient
    from src.rag.chain import GraphRAGChain

    class FakeLLM:
        def __init__(self):
            self.user_prompt = ""

        def chat(self, system_prompt, user_prompt, temperature=0.2):
            self.user_prompt = user_prompt
            return "知识工程为3.5学分。"

    root = Path(__file__).resolve().parent.parent
    graph = load_structured(root / "data/raw/curriculum_structured.json")
    llm = FakeLLM()
    result = GraphRAGChain(Settings(), MemoryGraphClient(graph), llm).answer(
        "知识工程是多少学分？"
    )
    assert result["answer"].endswith("[E1]")
    assert "2024级人工智能专业培养方案" in llm.user_prompt
    assert "[E1]" in llm.user_prompt
    assert result["answer_mode"] == "llm"


def test_offline_answer_is_scoped_and_readable():
    from src.rag.offline_answerer import build_offline_answer

    assert "2024 级" in build_offline_answer("未知问题", [])
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
    assert "只收录 2024 级" in refusal
    assert "无法可靠回答2025级" in refusal

    from src.rag.scope import scope_refusal

    assert scope_refusal("2024级知识工程是多少学分？") is None
    assert "无法可靠回答2023级" in scope_refusal("2023级知识工程是多少学分？")


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


def test_rule_retrieval_supports_explanatory_questions():
    from src.data.loader import load_knowledge_base
    from src.graph.memory_client import MemoryGraphClient
    from src.rag.retriever import GraphRetriever

    root = Path(__file__).resolve().parent.parent
    graph = load_knowledge_base(
        root / "data/raw/curriculum_structured.json",
        root / "data/raw/curriculum_rules.json",
    )
    retriever = GraphRetriever(MemoryGraphClient(graph))

    concept = retriever.retrieve("选修课和通识课是什么关系？")
    assert concept["hop"] == 2
    assert "CATEGORY_IN_DOMAIN" in concept["context_text"]
    assert "HAS_NATURE" in concept["context_text"]

    four_histories = retriever.retrieve("四史类课程是每一门都必修吗？")
    assert "minimum_courses=1" in four_histories["context_text"]
    assert "习近平新时代中国特色社会主义思想系列课程" in four_histories["context_text"]
    assert "verification_status=校内资料已整理，待原始通知复核" in four_histories["context_text"]


def test_offline_rule_answer_distinguishes_scope_and_evidence_status():
    from src.data.loader import load_knowledge_base
    from src.graph.memory_client import MemoryGraphClient
    from src.rag.offline_answerer import build_offline_answer
    from src.rag.retriever import GraphRetriever

    root = Path(__file__).resolve().parent.parent
    graph = load_knowledge_base(
        root / "data/raw/curriculum_structured.json",
        root / "data/raw/curriculum_rules.json",
    )
    retriever = GraphRetriever(MemoryGraphClient(graph))

    result = retriever.retrieve("四史类课程是每一门都必修吗？")
    answer = build_offline_answer("四史类课程是每一门都必修吗？", result["triples"])
    assert "至少选修1门" in answer
    assert "待原始通知复核" in answer

    result = retriever.retrieve("选修课和通识课是什么关系？")
    answer = build_offline_answer("选修课和通识课是什么关系？", result["triples"])
    assert "不是同一个分类维度" in answer

    result = retriever.retrieve("专业核心与专业选修有什么区别？")
    answer = build_offline_answer("专业核心与专业选修有什么区别？", result["triples"])
    assert "两者都属于专业教育" in answer
    assert "专业核心课是培养方案指定的必修模块，共21学分" in answer
    assert "专业选修课允许从课程清单中选择，但累计须完成16学分" in answer


def test_rule_overview_rows():
    from app import build_rule_rows
    from src.data.loader import load_knowledge_base
    from src.graph.memory_client import MemoryGraphClient

    root = Path(__file__).resolve().parent.parent
    graph = load_knowledge_base(
        root / "data/raw/curriculum_structured.json",
        root / "data/raw/curriculum_rules.json",
    )
    rows = build_rule_rows(MemoryGraphClient(graph))
    assert len(rows) == 5
    professional_elective = next(
        row for row in rows if row["规则"] == "2024级专业选修学分要求"
    )
    assert professional_elective["依据来源"] == "2024级人工智能专业培养方案原文"
    assert professional_elective["来源等级"] == "A-官方培养方案"
    assert professional_elective["来源链接"].startswith("https://")
