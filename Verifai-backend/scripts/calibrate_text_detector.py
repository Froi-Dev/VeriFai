"""Calibrate an existing VeriFai text model and audit it on an untouched split."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from transformers import AutoModelForSequenceClassification, AutoTokenizer

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from train_text_detector import (  # noqa: E402
    LABELS,
    Sample,
    predict_document_log_odds,
    resolve_device,
    seed_everything,
    write_json,
)

from app.ContentDetector.text_detector import (  # noqa: E402
    TEXT_AGGREGATION_VERSION,
    resolve_ai_label_id,
    text_deployment_fingerprint,
)
from app.ContentDetector.text_quality import (  # noqa: E402
    choose_review_thresholds,
    evaluate_ai_sources,
    evaluate_probabilities,
    evaluate_subgroups,
    fit_temperature,
    probabilities_from_log_odds,
)

logger = logging.getLogger("calibrate_text_detector")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--calibration-ratio", type=float, default=0.5)
    parser.add_argument("--target-precision", type=float, default=0.90)
    parser.add_argument("--minimum-confident-predictions", type=int)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--stride", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 0.2 <= args.calibration_ratio <= 0.8:
        raise ValueError("calibration ratio must be between 0.2 and 0.8")
    if args.model.resolve() != args.output_dir.resolve():
        raise ValueError(
            "output-dir must be the model directory; copy the model first to preserve an old export"
        )
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    seed_everything(args.seed)
    samples = load_audit_samples(args.dataset)
    calibration_samples, audit_samples = stratified_group_split(
        samples, ratio=args.calibration_ratio, seed=args.seed
    )
    validate_partition(calibration_samples, audit_samples)
    logger.info(
        "calibration=%d audit=%d (the audit partition remains untouched until thresholds freeze)",
        len(calibration_samples),
        len(audit_samples),
    )

    device = resolve_device(args.device)
    tokenizer = AutoTokenizer.from_pretrained(
        args.model, local_files_only=True, use_fast=True, trust_remote_code=False
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model, local_files_only=True, trust_remote_code=False
    ).to(device)
    ai_label_id = resolve_ai_label_id(model.config.id2label, None)
    model.eval()

    calibration_log_odds = predict_document_log_odds(
        model,
        tokenizer,
        calibration_samples,
        device=device,
        max_length=args.max_length,
        stride=args.stride,
        batch_size=args.batch_size,
        ai_label_id=ai_label_id,
    )
    calibration_labels = [sample.label for sample in calibration_samples]
    temperature = fit_temperature(calibration_log_odds, calibration_labels)
    calibration_probabilities = probabilities_from_log_odds(
        calibration_log_odds, temperature
    )
    human_threshold, ai_threshold = choose_review_thresholds(
        calibration_probabilities,
        calibration_labels,
        target_precision=args.target_precision,
        min_predictions=args.minimum_confident_predictions,
    )
    calibration_metrics = evaluate_probabilities(
        calibration_probabilities,
        calibration_labels,
        human_threshold=human_threshold,
        ai_threshold=ai_threshold,
    )

    audit_log_odds = predict_document_log_odds(
        model,
        tokenizer,
        audit_samples,
        device=device,
        max_length=args.max_length,
        stride=args.stride,
        batch_size=args.batch_size,
        ai_label_id=ai_label_id,
    )
    audit_labels = [sample.label for sample in audit_samples]
    audit_probabilities = probabilities_from_log_odds(audit_log_odds, temperature)
    audit_metrics = evaluate_probabilities(
        audit_probabilities,
        audit_labels,
        human_threshold=human_threshold,
        ai_threshold=ai_threshold,
    )

    artifact = {
        "schema_version": 2,
        "aggregation_version": TEXT_AGGREGATION_VERSION,
        "max_length": args.max_length,
        "stride": args.stride,
        "ai_label_id": ai_label_id,
        "deployment_fingerprint": text_deployment_fingerprint(args.model),
        "temperature": temperature,
        "human_max_ai_probability": human_threshold,
        "ai_min_ai_probability": ai_threshold,
        "validation_samples": len(calibration_samples),
        "target_class_precision": args.target_precision,
    }
    report = {
        "schema_version": 1,
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "model_config_sha256": hashlib.sha256(
            (args.model / "config.json").read_bytes()
        ).hexdigest(),
        "partition": {
            "seed": args.seed,
            "calibration_samples": len(calibration_samples),
            "audit_samples": len(audit_samples),
        },
        "calibration_artifact": artifact,
        "calibration_metrics": calibration_metrics,
        "audit_metrics": audit_metrics,
        "audit_subgroups": subgroup_report(
            audit_probabilities,
            audit_samples,
            human_threshold=human_threshold,
            ai_threshold=ai_threshold,
        ),
    }
    write_json(args.output_dir / "text_calibration.json", artifact)
    write_json(args.output_dir / "calibration_audit_report.json", report)
    logger.info(
        "complete temperature=%.4f thresholds=[%.4f, %.4f] audit_balanced_accuracy=%.4f "
        "audit_coverage=%.4f",
        temperature,
        human_threshold,
        ai_threshold,
        audit_metrics["balanced_accuracy"],
        audit_metrics["review_policy"]["coverage"],
    )


def load_audit_samples(path: Path) -> list[Sample]:
    if path.suffix.casefold() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    elif path.suffix.casefold() == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    else:
        raise ValueError("dataset must be CSV or JSONL")

    samples: list[Sample] = []
    seen_text: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=1):
        text = " ".join(str(row.get("text", "")).split())
        label_name = str(row.get("label", row.get("labels", ""))).strip().casefold()
        group_id = str(
            row.get("group_id") or row.get("original_id") or row.get("id") or ""
        ).strip()
        if len(text) < 20 or len(text) > 10_000 or label_name not in LABELS or not group_id:
            raise ValueError(f"row {row_number}: invalid text, label, or group identifier")
        label = LABELS[label_name]
        text_key = hashlib.sha256(text.casefold().encode()).hexdigest()
        if text_key in seen_text:
            if seen_text[text_key] != label:
                raise ValueError(f"row {row_number}: duplicate text has conflicting labels")
            continue
        seen_text[text_key] = label
        samples.append(
            Sample(
                text=text,
                label=label,
                group_id=group_id,
                split=None,
                language=str(row.get("language", "unknown")).casefold() or "unknown",
                domain=str(
                    row.get("domain") or row.get("content_type") or row.get("category") or "unknown"
                ).casefold(),
                source=str(row.get("ai_model") or row.get("source") or "human").casefold(),
            )
        )
    return samples


def stratified_group_split(
    samples: list[Sample], *, ratio: float, seed: int
) -> tuple[list[Sample], list[Sample]]:
    groups: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        groups[sample.group_id].append(sample)
    strata: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    for group_id, rows in groups.items():
        signature = tuple(
            sorted(
                Counter(
                    (sample.label, sample.language, sample.domain, sample.source)
                    for sample in rows
                ).items()
            )
        )
        strata[signature].append(group_id)

    randomizer = random.Random(seed)
    calibration_groups: set[str] = set()
    for group_ids in strata.values():
        randomizer.shuffle(group_ids)
        take = round(len(group_ids) * ratio)
        if len(group_ids) > 1:
            take = min(max(1, take), len(group_ids) - 1)
        calibration_groups.update(group_ids[:take])
    calibration = [sample for sample in samples if sample.group_id in calibration_groups]
    audit = [sample for sample in samples if sample.group_id not in calibration_groups]
    return calibration, audit


def validate_partition(calibration: list[Sample], audit: list[Sample]) -> None:
    if {sample.group_id for sample in calibration} & {sample.group_id for sample in audit}:
        raise ValueError("group leakage detected between calibration and audit partitions")
    for name, rows in (("calibration", calibration), ("audit", audit)):
        counts = Counter(sample.label for sample in rows)
        if set(counts) != {0, 1} or min(counts.values()) < 20:
            raise ValueError(f"{name} partition needs at least 20 samples from each class")


def subgroup_report(
    probabilities: list[float],
    samples: list[Sample],
    *,
    human_threshold: float,
    ai_threshold: float,
) -> dict[str, Any]:
    labels = [sample.label for sample in samples]
    report = {
        field: evaluate_subgroups(
            probabilities,
            labels,
            [getattr(sample, field) for sample in samples],
            human_threshold=human_threshold,
            ai_threshold=ai_threshold,
        )
        for field in ("language", "domain", "source")
    }
    report["ai_source"] = evaluate_ai_sources(
        probabilities,
        labels,
        [sample.source for sample in samples],
        human_threshold=human_threshold,
        ai_threshold=ai_threshold,
    )
    return report


if __name__ == "__main__":
    main()
