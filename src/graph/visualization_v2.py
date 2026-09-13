"""第二版图谱结构的稳定、可核对展示数据。"""
from __future__ import annotations

import json
from collections import Counter

from src.graph.schema_v2 import ENTITY_TYPES_V2, RELATION_SIGNATURES_V2


TYPE_META = {
    "Issue": ("故障", "用户面对的问题类别", "故障与证据层"),
    "EvidenceChunk": ("证据", "从官方资料切分的可检索片段", "故障与证据层"),
    "Cause": ("原因", "需要逐步判断的候选根因", "故障与证据层"),
    "DiagnosticQuestion": ("问题", "系统可向用户提出的诊断问题", "交互推理层"),
    "Observation": ("观察", "用户回答所对应的可观测事实", "交互推理层"),
    "Service": ("服务", "参与连接的客户端或目标服务", "环境约束层"),
    "Endpoint": ("端点", "需要访问或检查的实际接口", "环境约束层"),
    "DeploymentContext": ("部署环境", "容器、宿主机等运行边界", "环境约束层"),
    "Package": ("软件包", "故障涉及的软件包", "环境约束层"),
    "Platform": ("平台", "Windows、Linux或macOS", "环境约束层"),
    "VersionConstraint": ("版本约束", "适用版本与兼容条件", "环境约束层"),
    "DiagnosticCheck": ("检查", "确认原因前执行的验证步骤", "方案输出层"),
    "RepairAction": ("修复", "检查后可以执行的处理操作", "方案输出层"),
    "Risk": ("风险", "执行修复前必须说明的风险", "方案输出层"),
    "DocumentSource": ("来源", "支撑证据、检查和修复的文档", "方案输出层"),
}

RELATION_DESCRIPTIONS = {
    "HAS_POSSIBLE_CAUSE": "故障包含候选原因，不代表原因已经成立",
    "HAS_QUESTION": "故障对应可提出的诊断问题",
    "CHECKS": "问题产生一个可以被确认的观察",
    "OBSERVATION_SUPPORTS": "观察通过条件概率支持或削弱原因",
    "CAUSE_CHECKED_BY": "原因对应验证步骤",
    "CAUSE_RESOLVED_BY": "原因对应修复操作",
    "REPAIR_REQUIRES": "修复必须先完成检查",
    "REPAIR_HAS_RISK": "修复关联风险提示",
    "AFFECTS_PACKAGE": "原因影响特定软件包",
    "VALID_ON": "原因适用于特定平台",
    "SUBJECT_TO_VERSION": "原因受版本条件限制",
    "CAUSE_SUPPORTED_BY": "原因定义具有文档依据",
    "CHECK_SUPPORTED_BY": "检查步骤具有文档依据",
    "REPAIR_SUPPORTED_BY": "修复操作具有文档依据",
    "SOURCE_CONTAINS_CHUNK": "来源文档包含检索证据片段",
    "CHUNK_SUPPORTS_CAUSE": "检索证据支持候选原因",
    "CHUNK_SUPPORTS_CHECK": "检索证据支持检查步骤",
    "CHUNK_SUPPORTS_REPAIR": "检索证据支持修复操作",
    "CAUSE_CONTEXTUALIZED_BY": "通用原因落到具体部署环境",
    "CONTEXT_INVOLVES_CLIENT": "部署环境包含客户端服务",
    "CLIENT_CONNECTS_TO": "客户端服务连接目标服务",
    "SERVICE_EXPOSES": "目标服务提供实际端点",
    "ENDPOINT_REACHABLE_FROM": "端点需要从指定部署环境访问",
    "CONTEXT_CHECKED_BY": "部署环境对应专属检查",
    "CONTEXT_RESOLVED_BY": "部署环境对应专属修复",
    "CHECK_TARGETS_ENDPOINT": "检查针对实际端点",
    "REPAIR_CONFIGURES_ENDPOINT": "修复配置实际端点",
}


