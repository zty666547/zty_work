"""人工智能专业培养方案智能问答系统的学生端网页。"""
from __future__ import annotations

import streamlit as st

from config.settings import settings
from src.data.loader import load_structured
from src.graph.memory_client import MemoryGraphClient
from src.rag.offline_answerer import build_offline_answer
from src.rag.chain import GraphRAGChain
from src.rag.retriever import GraphRetriever
from src.rag.scope import SOURCE_NAME
from src.extraction.llm_client import LLMClient


SAMPLE_QUESTIONS = [
    "知识工程是多少学分，建议在哪个学期修读？",
    "第四学期有哪些专业核心课？",
    "第六学期有哪些专业选修课？",
    "人工智能专业有哪些毕业要求？",
]


@st.cache_resource
def load_services_v2() -> tuple[MemoryGraphClient, GraphRetriever]:
    graph = load_structured(settings.raw_dir / settings.structured_filename)
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


def main() -> None:
    st.set_page_config(page_title="AI 培养方案问答", page_icon="🎓", layout="wide")
    st.title("🎓 人工智能专业培养方案智能问答")
    st.caption("面向实际应用的 Graph RAG 高完成度原型 · 当前数据版本：2023级")
    st.info(
        "当前系统只收录 2023 级培养方案。其他年级的课程安排可能不同，"
        "请勿将本系统答案直接视为其他年级的正式选课依据。"
    )

    with st.sidebar:
        st.subheader("可以这样问")
        for item in SAMPLE_QUESTIONS:
            st.markdown(f"- {item}")
        st.divider()
        st.markdown(f"**依据来源**  \n{SOURCE_NAME}")
        st.markdown("**回答方式**  \n实体链接 → 图谱检索 → 证据组织")
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
    qa_tab, path_tab, coverage_tab = st.tabs(["智能问答", "培养路径", "数据范围"])

    with qa_tab:
        question = st.chat_input("请输入关于课程、学分、学期或毕业要求的问题")
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
                st.caption(f"适用范围：2023级人工智能专业｜依据：{SOURCE_NAME}")
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
            "- 已覆盖：代表性课程、学分、建议学期、课程类别、开课单位、毕业要求。\n"
            "- 尚未覆盖：其他年级培养方案、实时开课状态、个人成绩、官方先修关系。\n"
            "- 后续方向：导入多版本培养方案，经人工审核后接入实际教学服务场景。"
        )


if __name__ == "__main__":
    main()
