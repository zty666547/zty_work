"""将一次诊断整理为可脱敏分享、可复现实验的案例记录。"""
from __future__ import annotations

import re
from typing import Any


_REDACTIONS = (
    (re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b"), "[REDACTED_API_KEY]"),
    (
        re.compile(r"(?i)\b(Bearer)\s+[A-Za-z0-9._~+/=-]{10,}"),
        r"\1 [REDACTED_TOKEN]",
    ),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s]+"), r"[USER_HOME]"),
    (re.compile(r"/(?:Users|home)/[^/\s]+"), "/[USER_HOME]"),
    (
        re.compile(r"\b(?!127\.0\.0\.1\b)(?:\d{1,3}\.){3}\d{1,3}\b"),
        "[REDACTED_IP]",
    ),
)


def sanitize_text(value: str) -> str:
    """移除案例中常见的凭据和个人环境标识。"""
    sanitized = value
    for pattern, replacement in _REDACTIONS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def build_case_export(
    snapshot: dict[str, Any],
    actual_cause: str | None = None,
    confirmed: bool = False,
    note: str = "",
) -> dict[str, Any]:
    """生成稳定案例格式；未确认根因的记录永不进入准确率。"""
    state = snapshot["state"]
    candidates = snapshot.get("candidates", [])
    top = candidates[0] if candidates else {}
    is_confirmed = bool(confirmed and actual_cause)
    return {
        "schema_version": "debugpath-case-v1",
        "case_id": state["session_id"],
        "family": state["issue_name"],
        "report": sanitize_text(state["report"]),
        "answers": dict(state.get("answers", {})),
        "predicted_top_cause": top.get("name"),
        "predicted_top_probability": round(float(top.get("probability", 0.0)), 6),
        "decision": dict(snapshot.get("decision", {})),
        "actual_cause": actual_cause if is_confirmed else None,
        "root_cause_status": "confirmed" if is_confirmed else "unconfirmed",
        "include_in_accuracy": is_confirmed,
        "note": sanitize_text(note.strip()),
    }
