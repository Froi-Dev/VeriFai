"""Audit detector corpora without treating labels as proof of authorship."""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def fingerprint(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).casefold().encode()).hexdigest()


def audit(path: Path, synthetic: set[str]) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = (list(csv.DictReader(handle)) if path.suffix == ".csv"
                else [json.loads(line) for line in handle if line.strip()])
    groups = defaultdict(set)
    text_labels = defaultdict(set)
    for row in rows:
        groups[row.get("group_id") or row.get("original_id", "")].add(row.get("split", ""))
        text_labels[fingerprint(row.get("text", ""))].add(row.get("label", ""))
    matches = [row for row in rows if fingerprint(row.get("text", "")) in synthetic]
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": len(rows),
        "labels": dict(Counter(row.get("label", "missing") for row in rows)),
        "sources": dict(Counter(row.get("source") or row.get("ai_model") or row.get("model", "missing") for row in rows)),
        "languages": dict(Counter(row.get("language", "missing") for row in rows)),
        "explicit_split_group_conflicts": sum(len(splits) > 1 for splits in groups.values()),
        "duplicate_texts": len(rows) - len(text_labels),
        "conflicting_text_labels": sum(len(labels) > 1 for labels in text_labels.values()),
        "known_synthetic_generator_matches": len(matches),
        "known_synthetic_matches_labeled_human": sum(row.get("label") == "human" for row in matches),
        "provenance_status": "Authorship requires external verification; metadata alone is insufficient.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", type=Path, nargs="+")
    parser.add_argument("--generator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    synthetic = set()
    # Inspect literals without executing the generator or its imports.
    tree = ast.parse(args.generator.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in {"AI_SAMPLES", "HUMAN_SAMPLES"}:
                synthetic.update(fingerprint(row["text"]) for row in ast.literal_eval(node.value))
    report = {"corpora": [audit(path, synthetic) for path in args.paths]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
