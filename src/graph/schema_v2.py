"""DebugPath第二版新增的服务上下文图谱类型。"""
from __future__ import annotations

from src.graph.schema import ENTITY_TYPES, RELATION_SIGNATURES

ENTITY_TYPES_V2 = [
    *ENTITY_TYPES,
    "Service",
    "Endpoint",
    "DeploymentContext",
]

RELATION_SIGNATURES_V2 = {
    **RELATION_SIGNATURES,
    "CAUSE_CONTEXTUALIZED_BY": ("Cause", "DeploymentContext"),
    "CONTEXT_INVOLVES_CLIENT": ("DeploymentContext", "Service"),
    "CLIENT_CONNECTS_TO": ("Service", "Service"),
    "SERVICE_EXPOSES": ("Service", "Endpoint"),
    "ENDPOINT_REACHABLE_FROM": ("Endpoint", "DeploymentContext"),
    "CONTEXT_CHECKED_BY": ("DeploymentContext", "DiagnosticCheck"),
    "CONTEXT_RESOLVED_BY": ("DeploymentContext", "RepairAction"),
    "CHECK_TARGETS_ENDPOINT": ("DiagnosticCheck", "Endpoint"),
    "REPAIR_CONFIGURES_ENDPOINT": ("RepairAction", "Endpoint"),
}
