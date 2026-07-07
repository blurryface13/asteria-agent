from dataclasses import dataclass, field


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    title: str
    content: str
    page_start: int | None
    score: float                  # retriever-specific score (cosine sim / BM25 / RRF)
    provenance: dict = field(default_factory=dict)  # per-stage scores for debugging/eval
