from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sys
from time import perf_counter
from typing import Any, Literal, Protocol, Sequence
import unicodedata


DESIGN_VERSION = "V1.1"
ABLATION_DESIGN_SHA256 = (
    "442bedce1c43b27b3557b0055708342edd278e98bcac0c12a68c1390fe88f655"
)
DENSE_THRESHOLD = 0.35
RAW_BRANCH_LIMIT = 18
FUSED_LIMIT = 18
RRF_CONSTANT = 60
BM25_K1 = 1.5
BM25_B = 0.75
BM25_EPSILON = 0.25
RERANKER_MODEL_ID = "BAAI/bge-reranker-v2-m3"
RERANKER_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
RERANKER_TOKEN_CAP = 1024
FINAL_TOP_K = 6
PER_MATERIAL_CAP = 3
MAX_CHUNK_CHARS = 2200
MAX_CONTEXT_CHARS = 12000

Arm = Literal["B", "C", "D"]

REJECTION_REASONS = (
    "dense_ineligible",
    "not_admitted",
    "fused_top18_cutoff",
    "overlap_dedup",
    "diversity_deferred",
    "final_top_k",
    "context_budget",
    "empty_content",
)


class ContractViolation(RuntimeError):
    """A frozen V1.1 contract was violated and execution must stop."""


_IDENTIFIER = re.compile(r"[a-z0-9]+(?:[_.:/-]+[a-z0-9]+)*")
_IDENTIFIER_PART = re.compile(r"[a-z0-9]+")
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_LEXICAL_SPAN = re.compile(
    r"(?P<identifier>[a-z0-9]+(?:[_.:/-]+[a-z0-9]+)*)|"
    r"(?P<cjk>[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+)"
)


