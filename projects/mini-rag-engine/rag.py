from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import re
from typing import Iterable


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def chunk_text(text: str, chunk_size: int = 60, overlap: int = 10) -> list[str]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Require chunk_size > overlap >= 0")
    words = text.split()
    if not words:
        return []
    step = chunk_size - overlap
    return [" ".join(words[i : i + chunk_size]) for i in range(0, len(words), step)]


@dataclass(frozen=True)
class SearchHit:
    document_id: str
    chunk: str
    score: float


class MiniRAG:
    def __init__(self) -> None:
        self._chunks: list[tuple[str, str]] = []
        self._term_counts: list[Counter[str]] = []
        self._idf: dict[str, float] = {}

    def fit(self, documents: dict[str, str], chunk_size: int = 60, overlap: int = 10) -> None:
        self._chunks = []
        self._term_counts = []

        for document_id, text in documents.items():
            for chunk in chunk_text(text, chunk_size=chunk_size, overlap=overlap):
                self._chunks.append((document_id, chunk))
                self._term_counts.append(Counter(tokenize(chunk)))

        document_frequency: Counter[str] = Counter()
        for counts in self._term_counts:
            document_frequency.update(counts.keys())

        total = max(len(self._term_counts), 1)
        self._idf = {
            term: math.log((1 + total) / (1 + df)) + 1
            for term, df in document_frequency.items()
        }

    def _vector(self, counts: Counter[str]) -> dict[str, float]:
        total_terms = sum(counts.values()) or 1
        return {
            term: (count / total_terms) * self._idf.get(term, 0.0)
            for term, count in counts.items()
            if term in self._idf
        }

    @staticmethod
    def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
        common = left.keys() & right.keys()
        numerator = sum(left[key] * right[key] for key in common)
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)

    def search(self, query: str, top_k: int = 3) -> list[SearchHit]:
        if top_k <= 0:
            return []
        query_vector = self._vector(Counter(tokenize(query)))
        scored: list[SearchHit] = []

        for (document_id, chunk), counts in zip(self._chunks, self._term_counts):
            score = self._cosine(query_vector, self._vector(counts))
            if score > 0:
                scored.append(SearchHit(document_id, chunk, round(score, 6)))

        return sorted(scored, key=lambda hit: hit.score, reverse=True)[:top_k]

    def evidence(self, query: str, top_k: int = 3) -> str:
        hits = self.search(query, top_k=top_k)
        return "\n\n".join(
            f"[{hit.document_id} | score={hit.score}] {hit.chunk}" for hit in hits
        )


if __name__ == "__main__":
    docs = {
        "agents": "Reliable AI agents separate model reasoning from deterministic tool execution. Approval gates are useful before irreversible actions.",
        "rag": "Retrieval augmented generation finds relevant evidence before asking a language model to produce an answer.",
        "evals": "Evaluation harnesses compare model behavior against repeatable requirements instead of subjective impressions.",
    }

    index = MiniRAG()
    index.fit(docs, chunk_size=30, overlap=5)
    print(index.evidence("How should an AI system retrieve evidence?"))
