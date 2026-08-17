"""Validate Real-world Corpus V1 and derive deterministic shape/audit artifacts."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from app.services.material_processing.chunking import chunk_sections  # noqa: E402
from app.services.material_processing.cleaning import clean_text  # noqa: E402
from app.services.material_processing.parsers import parser_for  # noqa: E402
from app.services.material_processing.types import ParsedSection  # noqa: E402


REQUIRED_FIELDS = {
    "document_id", "title", "topic_cluster", "source_format", "repository_path",
    "upstream_project", "upstream_repository", "upstream_commit_sha",
    "upstream_path_or_source", "retrieved_at", "license", "license_source",
    "license_repository_path", "license_sha256", "attribution", "source_sha256",
    "corpus_sha256", "transformation", "language", "notes",
}
TOPICS = {"rag_retrieval", "agent_engineering", "ai_app_backend", "evaluation_reliability"}
FORMATS = {"md", "txt", "pdf"}
LICENSES = {"MIT", "Apache-2.0", "CC-BY-4.0"}
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
ID_PATTERN = re.compile(r"^rw-[a-z0-9-]+$")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def normalized_shingles(text: str, width: int = 5) -> set[tuple[str, ...]]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {tuple(tokens[index:index + width]) for index in range(max(0, len(tokens) - width + 1))}


def parsed_text_and_chunks(document: dict[str, Any], settings: Settings) -> tuple[str, list[Any], int | None]:
    path = ROOT / document["repository_path"]
    parsed = parser_for(path, document["source_format"]).parse(path)
    sections = [
        ParsedSection(
            text=clean_text(section.text, repair_pdf_lines=parsed.parser_type == "pdf"),
            source_order=section.source_order,
            page_number=section.page_number,
            section_title=section.section_title,
        )
        for section in parsed.sections
    ]
    sections = [section for section in sections if section.text]
    chunks = chunk_sections(
        sections,
        chunk_size=settings.material_chunk_size,
        overlap=settings.material_chunk_overlap,
        min_chunk_size=settings.material_min_chunk_size,
    )
    return "\n".join(section.text for section in sections), chunks, parsed.page_count


def main() -> int:
    manifest = json.loads((HERE / "corpus_manifest.json").read_text(encoding="utf-8"))
    acquisition_lock = json.loads((HERE / "acquisition_lock.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    documents = manifest.get("documents", [])
    if manifest.get("document_count") != len(documents) or not 8 <= len(documents) <= 15:
        errors.append("document_count must match an 8-15 document corpus")
    ids = [item.get("document_id") for item in documents]
    paths = [item.get("repository_path") for item in documents]
    if len(ids) != len(set(ids)):
        errors.append("duplicate document_id")
    if len(paths) != len(set(paths)):
        errors.append("duplicate repository_path")
    if any(not isinstance(item, str) or not ID_PATTERN.fullmatch(item) for item in ids):
        errors.append("invalid document_id")

    format_counts = Counter(item.get("source_format") for item in documents)
    topic_counts = Counter(item.get("topic_cluster") for item in documents)
    if set(format_counts) != FORMATS or format_counts["pdf"] != 2 or not 1 <= format_counts["txt"] <= 2:
        errors.append("format plan must include exactly 2 PDF, 1-2 TXT, and Markdown as the majority")
    if format_counts["md"] <= sum(format_counts.values()) / 2:
        errors.append("Markdown must be the majority format")
    if set(topic_counts) != TOPICS:
        errors.append("all four required topic clusters must be present")
    if format_counts != Counter(manifest.get("format_plan", {})):
        errors.append("format_plan does not match documents")
    if topic_counts != Counter(manifest.get("topic_plan", {})):
        errors.append("topic_plan does not match documents")
    manifested_names = {Path(item).name for item in paths if isinstance(item, str)}
    actual_names = {path.name for path in (HERE / "corpus").iterdir() if path.is_file()}
    if actual_names != manifested_names:
        errors.append(f"canonical corpus has unmanifested or missing files: {sorted(actual_names ^ manifested_names)}")

    locked_repositories = {item["project"]:item for item in acquisition_lock.get("repositories", [])}
    document_projects = {item.get("upstream_project") for item in documents}
    if set(locked_repositories) != document_projects:
        errors.append("acquisition lock projects do not match manifest projects")
    frozen_licenses = {item["project"]:item for item in manifest.get("licenses", [])}
    if set(frozen_licenses) != document_projects:
        errors.append("frozen license projects do not match manifest projects")
    for project, record in frozen_licenses.items():
        license_path = ROOT / record["repository_path"]
        if not license_path.is_file() or file_hash(license_path) != record["sha256"]:
            errors.append(f"{project}: manifest license record is missing or has a hash mismatch")
        notice = record.get("notice")
        if notice:
            notice_path = ROOT / notice["repository_path"]
            if not notice_path.is_file() or file_hash(notice_path) != notice["sha256"]:
                errors.append(f"{project}: NOTICE is missing or has a hash mismatch")

    settings = Settings(_env_file=None)
    shape: list[dict[str, Any]] = []
    text_by_id: dict[str, str] = {}
    corpus_hash_counts: Counter[str] = Counter()
    license_audit: list[dict[str, Any]] = []
    for document in documents:
        missing = REQUIRED_FIELDS.difference(document)
        if missing:
            errors.append(f"{document.get('document_id')}: missing {sorted(missing)}")
            continue
        document_id = document["document_id"]
        if document["topic_cluster"] not in TOPICS or document["source_format"] not in FORMATS:
            errors.append(f"{document_id}: unsupported topic or format")
        if document["license"] not in LICENSES:
            errors.append(f"{document_id}: unapproved license")
        if not HEX_40.fullmatch(document["upstream_commit_sha"]):
            errors.append(f"{document_id}: commit is not a full SHA")
        if document["upstream_commit_sha"] not in document["license_source"]:
            errors.append(f"{document_id}: license source is not commit-pinned")
        locked = locked_repositories.get(document["upstream_project"], {})
        if locked.get("repository") != document["upstream_repository"] or locked.get("commit_sha") != document["upstream_commit_sha"]:
            errors.append(f"{document_id}: acquisition lock mismatch")
        if not HEX_64.fullmatch(document["source_sha256"]) or not HEX_64.fullmatch(document["corpus_sha256"]):
            errors.append(f"{document_id}: invalid SHA-256")
        path = ROOT / document["repository_path"]
        expected_prefix = (HERE / "corpus").resolve()
        if expected_prefix not in path.resolve().parents:
            errors.append(f"{document_id}: repository path escapes the canonical corpus directory")
        if not path.is_file():
            errors.append(f"{document_id}: corpus file is missing")
            continue
        actual_hash = file_hash(path)
        corpus_hash_counts[actual_hash] += 1
        if actual_hash != document["corpus_sha256"]:
            errors.append(f"{document_id}: corpus SHA-256 mismatch")
        if path.suffix.lower() != "." + document["source_format"]:
            errors.append(f"{document_id}: format and extension disagree")
        if document["source_format"] != "pdf" and document["corpus_sha256"] != document["source_sha256"]:
            errors.append(f"{document_id}: byte-copy representation changed upstream content")
        if document["source_format"] == "pdf" and document["transformation"].get("method") is None:
            errors.append(f"{document_id}: PDF transformation is not explained")
        if document["transformation"].get("content_rewritten") is not False:
            errors.append(f"{document_id}: transformation must assert content_rewritten=false")
        license_path = ROOT / document["license_repository_path"]
        license_valid = license_path.is_file() and file_hash(license_path) == document["license_sha256"]
        if not license_valid:
            errors.append(f"{document_id}: frozen license missing or hash mismatch")
        text, chunks, page_count = parsed_text_and_chunks(document, settings)
        if not chunks:
            errors.append(f"{document_id}: canonical parser/chunker produced no chunks")
        text_by_id[document_id] = text
        shape.append({
            "document_id": document_id,
            "topic_cluster": document["topic_cluster"],
            "source_format": document["source_format"],
            "file_bytes": path.stat().st_size,
            "parsed_char_count": len(text),
            "projected_chunk_count": len(chunks),
            "projected_chunk_chars_min": min((item.char_count for item in chunks), default=0),
            "projected_chunk_chars_max": max((item.char_count for item in chunks), default=0),
            "projected_chunk_chars_mean": round(sum(item.char_count for item in chunks) / len(chunks), 2) if chunks else 0,
            "page_count": page_count,
        })
        license_audit.append({
            "document_id": document_id,
            "project": document["upstream_project"],
            "commit_sha": document["upstream_commit_sha"],
            "spdx_identifier": document["license"],
            "license_source": document["license_source"],
            "frozen_license_path": document["license_repository_path"],
            "frozen_license_sha256": document["license_sha256"],
            "verified": license_valid,
        })

    pairwise: list[dict[str, Any]] = []
    shingles = {document_id: normalized_shingles(text) for document_id, text in text_by_id.items()}
    for index, left in enumerate(ids):
        for right in ids[index + 1:]:
            left_set, right_set = shingles[left], shingles[right]
            intersection = len(left_set & right_set)
            union = len(left_set | right_set)
            smaller = min(len(left_set), len(right_set))
            pairwise.append({
                "left": left,
                "right": right,
                "jaccard_5gram": round(intersection / union, 6) if union else 0,
                "smaller_document_containment": round(intersection / smaller, 6) if smaller else 0,
            })
    pairwise.sort(key=lambda item: (item["jaccard_5gram"], item["smaller_document_containment"]), reverse=True)
    near_duplicates = [item for item in pairwise if item["jaccard_5gram"] >= 0.80 or item["smaller_document_containment"] >= 0.92]
    exact_duplicate_hashes = sorted(value for value, count in corpus_hash_counts.items() if count > 1)
    if exact_duplicate_hashes:
        errors.append("exact duplicate corpus files detected")
    if near_duplicates:
        errors.append("near-duplicate corpus documents detected")

    total_chunks = sum(item["projected_chunk_count"] for item in shape)
    if not 150 <= total_chunks <= 600:
        errors.append(f"projected chunk count {total_chunks} is outside the accepted 150-600 range")
    projected_topic_counts = {
        topic: sum(item["projected_chunk_count"] for item in shape if item["topic_cluster"] == topic)
        for topic in TOPICS
    }
    projected_topic_shares = {
        topic: count / total_chunks if total_chunks else 0
        for topic, count in projected_topic_counts.items()
    }
    if any(share < 0.10 for share in projected_topic_shares.values()) or max(projected_topic_shares.values(), default=0) > 0.45:
        errors.append(f"projected topic shares are imbalanced: {projected_topic_shares}")
    if any(HERE.glob("*gold*")) or any((HERE / "corpus").glob("*gold*")):
        errors.append("Gold questions/cases are outside this corpus task")

    chunk_projection = {
        "schema_version":"1.0.0",
        "canonical_chunking": {
            "chunk_size": settings.material_chunk_size,
            "overlap": settings.material_chunk_overlap,
            "min_chunk_size": settings.material_min_chunk_size,
        },
        "total_projected_chunks": total_chunks,
        "by_topic": dict(sorted(projected_topic_counts.items())),
        "topic_shares": {topic:round(share, 6) for topic, share in sorted(projected_topic_shares.items())},
        "by_format": dict(sorted(Counter({fmt: sum(item["projected_chunk_count"] for item in shape if item["source_format"] == fmt) for fmt in FORMATS}).items())),
        "documents": shape,
    }
    duplicate_analysis = {
        "schema_version":"1.0.0",
        "algorithm":"normalized lowercase alphanumeric token 5-gram set similarity",
        "near_duplicate_threshold":"jaccard >= 0.80 OR smaller-document containment >= 0.92",
        "exact_duplicate_hashes": exact_duplicate_hashes,
        "near_duplicates": near_duplicates,
        "top_pairs": pairwise[:15],
    }
    license_report = {
        "schema_version":"1.0.0",
        "allowed_licenses": sorted(LICENSES),
        "all_verified": all(item["verified"] for item in license_audit),
        "frozen_license_records":sorted(frozen_licenses.values(), key=lambda item: item["project"]),
        "documents": license_audit,
    }
    validation = {
        "status":"passed" if not errors else "failed",
        "errors":errors,
        "document_count":len(documents),
        "unique_document_ids":len(set(ids)),
        "format_counts":dict(sorted(format_counts.items())),
        "topic_counts":dict(sorted(topic_counts.items())),
        "projected_chunk_count":total_chunks,
        "exact_duplicates":len(exact_duplicate_hashes),
        "near_duplicates":len(near_duplicates),
        "all_licenses_verified":license_report["all_verified"],
    }
    write_json(HERE / "chunk_projection.json", chunk_projection)
    write_json(HERE / "duplicate_overlap_analysis.json", duplicate_analysis)
    write_json(HERE / "license_provenance_audit.json", license_report)
    write_json(HERE / "validation_report.json", validation)
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
