"""无外部依赖的中英文BM25证据检索与图谱候选融合。"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from src.data.loader import StructuredGraph
from src.diagnosis.models import DiagnosisState


def tokenize(text: str) -> list[str]:
    """保留错误码/包名，并为连续中文生成单字和二元词。"""
    lowered = text.casefold()
    tokens = re.findall(r"[a-z0-9_+.-]+", lowered)
    for block in re.findall(r"[\u4e00-\u9fff]+", lowered):
        tokens.extend(block)
        tokens.extend(block[index:index + 2] for index in range(len(block) - 1))
    return tokens


class EvidenceRetriever:
    def __init__(self, graph: StructuredGraph):
        self.chunks: list[dict] = []
        for item in graph.entities.get("EvidenceChunk", []):
            props = dict(item.get("props") or {})
            searchable = " ".join(
                [item["name"], props.get("text", ""), *(props.get("keywords") or [])]
            )
            self.chunks.append(
                {"name": item["name"], **props, "tokens": tokenize(searchable)}
            )
        self.chunk_causes: dict[str, list[str]] = defaultdict(list)
        for relation in graph.relations:
            if relation["type"] == "CHUNK_SUPPORTS_CAUSE":
                self.chunk_causes[relation["source"]].append(relation["target"])
        self.document_frequency = Counter(
            token for chunk in self.chunks for token in set(chunk["tokens"])
        )
        self.average_length = (
            sum(len(chunk["tokens"]) for chunk in self.chunks) / len(self.chunks)
            if self.chunks else 0.0
        )

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        query_tokens = tokenize(query)
        if not query_tokens or not self.chunks:
            return []
        scored: list[tuple[float, dict]] = []
        count = len(self.chunks)
        for chunk in self.chunks:
            frequencies = Counter(chunk["tokens"])
            length = len(chunk["tokens"])
            score = 0.0
            for token in query_tokens:
                frequency = frequencies[token]
                if not frequency:
                    continue
                document_frequency = self.document_frequency[token]
                inverse_frequency = math.log(1 + (count - document_frequency + 0.5) / (document_frequency + 0.5))
                denominator = frequency + 1.5 * (
                    1 - 0.75 + 0.75 * length / max(self.average_length, 1.0)
                )
                score += inverse_frequency * frequency * 2.5 / denominator
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: (-item[0], item[1]["name"]))
        maximum = scored[0][0] if scored else 1.0
        return [
            {
                "chunk_id": chunk.get("chunk_id", chunk["name"]),
                "name": chunk["name"],
                "text": chunk.get("text", ""),
                "source_title": chunk.get("source_title", ""),
                "url": chunk.get("url", ""),
                "section": chunk.get("section", ""),
                "platforms": chunk.get("platforms", []),
                "score": score / maximum,
                "supports_causes": self.chunk_causes.get(chunk["name"], []),
            }
            for score, chunk in scored[:top_k]
        ]

    def apply_to_state(
        self, state: DiagnosisState, hits: list[dict], weight: float = 0.45
    ) -> None:
        """融合归一化证据分布与图谱先验；主动问答仍负责最终收敛。"""
        cause_scores: dict[str, float] = defaultdict(float)
        for hit in hits:
            for cause in hit["supports_causes"]:
                if cause in state.probabilities:
                    cause_scores[cause] = max(cause_scores[cause], float(hit["score"]))
        evidence_total = sum(cause_scores.values())
        weight = min(max(weight, 0.0), 1.0)
        if evidence_total:
            state.probabilities = {
                cause: (1 - weight) * probability
                + weight * cause_scores[cause] / evidence_total
                for cause, probability in state.probabilities.items()
            }
        state.evidence = hits
