"""人工智能专业培养方案智能问答系统的学生端网页。"""
from __future__ import annotations

import streamlit as st

from config.settings import settings
from src.data.loader import load_knowledge_base
from src.graph.memory_client import MemoryGraphClient
from src.rag.offline_answerer import build_offline_answer
from src.rag.chain import GraphRAGChain
from src.rag.retriever import GraphRetriever
from src.rag.scope import SOURCE_NAME
from src.extraction.llm_client import LLMClient


SAMPLE_QUESTIONS = [
    "知识工程是多少学分，建议在哪个学期修读？",
    "选修课和通识课是什么关系？",
    "专业核心与专业选修有什么区别？",
    "建议修读学期是否具有强制性？",
    "四史类课程是每一门都必修吗？",
    "专业选修需要修满多少学分？",
]


@st.cache_resource
def load_services_v2() -> tuple[MemoryGraphClient, GraphRetriever]:
    graph = load_knowledge_base(
        settings.raw_dir / settings.structured_filename,
        settings.raw_dir / settings.rules_filename,
    )
    client = MemoryGraphClient(graph)
    return client, GraphRetriever(client)


def build_course_rows(client: MemoryGraphClient) -> list[dict]:
    """把课程邻接关系整理为适合学生浏览的表格。"""
    rows: dict[str, dict] = {}
    for name, props in client.nodes.items():
        if props.get("entity_type") == "Course":
            rows[name] = {
                "课程": name,
                "课程代码": props.get("code", ""),
                "学分": props.get("credits", ""),
                "必修": "是" if props.get("required") else "否",
                "建议学期": "",
                "课程类别": "",
            }
    for relation in client.relations:
        course = rows.get(relation["source"])
        if not course:
            continue
        if relation["type"] == "OFFERED_IN":
            course["建议学期"] = relation["target"]
        elif relation["type"] == "BELONGS_TO_CATEGORY":
            course["课程类别"] = relation["target"]
    return sorted(
        rows.values(),
        key=lambda row: (
            int(str(row["建议学期"]).replace("第", "").replace("学期", "") or 99),
            row["课程"],
        ),
    )


def build_dot(triples: list[dict]) -> str:
    """把少量检索三元组转为 Graphviz DOT。"""
    def quote(value: str) -> str:
        return value.replace('"', '\\"')

    lines = ["digraph G {", 'rankdir="LR";', 'node [shape="box", style="rounded,filled", fillcolor="#EEF4FF"];']
    for triple in triples[:16]:
        source = quote(triple["source"])
        target = quote(triple["target"])
        relation = quote(triple["rel"])
        lines.append(f'"{source}" -> "{target}" [label="{relation}"];')
    lines.append("}")
    return "\n".join(lines)


def build_rule_rows(client: MemoryGraphClient) -> list[dict]:
    """整理规则节点，便于用户直接查看适用范围和核验状态。"""
    sources_by_rule: dict[str, list[dict]] = {}
    for relation in client.relations:
        if relation["type"] != "SUPPORTED_BY":
            continue
        source_props = client.nodes.get(relation["target"], {})
        sources_by_rule.setdefault(relation["source"], []).append(
            {
                "name": relation["target"],
                "url": source_props.get("url", ""),
                "tier": source_props.get("source_tier", ""),
            }
        )

    rows = []
    for name, props in client.nodes.items():
        if props.get("entity_type") != "Rule":
            continue
        sources = sources_by_rule.get(name, [])
        rows.append(
            {
                "规则": name,
                "适用范围": props.get("scope", ""),
                "规则内容": props.get("statement", ""),
                "证据状态": props.get("verification_status", ""),
                "依据来源": "；".join(item["name"] for item in sources),
                "来源等级": "；".join(item["tier"] for item in sources),
                "来源链接": "；".join(item["url"] for item in sources),
            }
        )
    return sorted(rows, key=lambda row: row["规则"])


