"""DebugPath Streamlit 交互式主动诊断页面。"""
from __future__ import annotations

import streamlit as st
import json
import pandas as pd
import time

from config.settings import settings
from src.diagnosis.engine import UnknownIssueError
from src.diagnosis.calibration import build_case_export_v2
from src.diagnosis.generator import render_offline, render_with_llm
from src.diagnosis.models import DiagnosisState
from src.diagnosis.service_v2 import AmbiguousIssueError, DiagnosisServiceV2
from src.diagnosis.trajectory_v2 import stage_dot_v2, storyboard_dot_v2
from src.extraction.llm_client import LLMClient
from src.graph.visualization_v2 import graph_structure_summary, schema_overview_dot

EXAMPLES = [
    "宿主机Ollama可以访问，但Docker中的Open WebUI连接失败",
    "ModuleNotFoundError: No module named 'pandas'",
    "torch.cuda.is_available() 返回 False，检测不到GPU",
    "Neo4j Connection refused，无法连接 localhost:7687",
    "API 请求返回 401 Unauthorized",
]


@st.cache_resource
def load_service() -> DiagnosisServiceV2:
    return DiagnosisServiceV2(settings)


def _render_candidates(snapshot: dict) -> None:
    st.subheader("当前候选原因")
    rows = [
        {"候选原因": item["name"], "当前概率": round(item["probability"] * 100, 1), "说明": item["description"]}
        for item in snapshot["candidates"]
    ]
    st.dataframe(rows, width="stretch", hide_index=True)
    st.bar_chart({row["候选原因"]: row["当前概率"] for row in rows}, horizontal=True)


def _render_live_graph(snapshot: dict, service: DiagnosisServiceV2) -> None:
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
    st.graphviz_chart(stage_dot_v2(stage, service.graph, previous), width="stretch")
    st.caption(
        "蓝：故障；灰：检索证据；黄：候选原因；紫：当前问题；青：用户观察；"
        "橙：服务与端点；粉：部署环境；绿：最终检查与修复。"
    )


def _render_trajectory(snapshot: dict, service: DiagnosisServiceV2) -> None:
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
    st.graphviz_chart(stage_dot_v2(stage, service.graph, previous), width="stretch")
    st.caption("每个阶段只显示实际参与当前推理的节点和关系。低概率候选仍然保留，完成后只沿最终原因展开检查、修复、风险和来源。")
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


def _render_routing(snapshot: dict) -> None:
    routing = snapshot.get("routing") or {}
    candidates = routing.get("candidates") or []
    if not candidates:
        return
    with st.expander("故障族检索依据", expanded=True):
        st.dataframe(
            [
                {
                    "候选故障族": item["issue"],
                    "综合得分": round(item["score"], 3),
                    "固定特征": round(item["signature_score"], 3),
                    "图谱证据": round(item["evidence_score"], 3),
                    "主要证据": "、".join(
                        evidence["name"] for evidence in item["evidence"]
                    ),
                }
                for item in candidates
            ],
            hide_index=True,
            width="stretch",
        )
        if snapshot.get("service_context"):
            st.info("已识别部署环境：" + snapshot["service_context"])


