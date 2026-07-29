from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VectorSearchHit:
    chunk_id: int
    score: float
