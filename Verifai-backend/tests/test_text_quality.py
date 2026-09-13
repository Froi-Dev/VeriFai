import json
import math

import pytest

from app.ContentDetector.text_detector import (
    TEXT_AGGREGATION_VERSION,
    TextModelUnavailableError,
    classify_probabilities,
    load_text_calibration,
    text_deployment_fingerprint,
)
from app.ContentDetector.text_quality import (
    choose_review_thresholds,
    evaluate_probabilities,
    evaluate_subgroups,
    fit_temperature,
    probabilities_from_log_odds,
)


def test_calibration_artifact_is_validated(tmp_path) -> None:
    artifact = {
        "schema_version": 1,
        "temperature": 1.25,
        "human_max_ai_probability": 0.2,
        "ai_min_ai_probability": 0.8,
        "validation_samples": 200,
    }
    (tmp_path / "text_calibration.json").write_text(json.dumps(artifact), encoding="utf-8")

    result = load_text_calibration(tmp_path)

    assert result is not None
    assert result.temperature == 1.25
    assert result.validation_samples == 200


def test_runtime_loads_only_a_calibration_bound_to_its_model_and_preprocessing(tmp_path) -> None:
    for filename in ("config.json", "model.safetensors", "tokenizer.json"):
        (tmp_path / filename).write_text(filename, encoding="utf-8")
    artifact = {
        "schema_version": 2,
        "aggregation_version": TEXT_AGGREGATION_VERSION,
        "max_length": 512,
        "stride": 64,
        "ai_label_id": 1,
        "deployment_fingerprint": text_deployment_fingerprint(tmp_path),
        "temperature": 1.25,
        "human_max_ai_probability": 0.2,
        "ai_min_ai_probability": 0.8,
        "validation_samples": 200,
    }
    (tmp_path / "text_calibration.json").write_text(json.dumps(artifact), encoding="utf-8")

    result = load_text_calibration(tmp_path, max_length=512, stride=64, ai_label_id=1)

    assert result is not None
    assert result.temperature == 1.25


def test_legacy_calibration_is_rejected_at_runtime(tmp_path) -> None:
    artifact = {
        "schema_version": 1,
        "temperature": 1.25,
        "human_max_ai_probability": 0.2,
        "ai_min_ai_probability": 0.8,
        "validation_samples": 200,
    }
    (tmp_path / "text_calibration.json").write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(TextModelUnavailableError, match="calibration artifact"):
        load_text_calibration(tmp_path, max_length=512, stride=64, ai_label_id=1)


def test_invalid_calibration_fails_closed(tmp_path) -> None:
    artifact = {
        "schema_version": 1,
        "temperature": 0,
        "human_max_ai_probability": 0.8,
        "ai_min_ai_probability": 0.2,
        "validation_samples": 0,
    }
    (tmp_path / "text_calibration.json").write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(TextModelUnavailableError, match="calibration artifact"):
        load_text_calibration(tmp_path)


