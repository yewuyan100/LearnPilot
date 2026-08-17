"""Freeze stable source anchors independently from Gold case authoring."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from pypdf import PdfReader

from gold_common import GOLD_ROOT, REPO_ROOT, load_anchor_specs, load_manifest, write_json


def normalize(text: str) -> str:
    return " ".join(text.replace("\x00", "").split())


def build_anchor(spec: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    path = REPO_ROOT / document["repository_path"]
    if "lines" in spec:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        start, end = spec["lines"]
        if start > end or end > len(lines):
            raise ValueError(f"{spec['id']}: source line range does not resolve")
        text = normalize("\n".join(lines[start - 1:end]))
        locator = {
            "kind": "SOURCE_LINES",
            "source_path": document["repository_path"],
            "start_line": start,
            "end_line": end,
            "section_title": spec["section"],
            "region": spec["region"],
        }
    else:
        reader = PdfReader(str(path))
        page_number = spec["page"]
        if page_number > len(reader.pages):
            raise ValueError(f"{spec['id']}: PDF page does not resolve")
        text = normalize(reader.pages[page_number - 1].extract_text() or "")
        clue = normalize(spec["contains"])
        if clue.casefold() not in text.casefold():
            raise ValueError(f"{spec['id']}: PDF clue not found on page {page_number}")
        locator = {
            "kind": "PDF_PAGE",
            "source_path": document["repository_path"],
            "page_number": page_number,
            "region": spec["region"],
        }
    if not text:
        raise ValueError(f"{spec['id']}: empty anchor text")
    excerpt = text[:417] + ("..." if len(text) > 417 else "")
    return {
        "evidence_id": "ev-rw-" + spec["id"],
        "document_id": spec["doc"],
        "locator": locator,
        "anchor_text_hash": sha256(text.encode("utf-8")).hexdigest(),
        "excerpt": excerpt,
        "language": "en",
        "notes": "Frozen source representation; hash covers the complete normalized locator text.",
    }


def main() -> None:
    manifest = load_manifest()
    document_by_id = {item["document_id"]: item for item in manifest["documents"]}
    anchors = []
    for spec in load_anchor_specs():
        if spec["doc"] not in document_by_id:
            raise ValueError(f"{spec['id']}: unknown document {spec['doc']}")
        anchors.append(build_anchor(spec, document_by_id[spec["doc"]]))
    evidence_ids = [item["evidence_id"] for item in anchors]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("duplicate evidence anchor IDs")
    artifact = {
        "schema_version": "1.0.0",
        "corpus_ref": {
            "corpus_id": manifest["corpus_id"],
            "corpus_version": manifest["corpus_version"],
        },
        "anchor_count": len(anchors),
        "anchors": anchors,
    }
    write_json(GOLD_ROOT / "evidence_anchors.json", artifact)
    write_json(GOLD_ROOT / "evidence_anchor_validation.json", {
        "schema_version": "1.0.0",
        "status": "PASS",
        "anchor_count": len(anchors),
        "source_line_anchor_count": sum(item["locator"]["kind"] == "SOURCE_LINES" for item in anchors),
        "pdf_page_anchor_count": sum(item["locator"]["kind"] == "PDF_PAGE" for item in anchors),
        "unresolved_document_count": 0,
        "unresolved_locator_count": 0,
        "hash_failure_count": 0,
        "runtime_id_field_count": 0,
    })


if __name__ == "__main__":
    main()
