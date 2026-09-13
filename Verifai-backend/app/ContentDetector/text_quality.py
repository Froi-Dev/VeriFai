"""Evaluation and calibration utilities for the AI-writing detector.

This module intentionally has no scikit-learn dependency, so the same metric definitions can
be used by training jobs, CI tests, and offline audits.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any


def sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def probabilities_from_log_odds(log_odds: Sequence[float], temperature: float) -> list[float]:
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("temperature must be positive and finite")
    return [sigmoid(value / temperature) for value in log_odds]


def fit_temperature(log_odds: Sequence[float], labels: Sequence[int]) -> float:
    """Minimize binary negative log-likelihood with bounded golden-section search."""
    _validate_predictions(log_odds, labels)

    def loss(log_temperature: float) -> float:
        probabilities = probabilities_from_log_odds(log_odds, math.exp(log_temperature))
        epsilon = 1e-12
        return -sum(
            label * math.log(max(probability, epsilon))
            + (1 - label) * math.log(max(1.0 - probability, epsilon))
            for probability, label in zip(probabilities, labels, strict=True)
        ) / len(labels)

    left, right = math.log(0.05), math.log(20.0)
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    x1 = right - ratio * (right - left)
    x2 = left + ratio * (right - left)
    y1, y2 = loss(x1), loss(x2)
    for _ in range(80):
        if y1 < y2:
            right, x2, y2 = x2, x1, y1
            x1 = right - ratio * (right - left)
            y1 = loss(x1)
        else:
            left, x1, y1 = x1, x2, y2
            x2 = left + ratio * (right - left)
            y2 = loss(x2)
    return round(math.exp((left + right) / 2.0), 8)


def choose_review_thresholds(
    probabilities: Sequence[float],
    labels: Sequence[int],
    *,
    target_precision: float = 0.90,
    min_predictions: int | None = None,
) -> tuple[float, float]:
    """Choose the widest human/AI decision regions meeting class precision targets.

    Samples between the returned thresholds are explicitly sent to review. Thresholds must be
    learned from validation data only and frozen before evaluating the test set.
    """
    _validate_predictions(probabilities, labels, probabilities=True)
    if not 0.5 < target_precision <= 1.0:
        raise ValueError("target_precision must be in (0.5, 1.0]")
    required = (
        max(3, math.ceil(len(labels) * 0.02))
        if min_predictions is None
        else min_predictions
    )
    if required < 1 or required > len(labels):
        raise ValueError("min_predictions must be between 1 and the number of samples")

    human_threshold = 0.0
    for threshold in sorted({value for value in probabilities if value < 0.5}, reverse=True):
        chosen = [index for index, value in enumerate(probabilities) if value <= threshold]
        precision = sum(labels[index] == 0 for index in chosen) / len(chosen)
        if len(chosen) >= required and precision >= target_precision:
            human_threshold = threshold
            break

    ai_threshold = 1.0
    for threshold in sorted({value for value in probabilities if value > 0.5}):
        chosen = [index for index, value in enumerate(probabilities) if value >= threshold]
        precision = sum(labels[index] == 1 for index in chosen) / len(chosen)
        if len(chosen) >= required and precision >= target_precision:
            ai_threshold = threshold
            break

    # Preserve the learned boundary exactly. Ordinary decimal rounding can move it outward and
    # admit a validation sample that caused the precision constraint to fail.
    return human_threshold, ai_threshold


def evaluate_probabilities(
    probabilities: Sequence[float],
    labels: Sequence[int],
    *,
    human_threshold: float = 0.35,
    ai_threshold: float = 0.65,
    ece_bins: int = 10,
) -> dict[str, Any]:
    _validate_predictions(probabilities, labels, probabilities=True)
    if not 0 <= human_threshold < ai_threshold <= 1:
        raise ValueError("thresholds must define a non-empty review band")
    if ece_bins < 2:
        raise ValueError("ece_bins must be at least 2")

    hard_predictions = [int(probability >= 0.5) for probability in probabilities]
    true_positive = sum(p == 1 and y == 1 for p, y in zip(hard_predictions, labels, strict=True))
    true_negative = sum(p == 0 and y == 0 for p, y in zip(hard_predictions, labels, strict=True))
    false_positive = sum(p == 1 and y == 0 for p, y in zip(hard_predictions, labels, strict=True))
    false_negative = sum(p == 0 and y == 1 for p, y in zip(hard_predictions, labels, strict=True))

    ai_precision = _ratio(true_positive, true_positive + false_positive)
    ai_recall = _ratio(true_positive, true_positive + false_negative)
    human_recall = _ratio(true_negative, true_negative + false_positive)
    f1 = _ratio(2 * ai_precision * ai_recall, ai_precision + ai_recall)

    confident: list[tuple[int, int]] = []
    human_confident: list[int] = []
    ai_confident: list[int] = []
    review_count = 0
    for probability, label in zip(probabilities, labels, strict=True):
        if probability <= human_threshold:
            confident.append((0, label))
            human_confident.append(label)
        elif probability >= ai_threshold:
            confident.append((1, label))
            ai_confident.append(label)
        else:
            review_count += 1

    return {
        "samples": len(labels),
        "class_counts": {"human": labels.count(0), "ai": labels.count(1)},
        "accuracy": _ratio(true_positive + true_negative, len(labels)),
        "balanced_accuracy": (ai_recall + human_recall) / 2.0,
        "ai_precision": ai_precision,
        "ai_recall": ai_recall,
        "human_recall": human_recall,
        "f1": f1,
        "roc_auc": _roc_auc(probabilities, labels),
        "brier_score": sum(
            (probability - label) ** 2
            for probability, label in zip(probabilities, labels, strict=True)
        )
        / len(labels),
        "expected_calibration_error": _ece(probabilities, labels, ece_bins),
        "confusion_matrix": {
            "true_human_pred_human": true_negative,
            "true_human_pred_ai": false_positive,
            "true_ai_pred_human": false_negative,
            "true_ai_pred_ai": true_positive,
        },
        "review_policy": {
            "human_max_ai_probability": human_threshold,
            "ai_min_ai_probability": ai_threshold,
            "coverage": _ratio(len(confident), len(labels)),
            "review_rate": _ratio(review_count, len(labels)),
            "accuracy_on_confident": _ratio(
                sum(prediction == label for prediction, label in confident), len(confident)
            ),
            "human_predictions": len(human_confident),
            "human_precision": _ratio(
                sum(label == 0 for label in human_confident), len(human_confident)
            ),
            "human_precision_wilson_lower_95": _wilson_lower_bound(
                sum(label == 0 for label in human_confident), len(human_confident)
            ),
            "ai_predictions": len(ai_confident),
            "ai_precision": _ratio(
                sum(label == 1 for label in ai_confident), len(ai_confident)
            ),
            "ai_precision_wilson_lower_95": _wilson_lower_bound(
                sum(label == 1 for label in ai_confident), len(ai_confident)
            ),
        },
    }


def evaluate_subgroups(
    probabilities: Sequence[float],
    labels: Sequence[int],
    groups: Iterable[str],
    *,
    human_threshold: float,
    ai_threshold: float,
    minimum_size: int = 10,
) -> dict[str, dict[str, Any]]:
    _validate_predictions(probabilities, labels, probabilities=True)
    grouped: dict[str, list[int]] = defaultdict(list)
    group_values = list(groups)
    if len(group_values) != len(labels):
        raise ValueError("groups and labels must have the same length")
    for index, group in enumerate(group_values):
        grouped[group or "unknown"].append(index)
    return {
        group: evaluate_probabilities(
            [probabilities[index] for index in indices],
            [labels[index] for index in indices],
            human_threshold=human_threshold,
            ai_threshold=ai_threshold,
        )
        for group, indices in sorted(grouped.items())
        if len(indices) >= minimum_size
        and len({labels[index] for index in indices}) == 2
    }


def evaluate_ai_sources(
    probabilities: Sequence[float],
    labels: Sequence[int],
    sources: Iterable[str],
    *,
    human_threshold: float,
    ai_threshold: float,
    minimum_ai_samples: int = 10,
) -> dict[str, dict[str, Any]]:
    """Evaluate each generator source against the shared human comparison set."""
    _validate_predictions(probabilities, labels, probabilities=True)
    source_values = list(sources)
    if len(source_values) != len(labels):
        raise ValueError("sources and labels must have the same length")
    human_indices = [index for index, label in enumerate(labels) if label == 0]
    ai_sources = sorted(
        {
            source_values[index] or "unknown"
            for index, label in enumerate(labels)
            if label == 1
        }
    )
    report: dict[str, dict[str, Any]] = {}
    for source in ai_sources:
        ai_indices = [
            index
            for index, label in enumerate(labels)
            if label == 1 and (source_values[index] or "unknown") == source
        ]
        if len(ai_indices) < minimum_ai_samples:
            continue
        indices = human_indices + ai_indices
        report[source] = evaluate_probabilities(
            [probabilities[index] for index in indices],
            [labels[index] for index in indices],
            human_threshold=human_threshold,
            ai_threshold=ai_threshold,
        )
        report[source]["ai_source_samples"] = len(ai_indices)
        report[source]["shared_human_samples"] = len(human_indices)
    return report


def _validate_predictions(
    values: Sequence[float], labels: Sequence[int], *, probabilities: bool = False
) -> None:
    if not values or len(values) != len(labels):
        raise ValueError("predictions and labels must be non-empty and have the same length")
    if set(labels) != {0, 1}:
        raise ValueError("labels must contain both binary classes 0 and 1")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("predictions must be finite")
    if probabilities and any(value < 0 or value > 1 for value in values):
        raise ValueError("probabilities must be between 0 and 1")


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _wilson_lower_bound(successes: int, total: int, z: float = 1.959963984540054) -> float:
    if total == 0:
        return 0.0
    proportion = successes / total
    denominator = 1.0 + z**2 / total
    centre = proportion + z**2 / (2.0 * total)
    margin = z * math.sqrt(
        proportion * (1.0 - proportion) / total + z**2 / (4.0 * total**2)
    )
    return (centre - margin) / denominator


def _roc_auc(probabilities: Sequence[float], labels: Sequence[int]) -> float:
    ordered = sorted(zip(probabilities, labels, strict=True), key=lambda item: item[0])
    rank_sum = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = ((index + 1) + end) / 2.0
        rank_sum += average_rank * sum(label for _, label in ordered[index:end])
        index = end
    positives = labels.count(1)
    negatives = labels.count(0)
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def _ece(probabilities: Sequence[float], labels: Sequence[int], bins: int) -> float:
    total = len(labels)
    error = 0.0
    for bin_index in range(bins):
        lower = bin_index / bins
        upper = (bin_index + 1) / bins
        indices = [
            index
            for index, probability in enumerate(probabilities)
            if lower <= probability < upper or (bin_index == bins - 1 and probability == 1.0)
        ]
        if not indices:
            continue
        mean_probability = sum(probabilities[index] for index in indices) / len(indices)
        positive_rate = sum(labels[index] for index in indices) / len(indices)
        error += len(indices) / total * abs(mean_probability - positive_rate)
    return error
