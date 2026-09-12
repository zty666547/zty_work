"""第二版故障族候选检索：用图谱证据补充脆弱的固定词串匹配。"""
from __future__ import annotations

from collections import defaultdict

from src.data.loader import StructuredGraph
from src.retrieval.bm25 import EvidenceRetriever


def _compact(text: str) -> str:
    return "".join(text.casefold().split())


class IssueRouter:
    """返回可解释的Top-k故障族候选，不直接改动第一版诊断引擎。"""

    def __init__(self, graph: StructuredGraph, evidence_top_k: int = 10):
        self.graph = graph
        self.evidence_top_k = evidence_top_k
        self.retriever = EvidenceRetriever(graph)
        self.issue_terms: dict[str, list[str]] = {}
        for item in graph.entities.get("Issue", []):
            props = item.get("props") or {}
            self.issue_terms[item["name"]] = [
                item["name"],
                *(props.get("aliases") or []),
                props.get("example", ""),
            ]

        self.cause_to_issue = {
            relation["target"]: relation["source"]
            for relation in graph.relations
            if relation["type"] == "HAS_POSSIBLE_CAUSE"
        }

    def candidates(self, report: str, top_k: int = 3) -> list[dict]:
        report = report.strip()
        if not report:
            return []
        normalized = report.casefold()
        compact = _compact(report)

        signature_raw: dict[str, float] = defaultdict(float)
        matched_signatures: dict[str, list[str]] = defaultdict(list)
        for issue, terms in self.issue_terms.items():
            for term in terms:
                if not term:
                    continue
                lowered = term.casefold()
                if lowered in normalized or _compact(term) in compact:
                    signature_raw[issue] += len(_compact(term))
                    matched_signatures[issue].append(term)

        evidence_raw: dict[str, float] = defaultdict(float)
        evidence_by_issue: dict[str, list[dict]] = defaultdict(list)
        for hit in self.retriever.search(report, top_k=self.evidence_top_k):
            issues = {
                self.cause_to_issue[cause]
                for cause in hit["supports_causes"]
                if cause in self.cause_to_issue
            }
            for issue in issues:
                evidence_raw[issue] += float(hit["score"])
                evidence_by_issue[issue].append(
                    {
                        "chunk_id": hit["chunk_id"],
                        "name": hit["name"],
                        "score": hit["score"],
                        "supports_causes": hit["supports_causes"],
                    }
                )

        issues = set(self.issue_terms)
        max_signature = max(signature_raw.values(), default=0.0)
        max_evidence = max(evidence_raw.values(), default=0.0)
        rows = []
        for issue in issues:
            signature_score = (
                signature_raw[issue] / max_signature if max_signature else 0.0
            )
            evidence_score = evidence_raw[issue] / max_evidence if max_evidence else 0.0
            score = 0.55 * signature_score + 0.45 * evidence_score
            if score <= 0:
                continue
            rows.append(
                {
                    "issue": issue,
                    "score": score,
                    "signature_score": signature_score,
                    "evidence_score": evidence_score,
                    "matched_signatures": matched_signatures[issue],
                    "evidence": sorted(
                        evidence_by_issue[issue],
                        key=lambda item: (-item["score"], item["name"]),
                    )[:3],
                }
            )
        rows.sort(key=lambda item: (-item["score"], item["issue"]))
        return rows[:top_k]

    def route(self, report: str) -> dict | None:
        """返回首位故障族及其证据；无任何匹配时返回None。"""
        decision = self.decide(report)
        if decision["status"] != "routed":
            return None
        return decision["candidates"][0]

    def decide(self, report: str, min_margin: float = 0.10) -> dict:
        """区分明确路由、跨故障族歧义和知识库外输入。"""
        rows = self.candidates(report, top_k=3)
        if not rows:
            return {
                "status": "unsupported",
                "selected_issue": None,
                "margin": 0.0,
                "clarification": None,
                "candidates": [],
            }
        first = rows[0]
        second_score = rows[1]["score"] if len(rows) > 1 else 0.0
        margin = first["score"] - second_score
        evidence_only_is_weak = (
            first["signature_score"] == 0.0 and len(first["evidence"]) < 2
        )
        if evidence_only_is_weak:
            status = "unsupported"
        elif len(rows) > 1 and margin < min_margin:
            status = "ambiguous"
        else:
            status = "routed"
        return {
            "status": status,
            "selected_issue": first["issue"] if status == "routed" else None,
            "margin": margin,
            "clarification": (
                self._clarification(first["issue"], rows[1]["issue"])
                if status == "ambiguous"
                else None
            ),
            "candidates": rows,
        }

    @staticmethod
    def _clarification(first: str, second: str) -> str:
        pair = frozenset({first, second})
        questions = {
            frozenset({"Python模块无法导入", "PyTorch无法使用GPU"}): (
                "问题主要发生在导入Python模块时，还是在PyTorch调用GPU/CUDA时？"
            ),
            frozenset({"Python模块无法导入", "服务或配置连接失败"}): (
                "问题主要是本地Python模块无法导入，还是访问某个服务/API时连接失败？"
            ),
            frozenset({"PyTorch无法使用GPU", "服务或配置连接失败"}): (
                "问题主要是本机GPU/CUDA不可用，还是容器或远程服务连接失败？"
            ),
        }
        return questions.get(pair, "请补充报错发生的操作、组件名称和完整错误信息。")