@pytest.mark.parametrize("payload", [[], "invalid", 1, None])
def test_non_object_calibration_artifact_fails_closed(tmp_path, payload) -> None:
    (tmp_path / "text_calibration.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    with pytest.raises(TextModelUnavailableError, match="calibration artifact"):
        load_text_calibration(tmp_path)


def test_fractional_calibration_sample_count_is_rejected(tmp_path) -> None:
    artifact = {
        "schema_version": 1,
        "temperature": 1.25,
        "human_max_ai_probability": 0.2,
        "ai_min_ai_probability": 0.8,
        "validation_samples": 1.5,
    }
    (tmp_path / "text_calibration.json").write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(TextModelUnavailableError, match="calibration artifact"):
        load_text_calibration(tmp_path)


def test_calibrated_asymmetric_review_thresholds_are_used() -> None:
    assert classify_probabilities(
        0.25,
        0.65,
        human_max_ai_probability=0.20,
        ai_min_ai_probability=0.75,
    )[0] == "Review recommended"
    assert classify_probabilities(
        0.80,
        0.65,
        human_max_ai_probability=0.20,
        ai_min_ai_probability=0.75,
    )[0] == "Likely AI-generated"


def test_temperature_fitting_softens_overconfident_errors() -> None:
    log_odds = [-8.0, -6.0, -4.0, 4.0, 6.0, 8.0]
    labels = [0, 0, 1, 0, 1, 1]
    temperature = fit_temperature(log_odds, labels)
    probabilities = probabilities_from_log_odds(log_odds, temperature)

    assert temperature > 1.0
    assert all(math.isfinite(value) for value in probabilities)


def test_threshold_selection_meets_precision_and_creates_review_band() -> None:
    probabilities = [0.02, 0.10, 0.20, 0.35, 0.55, 0.70, 0.82, 0.95]
    labels = [0, 0, 0, 1, 0, 1, 1, 1]
    human_threshold, ai_threshold = choose_review_thresholds(
        probabilities, labels, target_precision=0.9, min_predictions=2
    )

    assert human_threshold == 0.2
    assert ai_threshold == 0.7
    assert human_threshold < ai_threshold


def test_threshold_selection_rejects_zero_minimum_predictions() -> None:
    with pytest.raises(ValueError, match="min_predictions"):
        choose_review_thresholds(
            [0.05, 0.15, 0.25, 0.75, 0.85, 0.95],
            [0, 0, 0, 1, 1, 1],
            min_predictions=0,
        )


def test_threshold_rounding_cannot_admit_a_sample_that_breaks_target_precision() -> None:
    probabilities = [0.10, 0.200000006, 0.200000009, 0.80, 0.90]
    labels = [0, 0, 1, 1, 1]

    human_threshold, _ = choose_review_thresholds(
        probabilities,
        labels,
        target_precision=1.0,
        min_predictions=2,
    )
    human_predictions = [
        label
        for probability, label in zip(probabilities, labels, strict=True)
        if probability <= human_threshold
    ]

    assert len(human_predictions) >= 2
    assert all(label == 0 for label in human_predictions)


def test_ai_threshold_rounding_cannot_break_target_precision() -> None:
    probabilities = [0.10, 0.20, 0.799999991, 0.799999994, 0.90]
    labels = [0, 0, 0, 1, 1]

    _, ai_threshold = choose_review_thresholds(
        probabilities,
        labels,
        target_precision=1.0,
        min_predictions=2,
    )
    ai_predictions = [
        label
        for probability, label in zip(probabilities, labels, strict=True)
        if probability >= ai_threshold
    ]

    assert len(ai_predictions) >= 2
    assert all(label == 1 for label in ai_predictions)


def test_threshold_clamping_cannot_expand_a_validated_decision_region() -> None:
    probabilities = [0.0001, 0.0004, 0.0008, 0.9992, 0.9996, 0.9999]
    labels = [0, 0, 1, 0, 1, 1]

    human_threshold, ai_threshold = choose_review_thresholds(
        probabilities,
        labels,
        target_precision=1.0,
        min_predictions=2,
    )
    human_predictions = [
        label
        for probability, label in zip(probabilities, labels, strict=True)
        if probability <= human_threshold
    ]
    ai_predictions = [
        label
        for probability, label in zip(probabilities, labels, strict=True)
        if probability >= ai_threshold
    ]

    assert human_predictions == [0, 0]
    assert ai_predictions == [1, 1]


def test_metrics_include_calibration_and_selective_accuracy() -> None:
    probabilities = [0.05, 0.30, 0.60, 0.95]
    labels = [0, 0, 1, 1]
    metrics = evaluate_probabilities(
        probabilities, labels, human_threshold=0.2, ai_threshold=0.8
    )

    assert metrics["accuracy"] == 1.0
    assert metrics["roc_auc"] == 1.0
    assert metrics["review_policy"]["coverage"] == 0.5
    assert metrics["review_policy"]["accuracy_on_confident"] == 1.0


@pytest.mark.parametrize("probabilities", [[0.1], [0.1, 0.9, 0.8]])
def test_subgroup_metrics_reject_mismatched_prediction_lengths(probabilities) -> None:
    with pytest.raises(ValueError, match="predictions and labels"):
        evaluate_subgroups(
            probabilities,
            [0, 1],
            ["english", "english"],
            human_threshold=0.2,
            ai_threshold=0.8,
            minimum_size=2,
        )
