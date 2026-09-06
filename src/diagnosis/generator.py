"""将已验证计划渲染为离线或大模型辅助答案。"""
from __future__ import annotations

import json
import re

from src.diagnosis.planner import DANGEROUS_COMMAND_MARKERS


def render_offline(snapshot: dict) -> str:
    candidates = snapshot["candidates"]
    if not candidates:
        return "当前知识图谱没有找到候选原因。"
    top = candidates[0]
    lines = [
        f"当前最可能的原因是 **{top['name']}**（{top['probability']:.1%}）。",
        "",
        "建议按以下顺序检查，检查结果不符合时再考虑下一项：",
    ]
    source_ids: dict[str, str] = {}
    for index, item in enumerate(snapshot["plan"], start=1):
        for source in item["sources"]:
            source_ids.setdefault(source["title"], f"S{len(source_ids) + 1}")
        citations = " ".join(f"[{source_ids[source['title']]}]" for source in item["sources"])
        blocked = "（已阻止自动建议）" if item["blocked"] else ""
        lines.extend([
            "",
            f"{index}. **{item['cause']}** · {item['probability']:.1%} · {item['risk']}{blocked}",
            f"   - 前置检查：{item['check']}",
            f"   - 检查命令：`{item['command']}`" if item["command"] else "   - 检查命令：当前平台暂无命令模板",
            f"   - 处理建议：{item['repair'] if not item['blocked'] else '风险或证据校验未通过，请人工确认。'} {citations}",
        ])
    if source_ids:
        lines.extend(["", "证据来源："])
        all_sources = {source["title"]: source for item in snapshot["plan"] for source in item["sources"]}
        for title, source_id in source_ids.items():
            source = all_sources[title]
            lines.append(f"- [{source_id}] [{title}]({source.get('url', '')})")
    lines.extend(["", "> 概率用于排列排查优先级，不代表已经确定根因；系统不会自动执行任何命令。"])
    return "\n".join(lines)


def render_with_llm(snapshot: dict, llm) -> str:
    """LLM 只能解释已验证计划，不能新增命令、原因或修复动作。"""
    if snapshot.get("plan_errors"):
        return render_offline(snapshot)
    context = json.dumps(
        {"candidates": snapshot["candidates"], "verified_plan": snapshot["plan"]},
        ensure_ascii=False,
        default=list,
    )
    system_prompt = (
        "你是DebugPath的答案解释器。只能改写给定的候选原因和已验证计划；"
        "不得新增命令、原因或操作，不得声称已确定根因；保留风险提示和来源标题。"
    )
    answer = llm.chat(system_prompt, f"请用简洁中文解释以下诊断结果：\n{context}", temperature=0.1)
    allowed_text = "\n".join(
        f"{item['cause']} {item['check']} {item['command']} {item['repair']} "
        + " ".join(source["title"] for source in item["sources"])
        for item in snapshot["plan"]
    )
    code_spans = re.findall(r"`([^`]+)`", answer)
    unsafe = any(marker in answer.casefold() for marker in DANGEROUS_COMMAND_MARKERS)
    unsupported_code = any(code not in allowed_text for code in code_spans)
    if unsafe or unsupported_code:
        return render_offline(snapshot)
    return answer
