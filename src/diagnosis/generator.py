"""将已验证计划渲染为离线或大模型辅助答案。"""
from __future__ import annotations

import json
from copy import deepcopy

from src.diagnosis.planner import DANGEROUS_COMMAND_MARKERS


def render_offline(snapshot: dict) -> str:
    candidates = snapshot["candidates"]
    if not candidates:
        return "当前知识图谱没有找到候选原因。"
    top = candidates[0]
    lines = [
        f"当前最可能的原因是 **{top['name']}**（{top['probability']:.1%}）。",
    ]
    evidence = snapshot.get("state", {}).get("evidence") or []
    if evidence:
        lines.extend(["", "本次召回的文本证据："])
        for item in evidence[:3]:
            source = item.get("source_title") or "未命名来源"
            lines.append(
                f"- [{item['chunk_id']}] [{source}]({item.get('url', '')})：{item.get('text', '')}"
            )
    lines.extend(["", "建议按以下顺序检查，检查结果不符合时再考虑下一项："])
    source_ids: dict[str, str] = {}
    for index, item in enumerate(snapshot["plan"], start=1):
        claim_id = item.get("claim_id", f"C{index}")
        for source in item["sources"]:
            source_ids.setdefault(source["title"], f"S{len(source_ids) + 1}")
        citations = " ".join(f"[{source_ids[source['title']]}]" for source in item["sources"])
        blocked = "（已阻止自动建议）" if item["blocked"] else ""
        lines.extend([
            "",
            f"{index}. **[{claim_id}] {item['cause']}** · {item['probability']:.1%} · "
            f"{item['risk']}{blocked}",
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


def build_claim_manifest(snapshot: dict) -> dict:
    """把模型可选择的声明与证据压缩成白名单。"""
    claims = [
        {
            "claim_id": f"C{index}",
            "cause": item["cause"],
            "risk_level": item["risk_level"],
            "blocked": item["blocked"],
            "source_titles": [source["title"] for source in item["sources"]],
        }
        for index, item in enumerate(snapshot.get("plan", []), start=1)
    ]
    evidence = [
        {
            "chunk_id": item["chunk_id"],
            "source_title": item.get("source_title", ""),
            "text": item.get("text", ""),
        }
        for item in snapshot.get("state", {}).get("evidence", [])
    ]
    return {"claims": claims, "evidence": evidence}


def validate_injection_decision(decision: dict, manifest: dict) -> list[str]:
    """验证模型只引用白名单ID，且不能删除任何已验证诊断项。"""
    errors: list[str] = []
    allowed_claims = [item["claim_id"] for item in manifest["claims"]]
    allowed_evidence = {item["chunk_id"] for item in manifest["evidence"]}
    order = decision.get("claim_order")
    evidence_ids = decision.get("evidence_ids")
    emphasis = decision.get("emphasis")
    if (
        not isinstance(order, list)
        or not all(isinstance(item, str) for item in order)
        or sorted(order) != sorted(allowed_claims)
    ):
        errors.append("claim_order必须完整且只能包含白名单声明")
    if (
        not isinstance(evidence_ids, list)
        or not all(isinstance(item, str) for item in evidence_ids)
        or len(evidence_ids) != len(set(evidence_ids))
        or not set(evidence_ids).issubset(allowed_evidence)
    ):
        errors.append("evidence_ids包含未召回证据或重复项")
    if emphasis not in {"diagnosis", "checks", "safety"}:
        errors.append("emphasis不在允许范围")
    return errors


def _render_injection_decision(snapshot: dict, decision: dict) -> str:
    selected = deepcopy(snapshot)
    plan_by_id = {
        f"C{index}": {**item, "claim_id": f"C{index}"}
        for index, item in enumerate(snapshot["plan"], start=1)
    }
    selected["plan"] = [plan_by_id[claim_id] for claim_id in decision["claim_order"]]
    selected_ids = set(decision["evidence_ids"])
    selected["state"]["evidence"] = [
        item
        for item in snapshot.get("state", {}).get("evidence", [])
        if item["chunk_id"] in selected_ids
    ]
    introductions = {
        "diagnosis": "以下按当前诊断优先级展示已验证结论。",
        "checks": "以下优先呈现可验证的检查路径，再考虑处理动作。",
        "safety": "以下方案优先保留前置检查、风险限制和证据来源。",
    }
    return introductions[decision["emphasis"]] + "\n\n" + render_offline(selected)


def render_with_llm(snapshot: dict, llm) -> str:
    """LLM只编排白名单声明和证据，技术内容仍由模板渲染。"""
    if snapshot.get("plan_errors"):
        return render_offline(snapshot)
    manifest = build_claim_manifest(snapshot)
    system_prompt = (
        "你是DebugPath的答案编排器，不负责生成技术内容。只输出JSON："
        '{"claim_order":["C1"],"evidence_ids":["E001"],'
        '"emphasis":"diagnosis|checks|safety"}。'
        "claim_order必须包含全部且仅包含给定声明ID；evidence_ids只能选择已召回ID。"
    )
    user_prompt = "请从以下白名单中选择展示次序和侧重点：\n" + json.dumps(
        manifest, ensure_ascii=False
    )
    try:
        if hasattr(llm, "chat_json"):
            decision = llm.chat_json(system_prompt, user_prompt, temperature=0.1)
        else:
            raw = llm.chat(system_prompt, user_prompt, temperature=0.1)
            if any(marker in raw.casefold() for marker in DANGEROUS_COMMAND_MARKERS):
                return render_offline(snapshot)
            decision = json.loads(raw)
    except (TypeError, ValueError):
        return render_offline(snapshot)
    if not isinstance(decision, dict) or validate_injection_decision(decision, manifest):
        return render_offline(snapshot)
    return _render_injection_decision(snapshot, decision)
