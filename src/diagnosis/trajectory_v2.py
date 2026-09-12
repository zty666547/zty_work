"""第二版逐阶段子图：记录每一步实际使用的节点和关系。"""
from __future__ import annotations

import json


def stage_subgraph(stage: dict, graph, previous: dict | None = None) -> dict:
    nodes = {
        item["name"]: {"type": entity_type, "props": item.get("props", {})}
        for entity_type, items in graph.entities.items()
        for item in items
    }
    probabilities = {
        item["name"]: item["probability"] for item in stage["candidates"]
    }
    previous_probabilities = {
        item["name"]: item["probability"]
        for item in (previous or stage)["candidates"]
    }
    selected = {stage["issue_name"], *probabilities}
    roles: dict[str, str] = {stage["issue_name"]: "issue"}
    roles.update({name: "candidate_cause" for name in probabilities})

    routing = stage.get("routing") or {}
    routing_candidates = routing.get("candidates") or []
    if routing_candidates:
        for evidence in routing_candidates[0].get("evidence", []):
            selected.add(evidence["name"])
            roles[evidence["name"]] = "routing_evidence"

    question = stage.get("question") or stage.get("next_question")
    if question:
        selected.add(question["name"])
        roles[question["name"]] = "current_question"
    observation = stage.get("observation")
    if observation:
        selected.add(observation)
        roles[observation] = "user_observation"

    context = stage.get("service_context")
    if context:
        selected.add(context)
        roles[context] = "deployment_context"
        context_relations = {
            "CONTEXT_INVOLVES_CLIENT",
            "CLIENT_CONNECTS_TO",
            "SERVICE_EXPOSES",
            "ENDPOINT_REACHABLE_FROM",
        }
        for _ in range(3):
            selected.update(
                relation["target"]
                for relation in graph.relations
                if relation["source"] in selected
                and relation["type"] in context_relations
            )
        for name in selected:
            if nodes.get(name, {}).get("type") in {
                "Service",
                "Endpoint",
                "DeploymentContext",
            }:
                roles.setdefault(name, "service_context")

    if stage["status"] == "completed":
        top = stage["candidates"][0]["name"]
        roles[top] = "final_cause"
        completion_relations = {
            "CAUSE_CONTEXTUALIZED_BY",
            "CONTEXT_CHECKED_BY",
            "CONTEXT_RESOLVED_BY",
            "CHECK_TARGETS_ENDPOINT",
            "REPAIR_CONFIGURES_ENDPOINT",
            "REPAIR_REQUIRES",
            "REPAIR_HAS_RISK",
            "CAUSE_SUPPORTED_BY",
            "CHECK_SUPPORTED_BY",
            "REPAIR_SUPPORTED_BY",
        }
        frontier = {top, *({context} if context else set())}
        for _ in range(3):
            discovered = {
                relation["target"]
                for relation in graph.relations
                if relation["source"] in frontier
                and relation["type"] in completion_relations
            }
            selected.update(discovered)
            frontier = discovered
        for name in selected:
            entity_type = nodes.get(name, {}).get("type")
            if entity_type == "DiagnosticCheck":
                roles.setdefault(name, "final_check")
            elif entity_type == "RepairAction":
                roles.setdefault(name, "final_repair")
            elif entity_type == "Risk":
                roles.setdefault(name, "final_risk")
            elif entity_type == "DocumentSource":
                roles.setdefault(name, "final_source")

    subgraph_nodes = []
    for name in sorted(selected):
        if name not in nodes:
            continue
        probability = probabilities.get(name)
        before = previous_probabilities.get(name, probability)
        subgraph_nodes.append(
            {
                "name": name,
                "type": nodes[name]["type"],
                "role": roles.get(name, "context"),
                "probability": probability,
                "probability_change": (
                    probability - before
                    if probability is not None and before is not None
                    else None
                ),
            }
        )
    subgraph_edges = [
        {
            "source": relation["source"],
            "target": relation["target"],
            "type": relation["type"],
            "props": relation.get("props", {}),
        }
        for relation in graph.relations
        if relation["source"] in selected and relation["target"] in selected
    ]
    return {
        "step": stage["step"],
        "event": stage["event"],
        "status": stage["status"],
        "stop_reason": stage["stop_reason"],
        "nodes": subgraph_nodes,
        "edges": subgraph_edges,
    }


