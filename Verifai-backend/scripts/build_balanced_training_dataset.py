"""Build a balanced, leakage-safe cross-lingual dataset for VeriFai text detection."""

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
    parser.add_argument("--prior-corpus", type=Path, default=None, help="Existing maximized jsonl corpus to merge with")
    parser.add_argument("--add-tagalog-ai", type=int, default=150)
    parser.add_argument("--add-taglish-ai", type=int, default=250)
    parser.add_argument("--add-english-ai", type=int, default=250)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def load_labeled(path: Path) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            text = normalize_text(row.get("text"))
            label = normalize_text(row.get("label")).casefold()
            original_id = normalize_text(row.get("original_id") or row.get("id"))
            language = normalize_text(row.get("language")).casefold() or "unknown"
            domain = normalize_text(row.get("content_type")).casefold() or "unknown"
            source = (
                normalize_text(row.get("ai_model")).casefold()
                if label == "ai"
                else "human"
            ) or "unknown"
            if len(text) < 20 or label not in {"human", "ai"} or not original_id:
                continue
            rows.append(
                {
                    "text": text,
                    "label": label,
                    "group_id": original_id,
                    "language": language,
                    "domain": domain,
                    "source": source,
                    "origin": "labeled",
                }
            )
    return rows


def load_prior_corpus(path: Path) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            text = normalize_text(row.get("text"))
            label = normalize_text(row.get("label")).casefold()
            group_id = normalize_text(row.get("group_id") or row.get("prompt"))
            language = normalize_text(row.get("language")).casefold() or "unknown"
            domain = normalize_text(row.get("domain") or row.get("category")).casefold() or "essay"
            source = normalize_text(row.get("source") or row.get("model")).casefold() or "unknown"
            if len(text) < 20 or label not in {"human", "ai"} or not group_id:
                continue
            rows.append(
                {
                    "text": text,
                    "label": label,
                    "group_id": group_id,
                    "language": language,
                    "domain": domain,
                    "source": source,
                    "origin": "prior_corpus",
                }
            )
    return rows


def load_stratified_ai(
    path: Path,
    target_counts: dict[str, int],
    seed: int,
    existing_texts: set[str],
) -> list[dict[str, str | int]]:
    by_lang_model: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    seen_in_corpus = set(existing_texts)

    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            text = normalize_text(row.get("text"))
            prompt = normalize_text(row.get("prompt"))
            model = normalize_text(row.get("model")).casefold()
            lang = normalize_text(row.get("language")).casefold()
            category = normalize_text(row.get("category")).casefold()
            if len(text) < 20 or not prompt or not model or not lang:
                continue
            text_key = hashlib.sha256(text.casefold().encode()).hexdigest()
            if text_key in seen_in_corpus:
                continue
            seen_in_corpus.add(text_key)
            by_lang_model[(lang, model)].append(
                {
                    "text": text,
                    "label": "ai",
                    "group_id": prompt,
                    "language": lang,
                    "domain": category or "essay",
                    "source": model,
                    "origin": "ai_corpus",
                }
            )

    for lang, total_needed in target_counts.items():
        active_models = sorted({m for (l, m) in by_lang_model if l == lang})
        if not active_models:
            continue
        per_model = total_needed // len(active_models)
        remainder = total_needed % len(active_models)
        for i, m in enumerate(active_models):
            count = per_model + (1 if i < remainder else 0)
            pool = by_lang_model.get((lang, m), [])
            rng.shuffle(pool)
            selected.extend(pool[:count])

    return selected


def assign_splits(rows: list[dict[str, str | int]], seed: int) -> None:
    groups: dict[str, list[dict[str, str | int]]] = defaultdict(list)
    for row in rows:
        groups[str(row["group_id"])].append(row)
    ordered = sorted(groups)
    if len(ordered) < 20:
        raise ValueError("dataset needs at least 20 independent groups")
    random.Random(seed).shuffle(ordered)
    ordered.sort(key=lambda group_id: len(groups[group_id]), reverse=True)
    assigned_rows = Counter({split: 0 for split in SPLIT_NAMES})
    assignments: dict[str, str] = {}
    for group_id in ordered:
        split = min(SPLIT_NAMES, key=lambda name: assigned_rows[name] / SPLIT_RATIOS[name])
        assignments[group_id] = split
        assigned_rows[split] += len(groups[group_id])

    for row in rows:
        row["split"] = assignments[str(row["group_id"])]


def deduplicate(rows: list[dict[str, str | int]]) -> list[dict[str, str | int]]:
    unique: dict[str, dict[str, str | int]] = {}
    for row in rows:
        text_key = hashlib.sha256(str(row["text"]).casefold().encode()).hexdigest()
        existing = unique.get(text_key)
        if existing is not None and existing["label"] != row["label"]:
            continue
        unique.setdefault(text_key, row)
    return list(unique.values())


def main() -> None:
    args = parse_args()
    labeled_rows = load_labeled(args.labeled_corpus)
    prior_rows = load_prior_corpus(args.prior_corpus) if args.prior_corpus and args.prior_corpus.exists() else []

    existing_texts = {
        hashlib.sha256(str(r["text"]).casefold().encode()).hexdigest()
        for r in (labeled_rows + prior_rows)
    }

    target_counts = {
        "tagalog": args.add_tagalog_ai,
        "taglish": args.add_taglish_ai,
        "english": args.add_english_ai,
    }
    ai_rows = load_stratified_ai(args.ai_corpus, target_counts, args.seed, existing_texts)

    all_rows = deduplicate(labeled_rows + prior_rows + ai_rows)
    assign_splits(all_rows, args.seed)

    counts_by_split = {
        split: Counter((str(row["language"]), str(row["label"])) for row in all_rows if row["split"] == split)
        for split in SPLIT_NAMES
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in all_rows:
            output = {
                key: row[key]
                for key in (
                    "text",
                    "label",
                    "group_id",
                    "split",
                    "language",
                    "domain",
                    "source",
                )
            }
            handle.write(json.dumps(output, ensure_ascii=False) + "\n")

    print("=== Dataset Generation Complete ===")
    print(f"Output: {args.output}")
    print(f"Total samples: {len(all_rows)}")
    overall_labels = Counter(r["label"] for r in all_rows)
    overall_langs = Counter(r["language"] for r in all_rows)
    print(f"Labels: {dict(overall_labels)}")
    print(f"Languages: {dict(overall_langs)}")
    print("\nBreakdown by Split & Language x Label:")
    for split in SPLIT_NAMES:
        print(f"--- {split.upper()} ---")
        for k, v in sorted(counts_by_split[split].items()):
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