def _render_case_export(snapshot: dict) -> None:
    """让使用者回填实际结果；数据只通过浏览器下载，不自动上传。"""
    state = snapshot["state"]
    session_id = state["session_id"]
    with st.expander("记录真实排查结果"):
        st.caption(
            "用于后续真实案例评测。内容只在当前页面生成并下载，不会自动上传；"
            "问题回答耗时会随案例保存，密钥、邮箱、IP 和个人目录会自动脱敏。"
        )
        options = ["尚未确认", *[item["name"] for item in snapshot["candidates"]]]
        selected = st.selectbox(
            "实际根因",
            options,
            key=f"actual-cause-{session_id}",
        )
        confirmed = st.checkbox(
            "已通过检查结果或修复结果确认该根因",
            disabled=selected == "尚未确认",
            key=f"cause-confirmed-{session_id}",
        )
        note = st.text_area(
            "补充说明（可选）",
            placeholder="例如：执行了哪项检查，修复后是否恢复。请不要粘贴账号或密钥。",
            key=f"case-note-{session_id}",
        )
        payload = build_case_export_v2(
            snapshot,
            actual_cause=None if selected == "尚未确认" else selected,
            confirmed=confirmed,
            note=note,
        )
        if not payload["include_in_accuracy"]:
            st.info("当前将作为“未确认案例”导出，不会计入准确率。")
        st.download_button(
            "下载脱敏案例（JSON）",
            json.dumps(payload, ensure_ascii=False, indent=2),
            file_name=f"debugpath-case-{session_id}.json",
            mime="application/json",
            width="stretch",
        )


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
            st.session_state.pop("pending_routing", None)
            st.session_state.pop("question_timer_name", None)
            st.session_state.pop("question_timer_started_at", None)
            st.rerun()

    diagnose_tab, graph_tab, structure_tab, story_tab, method_tab = st.tabs(
        ["主动诊断", "诊断轨迹", "图谱结构", "固定案例", "方法说明"]
    )
    with diagnose_tab:
        pending = st.session_state.get("pending_routing")
        report = st.text_area(
            "粘贴报错信息或描述现象",
            value=pending["report"] if pending else "",
            placeholder=EXAMPLES[0],
            height=120,
            disabled="diagnosis" in st.session_state or pending is not None,
        )
        if "diagnosis" not in st.session_state:
            if pending:
                decision = pending["decision"]
                st.warning(decision["clarification"])
                options = [item["issue"] for item in decision["candidates"][:2]]
                selected_issue = st.radio("请选择更符合当前情况的一项", options)
                confirm_col, cancel_col = st.columns(2)
                if confirm_col.button("确认并进入诊断", type="primary", width="stretch"):
                    st.session_state.diagnosis = service.resolve_ambiguity(
                        pending["report"], selected_issue, decision
                    )
                    st.session_state.pop("pending_routing", None)
                    st.session_state.pop("question_timer_name", None)
                    st.session_state.pop("question_timer_started_at", None)
                    st.rerun()
                if cancel_col.button("重新描述故障", width="stretch"):
                    st.session_state.pop("pending_routing", None)
                    st.rerun()
            else:
                st.caption("可直接尝试：" + " ｜ ".join(EXAMPLES))
                if st.button("开始诊断", type="primary"):
                    try:
                        st.session_state.diagnosis = service.start(report)
                        st.rerun()
                    except AmbiguousIssueError as exc:
                        st.session_state.pending_routing = {
                            "report": report,
                            "decision": exc.decision,
                        }
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
            _render_routing(snapshot)
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
                    st.caption("页面记录本题从显示到提交的耗时，仅用于校准问题成本，不会自动上传。")
                    if st.session_state.get("question_timer_name") != question["name"]:
                        st.session_state.question_timer_name = question["name"]
                        st.session_state.question_timer_started_at = time.time()
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
                        started_at = st.session_state.get(
                            "question_timer_started_at", time.time()
                        )
                        response_seconds = max(0.0, min(time.time() - started_at, 3600.0))
                        st.session_state.diagnosis = service.answer_with_feedback(
                            state,
                            question["name"],
                            answer,
                            response_seconds=response_seconds,
                        )
                        st.session_state.pop("question_timer_name", None)
                        st.session_state.pop("question_timer_started_at", None)
                        st.rerun()
                    if stop_col.button("结束追问，查看当前方案", width="stretch"):
                        st.session_state.diagnosis = service.complete(state)
                        st.rerun()
                else:
                    if snapshot["decision"]["sufficient"]:
                        st.subheader("已验证的排查方案")
                    else:
                        st.subheader("当前排查建议（证据不足）")
                        st.warning(
                            "现有观察不足以支持确定性诊断。以下内容仅按当前候选顺序给出，"
                            "请先补充检查结果，不要直接执行修复。"
                        )
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
                    _render_case_export(snapshot)
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

    with structure_tab:
        structure = graph_structure_summary(service.graph)
        st.subheader("知识图谱由四层节点组成")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("节点", structure["node_count"])
        c2.metric("关系", structure["relation_count"])
        c3.metric("节点类型", structure["node_type_count"])
        c4.metric("关系类型", structure["relation_type_count"])
        st.graphviz_chart(schema_overview_dot(service.graph), width="stretch")
        st.caption(
            "红色粗边表示真正参与概率更新的观察→原因关系；其他边负责候选组织、"
            "证据追溯、环境限定和方案约束。"
        )
        st.dataframe(structure["nodes"], hide_index=True, width="stretch")
        st.subheader("因果关系怎样进入推理")
        st.markdown(
            "- `HAS_POSSIBLE_CAUSE`：建立候选原因，不能证明原因成立。\n"
            "- `CHUNK_SUPPORTS_CAUSE`：检索证据支持初始排序。\n"
            "- `OBSERVATION_SUPPORTS`：保存条件概率，用户回答后通过贝叶斯公式更新原因概率。\n"
            "- 环境、检查、修复、风险和来源关系：把最终原因约束为可执行且可追溯的方案。"
        )
        with st.expander("查看全部27类受控关系"):
            st.dataframe(structure["relations"], hide_index=True, width="stretch")

    with story_tab:
        demo_path = settings.raw_dir.parent / "demo" / "open_webui_ollama_trajectory.json"
        demo = json.loads(demo_path.read_text(encoding="utf-8"))
        stages = demo["trajectory"]
        labels = ["① 初始检索", "② 第一次回答后", "③ 稳健停止与方案"]
        selected_label = st.radio("选择截图阶段", labels, horizontal=True)
        stage_index = labels.index(selected_label)
        stage = stages[stage_index]
        top = stage["candidates"][0]
        st.subheader(labels[stage_index] + f"：{top['name']} {top['probability']:.1%}")
        if stage_index == 0:
            st.info("根据报错文本与证据片段形成5个候选原因，并选择第一条主动询问。")
        else:
            question = stage["question"]
            answer_text = {
                "yes": question["yes_label"],
                "no": question["no_label"],
                "unknown": "暂时无法确认",
            }[stage["answer"]]
            st.info(f"系统询问：{question['text']}　用户回答：{answer_text}")
        st.graphviz_chart(
            storyboard_dot_v2(stages, stage_index, service.graph),
            width="stretch",
        )
        st.caption(
            "节点直接标注中文类型；蓝色粗边表示本阶段新进入的节点；绿色表示最终原因。"
            "三个阶段共用完整图骨架，未进入当前阶段的节点隐藏，因此截图切换时位置保持稳定。"
        )
        if stage_index == len(stages) - 1:
            plan = demo["final"]["plan"]
            st.success("停止原因：" + demo["final"]["stop_reason"])
            st.write("检查：" + plan["check"])
            st.write("修复：" + plan["repair"])
            st.write("风险：" + plan["risk"] + f"（{plan['risk_level']}）")

    with method_tab:
        st.subheader("为什么不是普通问答")
        st.markdown(
            "1. **服务感知因果图谱**：将故障、原因、服务、端点、部署环境、检查、修复和来源分别建模。\n"
            "2. **可解释入口检索**：固定错误特征与BM25图谱证据共同给出候选故障族。\n"
            "3. **主动询问**：同时考虑信息增益、用户可回答率和检查成本，并使用稳健停止。\n"
            "4. **受控知识注入**：模型只能编排白名单声明和证据ID；技术内容由已验证模板输出。"
        )
        st.code("Utility(q) = InformationGain(q) × Answerability(q) - CheckCost(q) - RiskCost(q)", language=None)
        st.caption("停止诊断还要求：有效回答数足够、首位概率达标，并且明显领先第二名。")
        st.caption("候选概率用于决定排查顺序，不替代真实运行结果或专业判断。")


if __name__ == "__main__":
    main()