def stage_dot_v2(stage: dict, graph, previous: dict | None = None) -> str:
    """把结构化阶段子图转换为保持语义颜色一致的Graphviz。"""
    subgraph = stage_subgraph(stage, graph, previous)
    props = {
        item["name"]: item.get("props", {})
        for items in graph.entities.values()
        for item in items
    }
    colors = {
        "Issue": "#bfdbfe",
        "Cause": "#fef08a",
        "DiagnosticQuestion": "#ddd6fe",
        "Observation": "#a5f3fc",
        "EvidenceChunk": "#e5e7eb",
        "Service": "#fed7aa",
        "Endpoint": "#fdba74",
        "DeploymentContext": "#fecdd3",
        "DiagnosticCheck": "#bbf7d0",
        "RepairAction": "#86efac",
        "Risk": "#fecaca",
        "DocumentSource": "#d1d5db",
    }
    shapes = {
        "EvidenceChunk": "note",
        "DiagnosticQuestion": "box",
        "DiagnosticCheck": "box",
        "RepairAction": "box",
        "DocumentSource": "folder",
        "Endpoint": "component",
        "DeploymentContext": "hexagon",
    }
    q = lambda value: json.dumps(value, ensure_ascii=False)
    lines = [
        "digraph G {",
        "rankdir=LR;",
        'graph [bgcolor="transparent", nodesep=0.35, ranksep=0.55];',
        'node [style="filled,rounded", fontname="Arial", fontsize=10];',
        'edge [fontname="Arial", fontsize=8, color="#64748b"];',
    ]
    answer = stage.get("answer")
    for node in subgraph["nodes"]:
        name = node["name"]
        entity_type = node["type"]
        label = name
        if entity_type == "DiagnosticQuestion":
            label = props[name].get("text", name)
        elif node["role"] == "user_observation" and answer:
            answer_text = {"yes": "是", "no": "否", "unknown": "不清楚"}[answer]
            label = f"{name}\n用户回答：{answer_text}"
        if node["probability"] is not None:
            label = f"{name}\n{node['probability']:.1%}"
            change = node["probability_change"]
            if change and abs(change) >= 0.0005:
                label += f" ({change:+.1%})"
        color = colors.get(entity_type, "#f8fafc")
        penwidth = 1.2
        if node["role"] == "final_cause":
            color = "#4ade80"
            penwidth = 3.0
        elif node["role"] == "candidate_cause" and (
            node["probability_change"] or 0
        ) < -1e-9:
            color = "#e5e7eb"
        width = 1.2 + (node["probability"] or 0) * 1.5
        lines.append(
            f"{q(name)} [label={q(label)}, fillcolor={q(color)}, "
            f"shape={shapes.get(entity_type, 'ellipse')}, width={width:.2f}, "
            f"penwidth={penwidth:.1f}];"
        )
    relation_labels = {
        "HAS_POSSIBLE_CAUSE": "候选原因",
        "HAS_QUESTION": "诊断问题",
        "CHECKS": "得到观察",
        "OBSERVATION_SUPPORTS": "更新概率",
        "CHUNK_SUPPORTS_CAUSE": "证据支持",
        "CAUSE_CONTEXTUALIZED_BY": "发生于",
        "CONTEXT_INVOLVES_CLIENT": "客户端",
        "CLIENT_CONNECTS_TO": "连接",
        "SERVICE_EXPOSES": "提供端点",
        "ENDPOINT_REACHABLE_FROM": "访问环境",
        "CONTEXT_CHECKED_BY": "上下文检查",
        "CONTEXT_RESOLVED_BY": "上下文修复",
        "CHECK_TARGETS_ENDPOINT": "检查端点",
        "REPAIR_CONFIGURES_ENDPOINT": "配置端点",
        "REPAIR_REQUIRES": "前置检查",
        "REPAIR_HAS_RISK": "风险",
        "CHECK_SUPPORTED_BY": "来源",
        "REPAIR_SUPPORTED_BY": "来源",
    }
    for edge in subgraph["edges"]:
        label = relation_labels.get(edge["type"], edge["type"])
        lines.append(
            f"{q(edge['source'])} -> {q(edge['target'])} [label={q(label)}];"
        )
    lines.append("}")
    return "\n".join(lines)
