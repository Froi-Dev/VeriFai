"""Build a leakage-safe human-versus-AI training dataset from VeriFai's local corpora."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SPLIT_NAMES = ("train", "validation", "calibration", "test")
SPLIT_RATIOS = {"train": 0.65, "validation": 0.10, "calibration": 0.10, "test": 0.15}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ai-corpus", type=Path, required=True)
    parser.add_argument("--labeled-corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def load_current_ai(path: Path) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    with path.open(encoding="utf-8") as handle:
        for row_number, line in enumerate(handle, start=1):
            row = json.loads(line)
            text = normalize_text(row.get("text"))
            prompt = normalize_text(row.get("prompt"))
            source = normalize_text(row.get("model")).casefold()
            if len(text) < 20 or not prompt or not source:
                raise ValueError(f"AI corpus row {row_number} is missing text, prompt, or model")
            rows.append(
                {
                    "text": text,
                    "label": "ai",
                    "group_id": f"current-prompt:{prompt.casefold()}",
                    "language": normalize_text(row.get("language")).casefold() or "unknown",
                    "domain": normalize_text(row.get("category")).casefold() or "unknown",
                    "source": source,
                    "origin": "current",
                }
            )
    return rows


def load_labeled(path: Path) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            text = normalize_text(row.get("text"))
            label = normalize_text(row.get("label")).casefold()
            original_id = normalize_text(row.get("original_id") or row.get("id"))
            if len(text) < 20 or label not in {"human", "ai"} or not original_id:
                raise ValueError(f"labeled corpus row {row_number} has invalid text, label, or ID")
            rows.append(
                {
                    "text": text,
                    "label": label,
                    "group_id": f"labeled:{original_id}",
                    "language": normalize_text(row.get("language")).casefold() or "unknown",
                    "domain": normalize_text(row.get("content_type")).casefold() or "unknown",
                    "source": (
                        normalize_text(row.get("ai_model")).casefold()
                        if label == "ai"
                        else "human"
                    )
                    or "unknown",
                    "origin": "labeled",
                }
            )
    return rows


def assign_splits(rows: list[dict[str, str | int]], seed: int) -> None:
    groups: dict[tuple[str, str], list[dict[str, str | int]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["label"]), str(row["group_id"]))].append(row)

    grouped_by_label: dict[str, list[str]] = defaultdict(list)
    for label, group_id in groups:
        grouped_by_label[label].append(group_id)
    assignments: dict[tuple[str, str], str] = {}
    for label, group_ids in grouped_by_label.items():
        ordered = sorted(group_ids)
        if len(ordered) < 20:
            raise ValueError(f"{label} class needs at least 20 independent groups")
        random.Random(f"{seed}:{label}").shuffle(ordered)
        ordered.sort(key=lambda group_id: len(groups[(label, group_id)]), reverse=True)
        assigned_rows = Counter({split: 0 for split in SPLIT_NAMES})
        for group_id in ordered:
            split = min(
                SPLIT_NAMES,
                key=lambda name: assigned_rows[name] / SPLIT_RATIOS[name],
            )
            assignments[(label, group_id)] = split
            assigned_rows[split] += len(groups[(label, group_id)])
    for row in rows:
        row["split"] = assignments[(str(row["label"]), str(row["group_id"]))]


def deduplicate(rows: list[dict[str, str | int]]) -> list[dict[str, str | int]]:
    unique: dict[str, dict[str, str | int]] = {}
    for row in rows:
        text_key = hashlib.sha256(str(row["text"]).casefold().encode()).hexdigest()
        existing = unique.get(text_key)
        if existing is not None and existing["label"] != row["label"]:
            raise ValueError("identical text has conflicting human and AI labels")
        unique.setdefault(text_key, row)
    return list(unique.values())


def main() -> None:
    args = parse_args()
    rows = deduplicate(load_current_ai(args.ai_corpus) + load_labeled(args.labeled_corpus))
    assign_splits(rows, args.seed)
    counts = {
        split: Counter(str(row["label"]) for row in rows if row["split"] == split)
        for split in SPLIT_NAMES
    }
    if any(set(counts[split]) != {"human", "ai"} for split in SPLIT_NAMES):
        raise ValueError("every split must contain human and AI samples")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            output = {key: row[key] for key in ("text", "label", "group_id", "split", "language", "domain", "source")}
            handle.write(json.dumps(output, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "rows": len(rows),
                "split_counts": {split: dict(counts[split]) for split in SPLIT_NAMES},
                "current_ai_groups": len({row["group_id"] for row in rows if row["origin"] == "current"}),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
