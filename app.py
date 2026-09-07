"""DebugPath Streamlit 交互式主动诊断页面。"""
from __future__ import annotations

import streamlit as st
import json
import pandas as pd

from config.settings import settings
from src.diagnosis.engine import UnknownIssueError
from src.diagnosis.generator import render_offline, render_with_llm
from src.diagnosis.models import DiagnosisState
from src.diagnosis.service import DiagnosisService
from src.diagnosis.trajectory import stage_dot
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


def _render_candidates(snapshot: dict) -> None:
    st.subheader("当前候选原因")
    rows = [
        {"候选原因": item["name"], "当前概率": round(item["probability"] * 100, 1), "说明": item["description"]}
        for item in snapshot["candidates"]
    ]
    st.dataframe(rows, width="stretch", hide_index=True)
    st.bar_chart({row["候选原因"]: row["当前概率"] for row in rows}, horizontal=True)


def _render_live_graph(snapshot: dict, service: DiagnosisService) -> None:
    """在问答旁展示最新阶段，而不是等诊断结束后再回放。"""
    stages = snapshot["state"].get("trajectory", [])
    if not stages:
        st.info("开始诊断后，这里会实时显示候选子图。")
        return
    stage = stages[-1]
    previous = stages[-2] if len(stages) > 1 else stage
    top = stage["candidates"][0]
    st.subheader("实时候选子图")
    st.caption(
        f"第 {stage['round']} 轮 · 当前首位：{top['name']}（{top['probability']:.1%}）"
    )
    st.graphviz_chart(stage_dot(stage, service.graph, previous), width="stretch")
    st.caption(
        "蓝：故障；紫：当前问题；青：用户观察；黄：候选原因；"
        "灰：本轮概率下降；绿：当前首位。节点越大，当前概率越高。"
    )


def _render_trajectory(snapshot: dict, service: DiagnosisService) -> None:
    stages = snapshot["state"].get("trajectory", [])
    if not stages:
        st.info("请重新开始一次诊断以记录完整轨迹。")
        return
    st.subheader("动态诊断轨迹")
    index = st.select_slider(
        "回看阶段", options=list(range(len(stages))), value=len(stages) - 1,
        format_func=lambda i: "初始检索" if i == 0 else ("手动结束" if stages[i]["event"] == "manual_stop" else f"第{stages[i]['round']}轮回答后"),
        key=f"stage-{snapshot['state']['session_id']}-{len(stages)}",
    )
    stage = stages[index]
    previous = stages[max(0, index - 1)]
    if stage["question"]:
        question = stage["question"]
        st.write("本轮问题：" + question["text"])
        st.caption("选择依据：" + question["reason"] + f"；扣除检查成本和风险后的效用为 {question['utility']:.3f}")
        st.write("用户反馈：" + {"yes": question["yes_label"], "no": question["no_label"], "unknown": "暂时无法确认（概率保持不变）"}[stage["answer"]])
    if stage["stop_reason"]:
        st.info("停止原因：" + stage["stop_reason"] + "。当前首位原因仍需实际检查确认。")
    elif stage.get("next_question"):
        st.caption("下一问：" + stage["next_question"]["text"])
    st.graphviz_chart(stage_dot(stage, service.graph, previous), width="stretch")
    st.caption("蓝：故障；紫：问题；青：观察；黄：候选；灰：概率较上一阶段降低；绿：当前首位及排查路径。灰色不代表排除，负面回答也保留原图关系。")
    before = {c["name"]: (rank, c["probability"]) for rank, c in enumerate(previous["candidates"], 1)}
    st.dataframe([
        {"候选原因": c["name"], "上一阶段排名": before[c["name"]][0], "当前排名": rank,
         "上一阶段概率 (%)": round(before[c["name"]][1] * 100, 2), "当前概率 (%)": round(c["probability"] * 100, 2),
         "变化 (百分点)": round((c["probability"] - before[c["name"]][1]) * 100, 2)}
        for rank, c in enumerate(stage["candidates"], 1)
    ], hide_index=True, width="stretch")
    chart = pd.DataFrame([
        {"阶段": s["step"], **{c["name"]: c["probability"] * 100 for c in s["candidates"]}}
        for s in stages[:index + 1]
    ]).set_index("阶段")
    st.line_chart(chart, x_label="阶段", y_label="候选概率 (%)")
    st.caption("回看只改变展示，不修改当前诊断。证据可能使判断反转，概率不保证单调收敛。")
    st.download_button("下载完整轨迹（JSON）", json.dumps({"issue": snapshot["state"]["issue_name"], "stages": stages}, ensure_ascii=False, indent=2), file_name="debugpath-trajectory.json", mime="application/json")