def main() -> None:
    st.set_page_config(page_title="AI 培养方案问答", page_icon="🎓", layout="wide")
    st.title("🎓 人工智能专业培养方案智能问答")
    st.caption("课程事实 + 培养规则 + 可追溯依据 · 当前主数据版本：2024级")
    st.info(
        "当前系统只收录 2024 级培养方案。其他年级的课程安排可能不同，"
        "请勿将本系统答案直接视为其他年级的正式选课依据。"
    )
    st.caption("官方2024版页面已确认；课程明细按两届无变动结论迁移，待PDF逐项复核。")

    with st.sidebar:
        st.subheader("可以这样问")
        for item in SAMPLE_QUESTIONS:
            st.markdown(f"- {item}")
        st.divider()
        st.markdown(f"**主要依据**  \n{SOURCE_NAME}")
        st.markdown("**回答方式**  \n问题识别 → 图谱检索 → 规则与来源 → 证据回答")
        st.divider()
        answer_options = ["离线证据回答"]
        if settings.deepseek_api_key:
            answer_options.append("DeepSeek Graph RAG")
        default_answer_index = (
            1
            if settings.answer_mode == "llm" and len(answer_options) > 1
            else 0
        )
        answer_mode = st.radio(
            "答案生成",
            answer_options,
            index=default_answer_index,
        )
        if not settings.deepseek_api_key:
            st.caption("填写 .env 中的 DEEPSEEK_API_KEY 后可启用大模型回答。")
        strategy_label = st.selectbox(
            "检索策略",
            ["增强检索", "基础检索"],
            help="基础检索用于最终答辩的对比实验。",
        )
        strategy = "enhanced" if strategy_label == "增强检索" else "baseline"

    client, retriever = load_services_v2()
    qa_tab, rules_tab, path_tab, coverage_tab = st.tabs(
        ["智能问答", "培养规则", "培养路径", "数据范围"]
    )

    with qa_tab:
        question = st.chat_input("请输入关于课程、分类、学分或修读规则的问题")
        if not question:
            st.markdown("#### 示例问题")
            cols = st.columns(2)
            for index, item in enumerate(SAMPLE_QUESTIONS):
                cols[index % 2].code(item, language=None)
        else:
            with st.chat_message("user"):
                st.write(question)
            if answer_mode == "DeepSeek Graph RAG":
                try:
                    result = GraphRAGChain(
                        settings,
                        client,
                        LLMClient(settings),
                    ).answer(question, hop=1, strategy=strategy)
                    answer = result["answer"]
                except Exception as exc:  # noqa: BLE001
                    st.warning(f"DeepSeek 调用失败，已回退到离线证据回答：{exc}")
                    result = retriever.retrieve(question, hop=1, strategy=strategy)
                    answer = build_offline_answer(question, result["triples"])
            else:
                result = retriever.retrieve(question, hop=1, strategy=strategy)
                answer = build_offline_answer(question, result["triples"])
            with st.chat_message("assistant"):
                st.write(answer)
                st.caption(
                    "主要适用范围：2024级人工智能专业｜"
                    "具体规则以证据中的适用范围与核验状态为准"
                )
                st.caption(
                    "检索说明："
                    f"策略={result.get('strategy', strategy)}；"
                    f"意图={','.join(result.get('intents', [])) or '通用查询'}；"
                    f"关系过滤={','.join(result.get('relation_filter', [])) or '无'}"
                )
                with st.expander("查看课程关系图"):
                    if result["triples"]:
                        st.graphviz_chart(build_dot(result["triples"]), width="stretch")
                    else:
                        st.write("没有可展示的关系。")
                with st.expander("查看原始图谱证据"):
                    if result["entities"]:
                        st.write("命中实体：", "、".join(result["entities"]))
                    st.code(result["context_text"], language=None)

    with rules_tab:
        st.subheader("已收录的培养与选课规则")
        st.caption(
            "规则与课程事实分开建模；每条规则保留适用范围和证据状态，"
            "学期性通知不会被当作永久规则。"
        )
        st.dataframe(build_rule_rows(client), width="stretch", hide_index=True)

    with path_tab:
        st.subheader("按培养方案浏览课程路径")
        st.caption("这里展示的是建议修读学期，不代表课程先修关系或个性化选课结论。")
        rows = build_course_rows(client)
        semesters = ["全部", *[f"第{i}学期" for i in range(1, 9)]]
        semester = st.selectbox("学期", semesters)
        categories = ["全部", *sorted({row["课程类别"] for row in rows if row["课程类别"]})]
        category = st.selectbox("课程类别", categories)
        filtered = [
            row
            for row in rows
            if (semester == "全部" or row["建议学期"] == semester)
            and (category == "全部" or row["课程类别"] == category)
        ]
        st.dataframe(filtered, width="stretch", hide_index=True)
        st.caption(f"当前展示 {len(filtered)} 门课程；知识库共收录 {len(rows)} 门代表性课程。")

    with coverage_tab:
        st.subheader("当前原型的数据边界")
        st.markdown(
            "- 已覆盖：代表性课程、课程分类、学分、建议学期、毕业要求和首批培养规则。\n"
            "- 规则能力：区分通识/专业领域与必修/选修性质，记录四史课程组、学分要求和来源状态。\n"
            "- 尚未覆盖：实时开课状态、个人成绩、完整课程目录和经官方原文复核的全部先修关系。\n"
            "- 使用原则：来源标记为“待原始通知复核”的结论，应以教务系统或官方原文为准。"
        )


if __name__ == "__main__":
    main()
