"""DebugPath 版本感知故障诊断知识图谱 Schema。"""
from __future__ import annotations

ENTITY_TYPES = [
    "Issue", "Cause", "Observation", "DiagnosticQuestion",
    "DiagnosticCheck", "RepairAction", "Package", "Platform",
    "VersionConstraint", "Risk", "DocumentSource",
    "EvidenceChunk",
]

RELATION_SIGNATURES = {
    "HAS_POSSIBLE_CAUSE": ("Issue", "Cause"),
    "HAS_QUESTION": ("Issue", "DiagnosticQuestion"),
    "CHECKS": ("DiagnosticQuestion", "Observation"),
    "OBSERVATION_SUPPORTS": ("Observation", "Cause"),
    "CAUSE_CHECKED_BY": ("Cause", "DiagnosticCheck"),
    "CAUSE_RESOLVED_BY": ("Cause", "RepairAction"),
    "REPAIR_REQUIRES": ("RepairAction", "DiagnosticCheck"),
    "REPAIR_HAS_RISK": ("RepairAction", "Risk"),
    "AFFECTS_PACKAGE": ("Cause", "Package"),
    "VALID_ON": ("Cause", "Platform"),
    "SUBJECT_TO_VERSION": ("Cause", "VersionConstraint"),
    "CAUSE_SUPPORTED_BY": ("Cause", "DocumentSource"),
    "CHECK_SUPPORTED_BY": ("DiagnosticCheck", "DocumentSource"),
    "REPAIR_SUPPORTED_BY": ("RepairAction", "DocumentSource"),
    "SOURCE_CONTAINS_CHUNK": ("DocumentSource", "EvidenceChunk"),
    "CHUNK_SUPPORTS_CAUSE": ("EvidenceChunk", "Cause"),
    "CHUNK_SUPPORTS_CHECK": ("EvidenceChunk", "DiagnosticCheck"),
    "CHUNK_SUPPORTS_REPAIR": ("EvidenceChunk", "RepairAction"),
}

RELATION_TYPES = list(RELATION_SIGNATURES)