def _render_evidence(snapshot: dict) -> None:
    evidence = snapshot["state"].get("evidence") or []
    if not evidence:
        return
    with st.expander("本次召回的文本证据", expanded=True):
        for item in evidence:
            source = item.get("source_title") or "未命名来源"
            score = float(item.get("score", 0.0))
            title = f"{item['chunk_id']} · {source} · 相关度 {score:.0%}"
            if item.get("url"):
                st.markdown(f"**[{title}]({item['url']})**")
            else:
                st.markdown(f"**{title}**")
            st.caption(item.get("text", ""))


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
            modes.append("DeepSeek受控编排模式")
        mode = st.radio("答案生成", modes)
        st.info("系统只生成检查建议，不会自动执行命令。")
        if st.button("重新开始", width="stretch"):
            st.session_state.pop("diagnosis", None)
            st.rerun()

    diagnose_tab, graph_tab, method_tab = st.tabs(["主动诊断", "诊断轨迹", "方法说明"])
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
            interaction_col, graph_col = st.columns([0.88, 1.12], gap="large")
            with interaction_col:
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
                    answer = {
                        question["yes_label"]: "yes",
                        question["no_label"]: "no",
                        "暂时无法确认": "unknown",
                    }[answer_label]
                    submit_col, stop_col = st.columns(2)
                    if submit_col.button("提交观察结果", type="primary", width="stretch"):
                        st.session_state.diagnosis = service.answer(state, question["name"], answer)
                        st.rerun()
                    if stop_col.button("结束追问，查看当前方案", width="stretch"):
                        st.session_state.diagnosis = service.complete(state)
                        st.rerun()
                else:
                    st.subheader("已验证的排查方案")
                    if snapshot["plan_errors"]:
                        st.error("方案验证未通过：" + "；".join(snapshot["plan_errors"]))
                    elif mode == "DeepSeek受控编排模式":
                        try:
                            st.markdown(render_with_llm(snapshot, LLMClient(settings)))
                        except Exception as exc:  # noqa: BLE001
                            st.warning(f"大模型暂不可用，已回退到离线答案：{exc}")
                            st.markdown(render_offline(snapshot))
                    else:
                        st.markdown(render_offline(snapshot))
            with graph_col:
                _render_live_graph(snapshot, service)
            _render_evidence(snapshot)

    with graph_tab:
        if "diagnosis" in st.session_state:
            _render_trajectory(st.session_state.diagnosis, service)
        else:
            st.info("开始一次诊断后，这里会显示问题、候选原因和下一条主动询问。")
        node_count = sum(len(items) for items in service.graph.entities.values())
        st.caption(f"知识库规模：{node_count} 个节点，{len(service.graph.relations)} 条受控关系。")

    with method_tab:
        st.subheader("为什么不是普通问答")
        st.markdown(
            "1. **版本化因果图谱**：原因、平台、版本、检查、修复和官方来源分别建模。\n"
            "2. **主动询问**：对每个未问问题计算期望信息增益，并扣除操作成本与风险。\n"
            "3. **受控知识注入**：模型只能编排白名单声明和证据ID；技术内容由已验证模板输出。"
        )
        st.code("Utility(q) = ExpectedInformationGain(q) - CheckCost(q) - RiskCost(q)", language=None)
        st.caption("候选概率用于决定排查顺序，不替代真实运行结果或专业判断。")


if __name__ == "__main__":
    main()
