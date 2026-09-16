"""Fine-tune, calibrate, and evaluate VeriFai's binary text detector.

Input is CSV or JSONL with: text, label, group_id, and optional split, language, domain,
source. Keep all human/AI answers derived from the same prompt or document in one group_id.
Labels accept human/0 and ai/1. If split is omitted, whole groups are deterministically split.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import math
import random
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as functional
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.ContentDetector.text_detector import (  # noqa: E402
    TEXT_AGGREGATION_VERSION,
    text_deployment_fingerprint,
    unique_chunk_weights,
)
from app.ContentDetector.text_quality import (  # noqa: E402
    choose_review_thresholds,
    evaluate_ai_sources,
    evaluate_probabilities,
    evaluate_subgroups,
    fit_temperature,
    probabilities_from_log_odds,
)

logger = logging.getLogger("train_text_detector")
LABELS = {"0": 0, "human": 0, "human-written": 0, "1": 1, "ai": 1, "ai-generated": 1}
SPLITS = {
    "train": "train",
    "validation": "validation",
    "val": "validation",
    "calibration": "calibration",
    "calibrate": "calibration",
    "test": "test",
}


@dataclass(frozen=True)
class Sample:
    text: str
    label: int
    group_id: str
    split: str | None
    language: str
    domain: str
    source: str


class ChunkDataset(Dataset):
    def __init__(
        self,
        samples: list[Sample],
        tokenizer: Any,
        *,
        max_length: int,
        stride: int,
        max_chunks_per_document: int,
        human_loss_weight: float,
    ) -> None:
        class_counts = Counter(sample.label for sample in samples)
        class_weights = {
            label: len(samples) / (2.0 * count) for label, count in class_counts.items()
        }
        class_weights[0] *= human_loss_weight
        normalization = sum(
            class_counts[label] * weight for label, weight in class_weights.items()
        ) / len(samples)
        class_weights = {
            label: weight / normalization for label, weight in class_weights.items()
        }
        self.rows: list[dict[str, Any]] = []
        for sample in samples:
            encoded = tokenizer(
                sample.text,
                add_special_tokens=True,
                max_length=max_length,
                truncation=True,
                stride=stride,
                return_overflowing_tokens=True,
                padding=False,
            )
            encoded.pop("overflow_to_sample_mapping", None)
            chunk_count = len(encoded["input_ids"])
            selected = evenly_spaced_indices(chunk_count, max_chunks_per_document)
            sample_weight = class_weights[sample.label] / len(selected)
            for index in selected:
                row = {name: values[index] for name, values in encoded.items()}
                row["label"] = sample.label
                row["sample_weight"] = sample_weight
                self.rows.append(row)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.rows[index]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--base-model", required=True, help="Hugging Face ID or local model path")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--gradient-accumulation", type=int, default=4)
    parser.add_argument("--warmup-ratio", type=float, default=0.1)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--stride", type=int, default=64)
    parser.add_argument("--max-train-chunks-per-document", type=int, default=4)
    parser.add_argument("--human-loss-weight", type=float, default=1.0)
    parser.add_argument("--validation-ratio", type=float, default=0.10)
    parser.add_argument("--calibration-ratio", type=float, default=0.10)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument("--target-precision", type=float, default=0.90)
    parser.add_argument("--minimum-confident-predictions", type=int)
    parser.add_argument("--patience", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--freeze-encoder", action="store_true")
    parser.add_argument(
        "--unfreeze-top-layers",
        type=int,
        default=0,
        help="Number of top transformer encoder layers to unfreeze (e.g. 2)",
    )
    parser.add_argument("--local-files-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_args(args)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    seed_everything(args.seed)

    samples = load_samples(args.dataset)
    splits = split_samples(
        samples,
        validation_ratio=args.validation_ratio,
        calibration_ratio=args.calibration_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed,
    )
    validate_splits(splits)
    log_split_summary(splits)

    device = resolve_device(args.device)
    tokenizer = AutoTokenizer.from_pretrained(
        args.base_model,
        use_fast=True,
        local_files_only=args.local_files_only,
        trust_remote_code=False,
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model,
        num_labels=2,
        id2label={0: "human", 1: "ai"},
        label2id={"human": 0, "ai": 1},
        local_files_only=args.local_files_only,
        trust_remote_code=False,
        ignore_mismatched_sizes=True,
    ).to(device)
    model.config.id2label = {0: "human", 1: "ai"}
    model.config.label2id = {"human": 0, "ai": 1}
    model.config.use_cache = False
    if args.freeze_encoder:
        for parameter in model.base_model.parameters():
            parameter.requires_grad_(False)
        logger.info("Frozen %s encoder parameters", model.base_model_prefix)
    elif args.unfreeze_top_layers > 0:
        for parameter in model.base_model.parameters():
            parameter.requires_grad_(False)
        encoder_layers = getattr(model.base_model.encoder, "layer", None)
        if encoder_layers is None and hasattr(model.base_model, "roberta"):
            encoder_layers = getattr(model.base_model.roberta.encoder, "layer", None)
        if encoder_layers is not None:
            num_unfrozen = min(args.unfreeze_top_layers, len(encoder_layers))
            for layer in encoder_layers[-num_unfrozen:]:
                for parameter in layer.parameters():
                    parameter.requires_grad_(True)
            logger.info(
                "Frozen %s encoder except top %d layers",
                model.base_model_prefix,
                num_unfrozen,
            )
        else:
            logger.warning("Could not locate encoder layers; default gradients retained")

    train_dataset = ChunkDataset(
        splits["train"],
        tokenizer,
        max_length=args.max_length,
        stride=args.stride,
        max_chunks_per_document=args.max_train_chunks_per_document,
        human_loss_weight=args.human_loss_weight,
    )

    def collate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        rows = [dict(row) for row in rows]
        labels = torch.tensor([row.pop("label") for row in rows], dtype=torch.long)
        weights = torch.tensor([row.pop("sample_weight") for row in rows], dtype=torch.float32)
        batch = tokenizer.pad(rows, padding=True, return_tensors="pt")
        batch["labels"] = labels
        batch["sample_weight"] = weights
        return batch

    generator = torch.Generator().manual_seed(args.seed)
    loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=collate,
        generator=generator,
        pin_memory=device.type == "cuda",
    )
    trainable_params = [p for p in model.parameters() if p.requires_grad]
    logger.info(
        "Trainable parameter tensors: %d / %d",
        len(trainable_params),
        len(list(model.parameters())),
    )
    optimizer = torch.optim.AdamW(
        trainable_params, lr=args.learning_rate, weight_decay=args.weight_decay
    )
    updates_per_epoch = math.ceil(len(loader) / args.gradient_accumulation)
    total_updates = max(1, updates_per_epoch * args.epochs)
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=round(total_updates * args.warmup_ratio),
        num_training_steps=total_updates,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer.save_pretrained(args.output_dir)
    best_score = -1.0
    best_epoch = 0
    stale_epochs = 0
    history: list[dict[str, Any]] = []

    for epoch in range(1, args.epochs + 1):
        train_loss = train_epoch(
            model,
            loader,
            optimizer,
            scheduler,
            device=device,
            gradient_accumulation=args.gradient_accumulation,
            encoder_frozen=args.freeze_encoder,
        )
        validation_log_odds = predict_document_log_odds(
            model,
            tokenizer,
            splits["validation"],
            device=device,
            max_length=args.max_length,
            stride=args.stride,
            batch_size=args.batch_size,
        )
        validation_labels = [sample.label for sample in splits["validation"]]
        validation_metrics = evaluate_probabilities(
            probabilities_from_log_odds(validation_log_odds, 1.0), validation_labels
        )
        score = float(validation_metrics["balanced_accuracy"])
        history.append(
            {"epoch": epoch, "train_loss": train_loss, "validation": validation_metrics}
        )
        logger.info(
            "epoch=%d train_loss=%.5f validation_balanced_accuracy=%.4f auc=%.4f",
            epoch,
            train_loss,
            score,
            validation_metrics["roc_auc"],
        )
        if score > best_score + 1e-6:
            best_score, best_epoch, stale_epochs = score, epoch, 0
            model.save_pretrained(args.output_dir, safe_serialization=True)
        else:
            stale_epochs += 1
            if stale_epochs >= args.patience:
                logger.info("early stopping after epoch %d", epoch)
                break

    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()
    model = AutoModelForSequenceClassification.from_pretrained(
        args.output_dir, local_files_only=True, trust_remote_code=False
    ).to(device)
    model.eval()

    calibration_log_odds = predict_document_log_odds(
        model,
        tokenizer,
        splits["calibration"],
        device=device,
        max_length=args.max_length,
        stride=args.stride,
        batch_size=args.batch_size,
    )
    calibration_labels = [sample.label for sample in splits["calibration"]]
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

    test_log_odds = predict_document_log_odds(
        model,
        tokenizer,
        splits["test"],
        device=device,
        max_length=args.max_length,
        stride=args.stride,
        batch_size=args.batch_size,
    )
    test_labels = [sample.label for sample in splits["test"]]
    test_probabilities = probabilities_from_log_odds(test_log_odds, temperature)
    test_metrics = evaluate_probabilities(
        test_probabilities,
        test_labels,
        human_threshold=human_threshold,
        ai_threshold=ai_threshold,
    )

    calibration = {
        "schema_version": 2,
        "aggregation_version": TEXT_AGGREGATION_VERSION,
        "max_length": args.max_length,
        "stride": args.stride,
        "ai_label_id": 1,
        "deployment_fingerprint": text_deployment_fingerprint(args.output_dir),
        "temperature": temperature,
        "human_max_ai_probability": human_threshold,
        "ai_min_ai_probability": ai_threshold,
        "validation_samples": len(calibration_labels),
        "calibration_samples": len(calibration_labels),
        "target_class_precision": args.target_precision,
    }
    report = {
        "schema_version": 1,
        "dataset_sha256": dataset_fingerprint(samples),
        "split_counts": {name: len(rows) for name, rows in splits.items()},
        "best_epoch": best_epoch,
        "training_history": history,
        "calibration": calibration,
        "calibration_metrics": calibration_metrics,
        "test": test_metrics,
        "test_subgroups": {
            "language": evaluate_subgroups(
                test_probabilities,
                test_labels,
                [sample.language for sample in splits["test"]],
                human_threshold=human_threshold,
                ai_threshold=ai_threshold,
            ),
            "domain": evaluate_subgroups(
                test_probabilities,
                test_labels,
                [sample.domain for sample in splits["test"]],
                human_threshold=human_threshold,
                ai_threshold=ai_threshold,
            ),
            "ai_source": evaluate_ai_sources(
                test_probabilities,
                test_labels,
                [sample.source for sample in splits["test"]],
                human_threshold=human_threshold,
                ai_threshold=ai_threshold,
            ),
        },
        "training_config": serializable_args(args),
    }
    write_json(args.output_dir / "text_calibration.json", calibration)
    write_json(args.output_dir / "evaluation_report.json", report)
    logger.info(
        "complete best_epoch=%d test_balanced_accuracy=%.4f test_auc=%.4f coverage=%.4f",
        best_epoch,
        test_metrics["balanced_accuracy"],
        test_metrics["roc_auc"],
        test_metrics["review_policy"]["coverage"],
    )


def train_epoch(
    model: Any,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    *,
    device: torch.device,
    gradient_accumulation: int,
    encoder_frozen: bool,
) -> float:
    model.train()
    if encoder_frozen:
        model.base_model.eval()
    optimizer.zero_grad(set_to_none=True)
    loss_total = 0.0
    for batch_index, batch in enumerate(loader, start=1):
        labels = batch.pop("labels").to(device)
        sample_weights = batch.pop("sample_weight").to(device)
        inputs = {name: value.to(device) for name, value in batch.items()}
        logits = model(**inputs).logits
        losses = functional.cross_entropy(logits, labels, reduction="none")
        # A fixed per-row normalization preserves inverse-document and class weights. Dividing
        # by the weights present in each shuffled mini-batch would cancel them for batch_size=1
        # and make the objective depend on batch composition.
        loss = (losses * sample_weights).mean()
        (loss / gradient_accumulation).backward()
        loss_total += float(loss.detach().cpu())
        if batch_index % gradient_accumulation == 0 or batch_index == len(loader):
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
    return loss_total / len(loader)


def predict_document_log_odds(
    model: Any,
    tokenizer: Any,
    samples: list[Sample],
    *,
    device: torch.device,
    max_length: int,
    stride: int,
    batch_size: int,
    ai_label_id: int = 1,
) -> list[float]:
    model.eval()
    rows: list[dict[str, Any]] = []
    metadata: list[tuple[int, int]] = []
    for document_index, sample in enumerate(samples):
        encoded = tokenizer(
            sample.text,
            add_special_tokens=True,
            max_length=max_length,
            truncation=True,
            stride=stride,
            return_overflowing_tokens=True,
            padding=False,
        )
        encoded.pop("overflow_to_sample_mapping", None)
        counts = [sum(mask) for mask in encoded["attention_mask"]]
        weights = unique_chunk_weights(counts, stride)
        for chunk_index, weight in enumerate(weights):
            rows.append({name: values[chunk_index] for name, values in encoded.items()})
            metadata.append((document_index, weight))

    weighted_sums = [0.0] * len(samples)
    weight_sums = [0] * len(samples)
    with torch.inference_mode():
        for start in range(0, len(rows), batch_size):
            batch_rows = rows[start : start + batch_size]
            batch = tokenizer.pad(batch_rows, padding=True, return_tensors="pt")
            logits = model(**{name: value.to(device) for name, value in batch.items()}).logits
            human_label_id = 1 - ai_label_id
            log_odds = (
                logits[:, ai_label_id] - logits[:, human_label_id]
            ).detach().cpu().tolist()
            for offset, value in enumerate(log_odds):
                document_index, weight = metadata[start + offset]
                weighted_sums[document_index] += float(value) * weight
                weight_sums[document_index] += weight
    return [total / weight for total, weight in zip(weighted_sums, weight_sums, strict=True)]


def load_samples(path: Path) -> list[Sample]:
    if not path.is_file():
        raise ValueError(f"dataset does not exist: {path}")
    if path.suffix.casefold() == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle if line.strip()]
    elif path.suffix.casefold() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            records = list(csv.DictReader(handle))
    else:
        raise ValueError("dataset must be a .csv or .jsonl file")

    samples: list[Sample] = []
    seen_text: dict[str, int] = {}
    for row_number, record in enumerate(records, start=1):
        try:
            text = " ".join(str(record["text"]).split())
            raw_label = str(record["label"]).strip().casefold()
            group_id = str(record["group_id"]).strip()
        except (KeyError, TypeError) as exc:
            raise ValueError(f"row {row_number}: text, label, and group_id are required") from exc
        if len(text) < 20 or len(text) > 10_000:
            raise ValueError(f"row {row_number}: text must contain 20-10,000 characters")
        if raw_label not in LABELS:
            raise ValueError(f"row {row_number}: unsupported label {raw_label!r}")
        if not group_id:
            raise ValueError(f"row {row_number}: group_id cannot be blank")
        label = LABELS[raw_label]
        text_key = hashlib.sha256(text.casefold().encode()).hexdigest()
        if text_key in seen_text:
            if seen_text[text_key] != label:
                raise ValueError(f"row {row_number}: identical text has conflicting labels")
            continue
        seen_text[text_key] = label
        raw_split = str(record.get("split", "")).strip().casefold()
        if raw_split and raw_split not in SPLITS:
            raise ValueError(
                f"row {row_number}: split must be train, validation, calibration, or test"
            )
        samples.append(
            Sample(
                text=text,
                label=label,
                group_id=group_id,
                split=SPLITS.get(raw_split),
                language=str(record.get("language", "unknown")).strip().casefold() or "unknown",
                domain=str(record.get("domain", "unknown")).strip().casefold() or "unknown",
                source=str(record.get("source", "unknown")).strip().casefold() or "unknown",
            )
        )
    if not samples:
        raise ValueError("dataset is empty")
    return samples


def split_samples(
    samples: list[Sample],
    *,
    validation_ratio: float,
    calibration_ratio: float,
    test_ratio: float,
    seed: int,
) -> dict[str, list[Sample]]:
    explicit = [sample.split is not None for sample in samples]
    if any(explicit):
        if not all(explicit):
            raise ValueError("split must be set on every row or omitted from every row")
        group_splits: dict[str, set[str | None]] = defaultdict(set)
        for sample in samples:
            group_splits[sample.group_id].add(sample.split)
        leaked = [group for group, values in group_splits.items() if len(values) != 1]
        if leaked:
            raise ValueError(f"group_id appears in multiple splits: {leaked[0]}")
        return {
            name: [sample for sample in samples if sample.split == name]
            for name in ("train", "validation", "calibration", "test")
        }

    grouped: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        grouped[sample.group_id].append(sample)
    group_ids = sorted(grouped)
    random.Random(seed).shuffle(group_ids)
    test_groups = max(1, round(len(group_ids) * test_ratio))
    validation_groups = max(1, round(len(group_ids) * validation_ratio))
    calibration_groups = max(1, round(len(group_ids) * calibration_ratio))
    held_out_groups = test_groups + validation_groups + calibration_groups
    if held_out_groups >= len(group_ids):
        raise ValueError(
            "not enough groups for train, validation, calibration, and test splits"
        )
    assignment = {
        group_id: (
            "test"
            if index < test_groups
            else "validation"
            if index < test_groups + validation_groups
            else "calibration"
            if index < held_out_groups
            else "train"
        )
        for index, group_id in enumerate(group_ids)
    }
    result: dict[str, list[Sample]] = {
        name: [] for name in ("train", "validation", "calibration", "test")
    }
    for sample in samples:
        result[assignment[sample.group_id]].append(sample)
    return result


def validate_splits(splits: dict[str, list[Sample]]) -> None:
    group_sets = {name: {sample.group_id for sample in rows} for name, rows in splits.items()}
    split_names = tuple(group_sets)
    for index, left in enumerate(split_names):
        for right in split_names[index + 1 :]:
            if group_sets[left] & group_sets[right]:
                raise ValueError("group leakage detected across splits")
    for name, rows in splits.items():
        counts = Counter(sample.label for sample in rows)
        if set(counts) != {0, 1} or min(counts.values()) < 3:
            raise ValueError(f"{name} split needs at least 3 unique samples from each class")


def validate_args(args: argparse.Namespace) -> None:
    if args.epochs < 1 or args.batch_size < 1 or args.gradient_accumulation < 1:
        raise ValueError("epochs, batch size, and gradient accumulation must be positive")
    if args.human_loss_weight <= 0:
        raise ValueError("human loss weight must be positive")
    if args.unfreeze_top_layers < 0:
        raise ValueError("unfreeze-top-layers must be non-negative")
    if not 32 <= args.max_length <= 512:
        raise ValueError("max length must be between 32 and 512")
    if not 0 <= args.stride < args.max_length - 2:
        raise ValueError("stride must be non-negative and smaller than the model window")
    held_out_ratios = (
        args.validation_ratio,
        args.calibration_ratio,
        args.test_ratio,
    )
    if any(not 0 < ratio < 0.5 for ratio in held_out_ratios):
        raise ValueError("validation, calibration, and test ratios must be between 0 and 0.5")
    if sum(held_out_ratios) >= 0.8:
        raise ValueError("held-out ratios leave too little training data")
    if args.output_dir.resolve() == Path(args.base_model).expanduser().resolve():
        raise ValueError("output directory must differ from the base model directory")


def evenly_spaced_indices(count: int, maximum: int) -> list[int]:
    if maximum < 1:
        raise ValueError("maximum chunks per document must be positive")
    if count <= maximum:
        return list(range(count))
    if maximum == 1:
        return [count // 2]
    return sorted({round(index * (count - 1) / (maximum - 1)) for index in range(maximum)})


def resolve_device(requested: str) -> torch.device:
    if requested == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA was requested but is unavailable")
    use_cuda = requested == "cuda" or (requested == "auto" and torch.cuda.is_available())
    return torch.device("cuda" if use_cuda else "cpu")


def seed_everything(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def dataset_fingerprint(samples: list[Sample]) -> str:
    canonical = "\n".join(
        json.dumps(asdict(sample), sort_keys=True, ensure_ascii=False)
        for sample in sorted(samples, key=lambda item: (item.group_id, item.label, item.text))
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def serializable_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        name: str(value) if isinstance(value, Path) else value
        for name, value in vars(args).items()
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def log_split_summary(splits: dict[str, list[Sample]]) -> None:
    for name, rows in splits.items():
        counts = Counter(sample.label for sample in rows)
        logger.info(
            "%s documents=%d groups=%d human=%d ai=%d",
            name,
            len(rows),
            len({sample.group_id for sample in rows}),
            counts[0],
            counts[1],
        )


if __name__ == "__main__":
    main()