def analyze_lexical(text: str) -> list[str]:
    """Apply the frozen bilingual BM25 analyzer to query or chunk text."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    for match in _LEXICAL_SPAN.finditer(normalized):
        identifier = match.group("identifier")
        if identifier is not None:
            tokens.append(identifier)
            for part in _IDENTIFIER_PART.findall(identifier):
                if part != identifier:
                    tokens.append(part)
            continue
        cjk = match.group("cjk") or ""
        if len(cjk) == 1:
            tokens.append(cjk)
        else:
            tokens.extend(cjk[index : index + 2] for index in range(len(cjk) - 1))
    return tokens


def stable_candidate_identity(document_id: str, chunk_index: int, content_hash: str) -> str:
    return f"{document_id}:{chunk_index}:{content_hash}"


@dataclass(frozen=True, slots=True)
class CorpusChunk:
    identity: str
    document_id: str
    chunk_index: int
    content_hash: str
    filename: str
    page_number: int | None
    section_title: str | None
    raw_text: str
    material_id: int
    chunk_id: int
    evidence_ids: tuple[str, ...]


@dataclass(slots=True)
class Candidate:
    identity: str
    document_id: str
    chunk_index: int
    content_hash: str
    filename: str
    page_number: int | None
    section_title: str | None
    raw_text: str
    material_id: int
    chunk_id: int
    evidence_ids: tuple[str, ...]
    arm: Arm
    dense_score: float | None = None
    dense_rank: int | None = None
    branch_admitted_dense: bool = False
    dense_fusion_rank: int | None = None
    bm25_score: float | None = None
    bm25_rank: int | None = None
    branch_admitted_bm25: bool = False
    bm25_fusion_rank: int | None = None
    candidate_admitted: bool = False
    fusion_score: float | None = None
    fusion_rank: int | None = None
    reranker_score: float | None = None
    reranker_rank: int | None = None
    reranker_truncated: bool | None = None
    reranker_input_tokens: int | None = None
    governance_input_rank: int | None = None
    selected: bool = False
    selected_text_chars: int | None = None
    rejection_reason: str | None = None

    @classmethod
    def from_chunk(cls, chunk: CorpusChunk, arm: Arm) -> Candidate:
        return cls(
            identity=chunk.identity,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            content_hash=chunk.content_hash,
            filename=chunk.filename,
            page_number=chunk.page_number,
            section_title=chunk.section_title,
            raw_text=chunk.raw_text,
            material_id=chunk.material_id,
            chunk_id=chunk.chunk_id,
            evidence_ids=chunk.evidence_ids,
            arm=arm,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "content_hash": self.content_hash,
            "filename": self.filename,
            "page_number": self.page_number,
            "section_title": self.section_title,
            "raw_text": self.raw_text,
            "material_id": self.material_id,
            "chunk_id": self.chunk_id,
            "evidence_ids": list(self.evidence_ids),
            "dense_score": self.dense_score,
            "dense_rank": self.dense_rank,
            "branch_admitted_dense": self.branch_admitted_dense,
            "dense_fusion_rank": self.dense_fusion_rank,
            "bm25_score": self.bm25_score,
            "bm25_rank": self.bm25_rank,
            "branch_admitted_bm25": self.branch_admitted_bm25,
            "bm25_fusion_rank": self.bm25_fusion_rank,
            "candidate_admitted": self.candidate_admitted,
            "fusion_score": self.fusion_score,
            "fusion_rank": self.fusion_rank,
            "reranker_score": self.reranker_score,
            "reranker_rank": self.reranker_rank,
            "reranker_truncated": self.reranker_truncated,
            "reranker_input_tokens": self.reranker_input_tokens,
            "governance_input_rank": self.governance_input_rank,
            "selected": self.selected,
            "selected_text_chars": self.selected_text_chars,
            "rejection_reason": self.rejection_reason,
            "arm": self.arm,
        }


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _normalize_anchor(value: str) -> str:
    return " ".join(value.casefold().split())


def _anchor_texts(project_root: Path, anchors: dict[str, Any]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for anchor in anchors["anchors"]:
        locator = anchor["locator"]
        if locator["kind"] != "SOURCE_LINES":
            continue
        lines = (project_root / locator["source_path"]).read_text(
            encoding="utf-8"
        ).splitlines()
        texts[anchor["evidence_id"]] = "\n".join(
            _normalize_anchor(line)
            for line in lines[locator["start_line"] - 1 : locator["end_line"]]
        )
    return texts


def _evidence_ids(
    *,
    chunk: Any,
    document_id: str,
    anchors: dict[str, Any],
    anchor_texts: dict[str, str],
) -> tuple[str, ...]:
    content = _normalize_anchor(chunk.content)
    matches: list[str] = []
    for anchor in anchors["anchors"]:
        if anchor["document_id"] != document_id:
            continue
        locator = anchor["locator"]
        matched = False
        if locator["kind"] == "PDF_PAGE":
            matched = chunk.page_number == locator["page_number"]
        else:
            material_text = anchor_texts[anchor["evidence_id"]]
            anchor_text = _normalize_anchor(material_text)
            if len(content) >= 60 and (content in anchor_text or anchor_text in content):
                matched = True
            elif content:
                matched = any(
                    len(line) >= 60 and line in content
                    for line in material_text.splitlines()
                )
        if matched:
            matches.append(anchor["evidence_id"])
    return tuple(sorted(matches))


@dataclass(frozen=True, slots=True)
class FrozenCorpus:
    chunks: tuple[CorpusChunk, ...]
    by_identity: dict[str, CorpusChunk]
    by_document_chunk: dict[tuple[str, int], CorpusChunk]

    @classmethod
    def from_project(cls, project_root: Path) -> FrozenCorpus:
        backend = str(project_root / "backend")
        if backend not in sys.path:
            sys.path.insert(0, backend)
        from app.services.material_processing.chunking import chunk_sections
        from app.services.material_processing.cleaning import clean_text
        from app.services.material_processing.parsers import parser_for
        from app.services.material_processing.types import ParsedSection

        v1 = project_root / "evals/rag_real_world_corpus/v1"
        manifest = _json(v1 / "corpus_manifest.json")
        projection = _json(v1 / "chunk_projection.json")["canonical_chunking"]
        inventory_rows = _json(
            v1
            / "results/ingestion_v1/20260813T131304Z-ac0a8cee/chunk_inventory.json"
        )
        inventory = {
            (row["document_id"], row["chunk_index"]): row for row in inventory_rows
        }
        if len(inventory) != 442:
            raise ContractViolation(f"frozen inventory is not 442 unique chunks: {len(inventory)}")
        anchors = _json(v1 / "gold/v1/evidence_anchors.json")
        anchor_texts = _anchor_texts(project_root, anchors)
        chunks: list[CorpusChunk] = []
        for document in manifest["documents"]:
            path = project_root / document["repository_path"]
            parsed = parser_for(path, document["source_format"]).parse(path)
            cleaned_sections = [
                ParsedSection(
                    text=clean_text(
                        section.text,
                        repair_pdf_lines=parsed.parser_type == "pdf",
                    ),
                    source_order=section.source_order,
                    page_number=section.page_number,
                    section_title=section.section_title,
                )
                for section in parsed.sections
            ]
            drafts = chunk_sections(
                [section for section in cleaned_sections if section.text],
                chunk_size=projection["chunk_size"],
                overlap=projection["overlap"],
                min_chunk_size=projection["min_chunk_size"],
            )
            for draft in drafts:
                key = (document["document_id"], draft.chunk_index)
                row = inventory.get(key)
                if row is None:
                    raise ContractViolation(f"reconstructed chunk missing from inventory: {key}")
                observed = {
                    "content_hash": draft.content_hash,
                    "char_count": draft.char_count,
                    "page_number": draft.page_number,
                    "section_title": draft.section_title,
                }
                expected = {name: row[name] for name in observed}
                if observed != expected:
                    raise ContractViolation(
                        f"reconstructed chunk differs from frozen inventory {key}: "
                        f"{observed!r} != {expected!r}"
                    )
                identity = stable_candidate_identity(
                    document["document_id"], draft.chunk_index, draft.content_hash
                )
                chunks.append(
                    CorpusChunk(
                        identity=identity,
                        document_id=document["document_id"],
                        chunk_index=draft.chunk_index,
                        content_hash=draft.content_hash,
                        filename=path.name,
                        page_number=draft.page_number,
                        section_title=draft.section_title,
                        raw_text=draft.content,
                        material_id=row["material_id"],
                        chunk_id=row["chunk_id"],
                        evidence_ids=_evidence_ids(
                            chunk=draft,
                            document_id=document["document_id"],
                            anchors=anchors,
                            anchor_texts=anchor_texts,
                        ),
                    )
                )
        chunks.sort(key=lambda item: (item.material_id, item.chunk_index, item.chunk_id))
        if len(chunks) != 442:
            raise ContractViolation(f"reconstructed corpus is not 442 chunks: {len(chunks)}")
        by_identity = {item.identity: item for item in chunks}
        by_document_chunk = {(item.document_id, item.chunk_index): item for item in chunks}
        if len(by_identity) != 442 or len(by_document_chunk) != 442:
            raise ContractViolation("stable candidate identities are not unique")
        return cls(tuple(chunks), by_identity, by_document_chunk)


class DenseAdapter(Protocol):
    def retrieve(self, case_id: str, *, arm: Arm) -> tuple[str, list[Candidate]]: ...


class FrozenDenseTraceAdapter:
    """Expose frozen production Dense Top18 as an immutable experimental adapter."""

    def __init__(self, baseline_path: Path, corpus: FrozenCorpus):
        raw = _json(baseline_path)
        if raw["run_id"] != "20260814T052007Z-593cd2ac":
            raise ContractViolation(f"unexpected frozen A run: {raw['run_id']}")
        self.raw = raw
        self.corpus = corpus
        self.cases = {row["case_id"]: row for row in raw["cases"]}
        if len(self.cases) != 72:
            raise ContractViolation(f"frozen A case count is not 72: {len(self.cases)}")

    def retrieve(self, case_id: str, *, arm: Arm) -> tuple[str, list[Candidate]]:
        record = self.cases[case_id]
        diagnostic = record["diagnostic"]
        rows = diagnostic["candidates"]
        if len(rows) > RAW_BRANCH_LIMIT:
            raise ContractViolation(f"Dense candidate cap violated for {case_id}: {len(rows)}")
        candidates: list[Candidate] = []
        for expected_rank, row in enumerate(rows, start=1):
            if row["rank"] != expected_rank:
                raise ContractViolation(f"Dense ranks are not contiguous for {case_id}")
            chunk = self.corpus.by_document_chunk[(row["document_id"], row["chunk_index"])]
            if row["content"] != chunk.raw_text:
                raise ContractViolation(
                    f"frozen Dense text differs from reconstructed chunk: {case_id}/{chunk.identity}"
                )
            candidate = Candidate.from_chunk(chunk, arm)
            candidate.dense_score = float(row["score"])
            candidate.dense_rank = row["rank"]
            candidates.append(candidate)
        return diagnostic["query"], candidates

    def gold_case(self, case_id: str) -> dict[str, Any]:
        return self.cases[case_id]["gold_case"]

    def reference_candidates(self, case_id: str) -> list[dict[str, Any]]:
        return self.cases[case_id]["diagnostic"]["candidates"]

    def reference_selected(self, case_id: str) -> list[dict[str, Any]]:
        return self.cases[case_id]["retrieval"]["selected_sources"]


class FrozenBM25Index:
    """Experiment-local, dependency-free BM25Okapi with the frozen defaults."""

    implementation_id = "learnpilot_experiment_local_bm25_okapi_v1_1"

    def __init__(self, chunks: Sequence[CorpusChunk]):
        self.chunks = tuple(chunks)
        self.tokenized = tuple(tuple(analyze_lexical(item.raw_text)) for item in self.chunks)
        self.doc_len = tuple(len(tokens) for tokens in self.tokenized)
        self.avgdl = sum(self.doc_len) / len(self.doc_len)
        frequencies: Counter[str] = Counter()
        self.term_frequencies: list[Counter[str]] = []
        for tokens in self.tokenized:
            term_frequency = Counter(tokens)
            self.term_frequencies.append(term_frequency)
            frequencies.update(term_frequency.keys())
        idf = {
            term: math.log(len(self.chunks) - frequency + 0.5)
            - math.log(frequency + 0.5)
            for term, frequency in frequencies.items()
        }
        average_idf = sum(idf.values()) / len(idf) if idf else 0.0
        epsilon_floor = BM25_EPSILON * average_idf
        self.idf = {
            term: epsilon_floor if value < 0 else value for term, value in idf.items()
        }
        self.average_idf = average_idf

    def score(self, query: str) -> list[float]:
        query_tokens = analyze_lexical(query)
        scores: list[float] = []
        for term_frequency, doc_len in zip(self.term_frequencies, self.doc_len, strict=True):
            score = 0.0
            length_normalization = BM25_K1 * (
                1.0 - BM25_B + BM25_B * doc_len / self.avgdl
            )
            for term in query_tokens:
                frequency = term_frequency.get(term, 0)
                if frequency:
                    score += self.idf.get(term, 0.0) * (
                        frequency * (BM25_K1 + 1.0)
                        / (frequency + length_normalization)
                    )
            scores.append(score)
        return scores

    def retrieve(self, query: str, *, arm: Arm, limit: int = RAW_BRANCH_LIMIT) -> list[Candidate]:
        if limit != RAW_BRANCH_LIMIT:
            raise ContractViolation(f"BM25 depth must remain 18, got {limit}")
        scores = self.score(query)
        ordered = sorted(
            zip(self.chunks, scores, strict=True),
            key=lambda item: (-item[1], item[0].identity),
        )[:limit]
        candidates: list[Candidate] = []
        for rank, (chunk, score) in enumerate(ordered, start=1):
            candidate = Candidate.from_chunk(chunk, arm)
            candidate.bm25_score = float(score)
            candidate.bm25_rank = rank
            candidates.append(candidate)
        return candidates


def _merge_candidate(existing: Candidate, incoming: Candidate) -> None:
    immutable = (
        "document_id",
        "chunk_index",
        "content_hash",
        "filename",
        "page_number",
        "section_title",
        "raw_text",
        "material_id",
        "chunk_id",
        "evidence_ids",
    )
    for name in immutable:
        if getattr(existing, name) != getattr(incoming, name):
            raise ContractViolation(f"identity collision for {existing.identity}: {name}")
    for score_name, rank_name in (("dense_score", "dense_rank"), ("bm25_score", "bm25_rank")):
        incoming_rank = getattr(incoming, rank_name)
        if incoming_rank is None:
            continue
        if getattr(existing, rank_name) is not None:
            raise ContractViolation(
                f"duplicate {rank_name.removesuffix('_rank')} branch observation: {existing.identity}"
            )
        setattr(existing, score_name, getattr(incoming, score_name))
        setattr(existing, rank_name, incoming_rank)


def build_candidate_pool(
    *,
    arm: Arm,
    dense_candidates: Sequence[Candidate],
    bm25_candidates: Sequence[Candidate] = (),
) -> list[Candidate]:
    if len(dense_candidates) > RAW_BRANCH_LIMIT or len(bm25_candidates) > RAW_BRANCH_LIMIT:
        raise ContractViolation("raw branch candidate cap exceeded")
    merged: dict[str, Candidate] = {}
    for candidate in (*dense_candidates, *bm25_candidates):
        incoming = replace(candidate, arm=arm)
        expected_identity = stable_candidate_identity(
            incoming.document_id, incoming.chunk_index, incoming.content_hash
        )
        if incoming.identity != expected_identity:
            raise ContractViolation(f"invalid stable candidate identity: {incoming.identity}")
        actual_hash = sha256(incoming.raw_text.encode("utf-8")).hexdigest()
        if actual_hash != incoming.content_hash:
            raise ContractViolation(f"candidate raw text hash mismatch: {incoming.identity}")
        existing = merged.get(incoming.identity)
        if existing is None:
            merged[incoming.identity] = incoming
        else:
            _merge_candidate(existing, incoming)
    if len(merged) > 36:
        raise ContractViolation(f"pre-fusion identity union exceeds 36: {len(merged)}")
    pool = sorted(merged.values(), key=lambda item: item.identity)
    for candidate in pool:
        candidate.branch_admitted_dense = (
            candidate.dense_rank is not None
            and candidate.dense_score is not None
            and candidate.dense_score >= DENSE_THRESHOLD
        )
        candidate.branch_admitted_bm25 = (
            candidate.bm25_rank is not None
            and 1 <= candidate.bm25_rank <= RAW_BRANCH_LIMIT
        )
        candidate.candidate_admitted = (
            candidate.branch_admitted_dense or candidate.branch_admitted_bm25
        )
        candidate.dense_fusion_rank = (
            candidate.dense_rank if candidate.branch_admitted_dense else None
        )
        candidate.bm25_fusion_rank = (
            candidate.bm25_rank if candidate.branch_admitted_bm25 else None
        )
        if not candidate.candidate_admitted:
            candidate.rejection_reason = (
                "dense_ineligible" if arm == "C" else "not_admitted"
            )
    return pool


def reciprocal_rank_fusion(pool: Sequence[Candidate]) -> list[Candidate]:
    admitted = [candidate for candidate in pool if candidate.candidate_admitted]
    for candidate in admitted:
        contribution_ranks = [
            rank
            for rank in (candidate.dense_fusion_rank, candidate.bm25_fusion_rank)
            if rank is not None
        ]
        if not contribution_ranks:
            raise ContractViolation(f"admitted candidate has no RRF contribution: {candidate.identity}")
        candidate.fusion_score = sum(
            1.0 / (RRF_CONSTANT + rank) for rank in contribution_ranks
        )
    null_last = RAW_BRANCH_LIMIT + 1
    ordered = sorted(
        admitted,
        key=lambda item: (
            -float(item.fusion_score),
            min(
                rank
                for rank in (item.dense_fusion_rank, item.bm25_fusion_rank)
                if rank is not None
            ),
            item.dense_fusion_rank if item.dense_fusion_rank is not None else null_last,
            item.bm25_fusion_rank if item.bm25_fusion_rank is not None else null_last,
            item.identity,
        ),
    )
    for rank, candidate in enumerate(ordered, start=1):
        candidate.fusion_rank = rank
        if rank > FUSED_LIMIT:
            candidate.rejection_reason = "fused_top18_cutoff"
    return ordered[:FUSED_LIMIT]


@dataclass(frozen=True, slots=True)
class PairTokens:
    query_token_ids: tuple[int, ...]
    chunk_token_ids: tuple[int, ...]
    truncated: bool
    total_tokens: int


def enforce_pair_token_budget(
    query_token_ids: Sequence[int],
    chunk_token_ids: Sequence[int],
    *,
    special_token_count: int,
    token_cap: int = RERANKER_TOKEN_CAP,
) -> PairTokens:
    if len(query_token_ids) + special_token_count > token_cap:
        raise ContractViolation("query alone exceeds reranker pair token cap")
    allowed_chunk_tokens = token_cap - len(query_token_ids) - special_token_count
    truncated_chunk = tuple(chunk_token_ids[:allowed_chunk_tokens])
    return PairTokens(
        query_token_ids=tuple(query_token_ids),
        chunk_token_ids=truncated_chunk,
        truncated=len(chunk_token_ids) > allowed_chunk_tokens,
        total_tokens=len(query_token_ids) + len(truncated_chunk) + special_token_count,
    )


@dataclass(frozen=True, slots=True)
class RerankObservation:
    raw_logit: float
    truncated: bool
    input_tokens: int


class RerankerAdapter(Protocol):
    model_id: str
    revision: str

    def score(self, query: str, candidates: Sequence[Candidate]) -> list[RerankObservation]: ...


def build_xlm_roberta_pair_feature(tokenizer: Any, pair: PairTokens) -> dict[str, list[int]]:
    """Assemble the exact XLM-R sequence without tokenizer-version helper APIs."""
    if tokenizer.num_special_tokens_to_add(pair=True) != 4:
        raise ContractViolation("reranker tokenizer pair template is not the frozen XLM-R template")
    bos_token_id = tokenizer.bos_token_id
    eos_token_id = tokenizer.eos_token_id
    if bos_token_id is None or eos_token_id is None:
        raise ContractViolation("reranker tokenizer is missing XLM-R boundary token ids")
    input_ids = [
        bos_token_id,
        *pair.query_token_ids,
        eos_token_id,
        eos_token_id,
        *pair.chunk_token_ids,
        eos_token_id,
    ]
    if len(input_ids) != pair.total_tokens or len(input_ids) > RERANKER_TOKEN_CAP:
        raise ContractViolation("reranker pair construction violated the token contract")
    return {"input_ids": input_ids, "attention_mask": [1] * len(input_ids)}


class HuggingFaceRerankerAdapter:
    model_id = RERANKER_MODEL_ID
    revision = RERANKER_REVISION

    def __init__(self, snapshot_path: Path, *, device: str = "cpu"):
        if snapshot_path.name != RERANKER_REVISION:
            raise ContractViolation(
                f"resolved reranker revision mismatch: {snapshot_path.name} != {RERANKER_REVISION}"
            )
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        started = perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(
            str(snapshot_path), local_files_only=True, trust_remote_code=False
        )
        self.model = AutoModelForSequenceClassification.from_pretrained(
            str(snapshot_path), local_files_only=True, trust_remote_code=False
        )
        self.model.to(device)
        self.model.eval()
        self.device = device
        self.snapshot_path = snapshot_path
        self.load_seconds = perf_counter() - started
        self.inference_calls = 0
        self.pair_count = 0

    def _feature(self, query: str, chunk: str) -> tuple[dict[str, Any], PairTokens]:
        query_ids = self.tokenizer.encode(query, add_special_tokens=False)
        chunk_ids = self.tokenizer.encode(chunk, add_special_tokens=False)
        pair = enforce_pair_token_budget(
            query_ids,
            chunk_ids,
            special_token_count=self.tokenizer.num_special_tokens_to_add(pair=True),
        )
        feature = build_xlm_roberta_pair_feature(self.tokenizer, pair)
        return feature, pair

    def score(self, query: str, candidates: Sequence[Candidate]) -> list[RerankObservation]:
        if len(candidates) > RAW_BRANCH_LIMIT:
            raise ContractViolation(f"reranker pair cap violated: {len(candidates)}")
        import torch

        features: list[dict[str, Any]] = []
        pairs: list[PairTokens] = []
        for candidate in candidates:
            feature, pair = self._feature(query, candidate.raw_text)
            features.append(feature)
            pairs.append(pair)
        if not features:
            return []
        batch = self.tokenizer.pad(features, padding=True, return_tensors="pt")
        batch = {key: value.to(self.device) for key, value in batch.items()}
        with torch.inference_mode():
            logits = self.model(**batch, return_dict=True).logits
        raw = logits.reshape(-1).detach().cpu().tolist()
        if len(raw) != len(candidates):
            raise ContractViolation(
                f"reranker returned {len(raw)} logits for {len(candidates)} pairs"
            )
        self.inference_calls += 1
        self.pair_count += len(candidates)
        return [
            RerankObservation(
                raw_logit=float(logit),
                truncated=pair.truncated,
                input_tokens=pair.total_tokens,
            )
            for logit, pair in zip(raw, pairs, strict=True)
        ]


def apply_reranker(
    *, query: str, candidates: Sequence[Candidate], reranker: RerankerAdapter
) -> list[Candidate]:
    if len(candidates) > RAW_BRANCH_LIMIT:
        raise ContractViolation(f"reranker input cap exceeded: {len(candidates)}")
    if any(not candidate.candidate_admitted for candidate in candidates):
        raise ContractViolation("non-admitted candidate reached reranker")
    observations = reranker.score(query, candidates)
    if len(observations) != len(candidates):
        raise ContractViolation("reranker observation count mismatch")
    for candidate, observation in zip(candidates, observations, strict=True):
        candidate.reranker_score = observation.raw_logit
        candidate.reranker_truncated = observation.truncated
        candidate.reranker_input_tokens = observation.input_tokens
    ordered = sorted(
        candidates,
        key=lambda item: (
            -float(item.reranker_score),
            item.fusion_rank if item.fusion_rank is not None else int(item.dense_rank),
            item.identity,
        ),
    )
    for rank, candidate in enumerate(ordered, start=1):
        candidate.reranker_rank = rank
    return ordered


def _substantial_overlap(left: str, right: str) -> bool:
    a = " ".join(left.split())
    b = " ".join(right.split())
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    max_width = min(240, len(a), len(b))
    for width in range(max_width, 59, -1):
        if a[-width:] == b[:width] or b[-width:] == a[:width]:
            return True
    return False


def govern_evidence(ordered_candidates: Sequence[Candidate]) -> list[Candidate]:
    """Apply the frozen production governance once for every experimental arm."""

    if any(not candidate.candidate_admitted for candidate in ordered_candidates):
        raise ContractViolation("evidence governance received a non-admitted candidate")
    unique: list[Candidate] = []
    for rank, candidate in enumerate(ordered_candidates, start=1):
        candidate.governance_input_rank = rank
        if any(
            prior.material_id == candidate.material_id
            and abs(prior.chunk_index - candidate.chunk_index) <= 1
            and _substantial_overlap(prior.raw_text, candidate.raw_text)
            for prior in unique
        ):
            candidate.rejection_reason = "overlap_dedup"
            continue
        unique.append(candidate)

    selected_before_context: list[Candidate] = []
    diversity_deferred: set[str] = set()
    counts: dict[int, int] = {}
    for candidate in unique:
        if counts.get(candidate.material_id, 0) >= PER_MATERIAL_CAP:
            diversity_deferred.add(candidate.identity)
            continue
        selected_before_context.append(candidate)
        counts[candidate.material_id] = counts.get(candidate.material_id, 0) + 1
        if len(selected_before_context) >= FINAL_TOP_K:
            break
    if len(selected_before_context) < FINAL_TOP_K:
        for candidate in unique:
            if candidate in selected_before_context:
                continue
            selected_before_context.append(candidate)
            if len(selected_before_context) >= FINAL_TOP_K:
                break

    selected_ids = {candidate.identity for candidate in selected_before_context}
    for candidate in unique:
        if candidate.identity in selected_ids:
            continue
        candidate.rejection_reason = (
            "diversity_deferred"
            if candidate.identity in diversity_deferred
            else "final_top_k"
        )

    selected: list[Candidate] = []
    context_chars = 0
    for candidate in selected_before_context:
        content = candidate.raw_text[:MAX_CHUNK_CHARS]
        remaining = MAX_CONTEXT_CHARS - context_chars
        if remaining <= 0:
            candidate.rejection_reason = "context_budget"
            continue
        content = content[:remaining]
        if not content.strip():
            candidate.rejection_reason = "empty_content"
            continue
        candidate.selected = True
        candidate.selected_text_chars = len(content)
        candidate.rejection_reason = None
        selected.append(candidate)
        context_chars += len(content)
    return selected


@dataclass(frozen=True, slots=True)
class ArmExecution:
    arm: Arm
    query: str
    pool: tuple[Candidate, ...]
    ordered_for_governance: tuple[Candidate, ...]
    selected: tuple[Candidate, ...]
    stage_latency_ms: dict[str, float]
    pair_count: int
    truncation_count: int


def execute_arm(
    *,
    arm: Arm,
    case_id: str,
    dense_adapter: DenseAdapter,
    bm25_index: FrozenBM25Index | None,
    reranker: RerankerAdapter | None,
) -> ArmExecution:
    if arm not in {"B", "C", "D"}:
        raise ContractViolation(f"Arm A execution is forbidden; unsupported arm: {arm}")
    total_started = perf_counter()
    dense_started = perf_counter()
    query, dense = dense_adapter.retrieve(case_id, arm=arm)
    dense_ms = (perf_counter() - dense_started) * 1000.0

    bm25: list[Candidate] = []
    bm25_ms = 0.0
    if arm in {"B", "D"}:
        if bm25_index is None:
            raise ContractViolation(f"Arm {arm} requires an isolated BM25 index")
        bm25_started = perf_counter()
        bm25 = bm25_index.retrieve(query, arm=arm)
        bm25_ms = (perf_counter() - bm25_started) * 1000.0

    fusion_started = perf_counter()
    pool = build_candidate_pool(
        arm=arm, dense_candidates=dense, bm25_candidates=bm25
    )
    if arm in {"B", "D"}:
        ordered = reciprocal_rank_fusion(pool)
    else:
        ordered = sorted(
            (candidate for candidate in pool if candidate.candidate_admitted),
            key=lambda item: (int(item.dense_rank), item.identity),
        )
    fusion_ms = (perf_counter() - fusion_started) * 1000.0

    reranker_ms = 0.0
    if arm in {"C", "D"}:
        if reranker is None:
            raise ContractViolation(f"Arm {arm} requires the frozen reranker")
        reranker_started = perf_counter()
        ordered = apply_reranker(query=query, candidates=ordered, reranker=reranker)
        reranker_ms = (perf_counter() - reranker_started) * 1000.0

    governance_started = perf_counter()
    selected = govern_evidence(ordered)
    governance_ms = (perf_counter() - governance_started) * 1000.0
    total_ms = (perf_counter() - total_started) * 1000.0
    pair_count = len(ordered) if arm in {"C", "D"} else 0
    truncation_count = sum(
        candidate.reranker_truncated is True for candidate in ordered
    )
    return ArmExecution(
        arm=arm,
        query=query,
        pool=tuple(pool),
        ordered_for_governance=tuple(ordered),
        selected=tuple(selected),
        stage_latency_ms={
            "dense_retrieval": round(dense_ms, 6),
            "bm25_retrieval": round(bm25_ms, 6),
            "union_fusion": round(fusion_ms, 6),
            "reranker_inference": round(reranker_ms, 6),
            "governance": round(governance_ms, 6),
            "total_retrieval_selection": round(total_ms, 6),
        },
        pair_count=pair_count,
        truncation_count=truncation_count,
    )


def group_coverage(
    groups: Sequence[dict[str, Any]], candidates: Sequence[Candidate] | Sequence[dict[str, Any]]
) -> dict[str, Any]:
    documents: set[str] = set()
    evidence: set[str] = set()
    for item in candidates:
        if isinstance(item, Candidate):
            documents.add(item.document_id)
            evidence.update(item.evidence_ids)
        else:
            document_id = item.get("document_id")
            if document_id:
                documents.add(document_id)
            evidence.update(item.get("evidence_ids", []))
    rows = []
    for group in groups:
        required = bool(group.get("required", False))
        document_match = bool(documents.intersection(group.get("any_of_document_ids", [])))
        anchor_match = bool(evidence.intersection(group.get("any_of_evidence_ids", [])))
        rows.append(
            {
                "evidence_group_id": group["evidence_group_id"],
                "required": required,
                "document_match": document_match,
                "anchor_match": anchor_match,
                "document_pass": (not required) or document_match,
                "anchor_pass": (not required) or anchor_match,
            }
        )
    required_rows = [row for row in rows if row["required"]]
    return {
        "groups": rows,
        "required_group_count": len(required_rows),
        "document_groups_covered": sum(row["document_pass"] for row in required_rows),
        "anchor_groups_covered": sum(row["anchor_pass"] for row in required_rows),
        "document_pass": all(row["document_pass"] for row in required_rows),
        "anchor_pass": all(row["anchor_pass"] for row in required_rows),
    }


def candidate_order(candidates: Sequence[Candidate]) -> list[str]:
    return [candidate.identity for candidate in candidates]
