"""DebugPath Streamlit 交互式主动诊断页面。"""
from __future__ import annotations

import streamlit as st

from config.settings import settings
from src.diagnosis.engine import UnknownIssueError
from src.diagnosis.generator import render_offline, render_with_llm
from src.diagnosis.models import DiagnosisState
from src.diagnosis.service import DiagnosisService
from src.extraction.llm_client import LLMClient

EXAMPLES = [
    "ModuleNotFoundError: No module named 'pandas'",
    "torch.cuda.is_available() 返回 False，检测不到GPU",
    "Neo4j Connection refused，无法连接 localhost:7687",
    "API 请求返回 401 Unauthorized",
]


@st.cache_resource
def load_service() -> DiagnosisService:
    return DiagnosisService(settings)


def _graph_dot(snapshot: dict) -> str:
    issue = snapshot["state"]["issue_name"]
    lines = ["digraph G {", 'rankdir="LR";', 'node [shape="box", style="rounded,filled", fontname="Arial"];']
    lines.append(f'issue [label="{issue}", fillcolor="#dbeafe"];')
    for index, candidate in enumerate(snapshot["candidates"]):
        color = "#fecaca" if index == 0 else "#fef3c7"
        label = f"{candidate['name']}\\n{candidate['probability']:.1%}"
        lines.append(f'c{index} [label="{label}", fillcolor="{color}"];')
        lines.append(f'issue -> c{index};')
    if snapshot.get("question"):
        question_text = snapshot["question"]["text"].replace('"', "'")
        lines.append(f'q [label="下一问\\n{question_text}", fillcolor="#dcfce7"];')
        lines.append("issue -> q [style=dashed];")
    lines.append("}")
    return "\n".join(lines)


def _render_candidates(snapshot: dict) -> None:
    st.subheader("候选原因正在收敛")
    rows = [
        {"候选原因": item["name"], "当前概率": round(item["probability"] * 100, 1), "说明": item["description"]}
        for item in snapshot["candidates"]
    ]
    st.dataframe(rows, width="stretch", hide_index=True)
    st.bar_chart({row["候选原因"]: row["当前概率"] for row in rows}, horizontal=True)


def main() -> None:
    st.set_page_config(page_title="DebugPath", page_icon="🧭", layout="wide")
    st.title("🧭 DebugPath")
    st.caption("基于版本感知因果知识图谱与主动询问的 AI 开发环境故障诊断")
    service = load_service()

    with st.sidebar:
        st.header("演示设置")
        platform_label = st.selectbox("目标环境", ["macOS", "Windows", "Linux"])
        platform = {"macOS": "macos", "Windows": "windows", "Linux": "linux"}[platform_label]
        modes = ["离线稳定模式"]
        if settings.deepseek_api_key:
            modes.append("DeepSeek解释模式")
        mode = st.radio("答案生成", modes)
        st.info("系统只生成检查建议，不会自动执行命令。")
        if st.button("重新开始", width="stretch"):
            st.session_state.pop("diagnosis", None)
            st.rerun()

    diagnose_tab, graph_tab, method_tab = st.tabs(["主动诊断", "因果图谱", "方法说明"])
    with diagnose_tab:
        report = st.text_area(
            "粘贴报错信息或描述现象", placeholder=EXAMPLES[0], height=120,
            disabled="diagnosis" in st.session_state,
        )
        if "diagnosis" not in st.session_state:
            st.caption("可直接尝试：" + " ｜ ".join(EXAMPLES))
            if st.button("开始诊断", type="primary"):
                try:
                    st.session_state.diagnosis = service.start(report)
                    st.rerun()
                except (ValueError, UnknownIssueError) as exc:
                    st.warning(str(exc))
        else:
            previous = st.session_state.diagnosis
            state = previous["state"]
            snapshot = service.snapshot(DiagnosisState.from_dict(state), platform=platform)
            st.session_state.diagnosis = snapshot
            state = snapshot["state"]
            st.success(f"已识别场景：{state['issue_name']}")
            c1, c2, c3 = st.columns(3)
            c1.metric("候选原因", len(snapshot["candidates"]))
            c2.metric("已追问", len(state["asked_questions"]))
            c3.metric("最高概率", f"{snapshot['candidates'][0]['probability']:.1%}")
            _render_candidates(snapshot)
            question = snapshot.get("question")
            if state["status"] == "questioning" and question:
                st.subheader("系统选择的下一问")
                st.write(question["text"])
                st.caption(question["reason"])
                answer_label = st.radio(
                    "请选择观察结果",
                    [question["yes_label"], question["no_label"], "暂时无法确认"],
                    key=f"answer-{question['name']}",
                )
                answer = {question["yes_label"]: "yes", question["no_label"]: "no", "暂时无法确认": "unknown"}[answer_label]
                left, right = st.columns(2)
                if left.button("提交观察结果", type="primary", width="stretch"):
                    st.session_state.diagnosis = service.answer(state, question["name"], answer)
                    st.rerun()
                if right.button("结束追问，查看当前方案", width="stretch"):
                    st.session_state.diagnosis = service.complete(state)
                    st.rerun()
            else:
                st.subheader("已验证的排查方案")
                if snapshot["plan_errors"]:
                    st.error("方案验证未通过：" + "；".join(snapshot["plan_errors"]))
                elif mode == "DeepSeek解释模式":
                    try:
                        st.markdown(render_with_llm(snapshot, LLMClient(settings)))
                    except Exception as exc:  # noqa: BLE001
                        st.warning(f"大模型暂不可用，已回退到离线答案：{exc}")
                        st.markdown(render_offline(snapshot))
                else:
                    st.markdown(render_offline(snapshot))

    with graph_tab:
        st.subheader("当前诊断子图")
        if "diagnosis" in st.session_state:
            st.graphviz_chart(_graph_dot(st.session_state.diagnosis), width="stretch")
        else:
            st.info("开始一次诊断后，这里会显示问题、候选原因和下一条主动询问。")
        node_count = sum(len(items) for items in service.graph.entities.values())
        st.caption(f"知识库规模：{node_count} 个节点，{len(service.graph.relations)} 条受控关系。")

    with method_tab:
        st.subheader("为什么不是普通问答")
        st.markdown(
            "1. **版本化因果图谱**：原因、平台、版本、检查、修复和官方来源分别建模。\n"
            "2. **主动询问**：对每个未问问题计算期望信息增益，并扣除操作成本与风险。\n"
            "3. **生成前验证**：修复动作必须具备前置检查、风险等级和证据来源；高风险动作自动阻止。"
        )
        st.code("Utility(q) = ExpectedInformationGain(q) - CheckCost(q) - RiskCost(q)", language=None)
        st.caption("候选概率用于决定排查顺序，不替代真实运行结果或专业判断。")


if __name__ == "__main__":
    main()