def graph_structure_summary(graph) -> dict:
    """从当前运行图谱生成节点与关系清单，避免文档数字漂移。"""
    entity_counts = {
        entity_type: len(graph.entities.get(entity_type, []))
        for entity_type in ENTITY_TYPES_V2
    }
    relation_counts = Counter(item["type"] for item in graph.relations)
    node_rows = [
        {
            "层次": TYPE_META[entity_type][2],
            "中文类型": TYPE_META[entity_type][0],
            "节点类型": entity_type,
            "当前数量": entity_counts[entity_type],
            "作用": TYPE_META[entity_type][1],
        }
        for entity_type in ENTITY_TYPES_V2
    ]
    relation_rows = [
        {
            "关系类型": relation_type,
            "起点": TYPE_META[source][0],
            "终点": TYPE_META[target][0],
            "当前数量": relation_counts[relation_type],
            "含义": RELATION_DESCRIPTIONS[relation_type],
        }
        for relation_type, (source, target) in RELATION_SIGNATURES_V2.items()
    ]
    return {
        "node_count": sum(entity_counts.values()),
        "relation_count": sum(relation_counts.values()),
        "node_type_count": len(ENTITY_TYPES_V2),
        "relation_type_count": len(RELATION_SIGNATURES_V2),
        "nodes": node_rows,
        "relations": relation_rows,
    }


def schema_overview_dot(graph) -> str:
    """展示四层节点与核心关系；完整27类关系由结构表补充。"""
    summary = graph_structure_summary(graph)
    counts = {item["节点类型"]: item["当前数量"] for item in summary["nodes"]}
    q = lambda value: json.dumps(value, ensure_ascii=False)
    layer_meta = {
        "故障与证据层": ("cluster_knowledge", "#eff6ff"),
        "交互推理层": ("cluster_reasoning", "#faf5ff"),
        "环境约束层": ("cluster_context", "#fff7ed"),
        "方案输出层": ("cluster_action", "#f0fdf4"),
    }
    colors = {
        "故障与证据层": "#dbeafe",
        "交互推理层": "#ede9fe",
        "环境约束层": "#fed7aa",
        "方案输出层": "#bbf7d0",
    }
    lines = [
        "digraph Schema {", "rankdir=LR;", "compound=true;",
        'graph [bgcolor="transparent", nodesep=0.28, ranksep=0.62];',
        'node [shape=box, style="rounded,filled", fontname="Arial", fontsize=10, color="#64748b"];',
        'edge [fontname="Arial", fontsize=8, color="#64748b"];',
    ]
    for layer, (cluster, background) in layer_meta.items():
        lines.append(f"subgraph {cluster} {{")
        lines.append(f"label={q(layer)}; style=rounded; color={q(background)};")
        for entity_type in ENTITY_TYPES_V2:
            chinese, _, entity_layer = TYPE_META[entity_type]
            if entity_layer != layer:
                continue
            label = f"【{chinese}】\n{entity_type}\n{counts[entity_type]}个节点"
            lines.append(
                f"{q(entity_type)} [label={q(label)}, fillcolor={q(colors[layer])}];"
            )
        lines.append("}")
    key_edges = [
        ("Issue", "Cause", "候选原因"),
        ("EvidenceChunk", "Cause", "检索证据支持"),
        ("Issue", "DiagnosticQuestion", "提出问题"),
        ("DiagnosticQuestion", "Observation", "得到观察"),
        ("Observation", "Cause", "条件概率更新"),
        ("Cause", "DeploymentContext", "限定部署环境"),
        ("DeploymentContext", "Service", "涉及客户端"),
        ("Service", "Endpoint", "连接并访问端点"),
        ("Cause", "Package", "影响软件包"),
        ("Cause", "Platform", "适用平台"),
        ("Cause", "VersionConstraint", "版本限制"),
        ("DeploymentContext", "DiagnosticCheck", "选择检查"),
        ("DeploymentContext", "RepairAction", "选择修复"),
        ("RepairAction", "DiagnosticCheck", "先检查后修复"),
        ("RepairAction", "Risk", "风险提示"),
        ("DiagnosticCheck", "DocumentSource", "检查依据"),
        ("RepairAction", "DocumentSource", "修复依据"),
    ]
    for source, target, label in key_edges:
        width = 2.6 if label == "条件概率更新" else 1.1
        color = "#dc2626" if label == "条件概率更新" else "#64748b"
        lines.append(
            f"{q(source)} -> {q(target)} [label={q(label)}, color={q(color)}, penwidth={width}];"
        )
    lines.append("}")
    return "\n".join(lines)
