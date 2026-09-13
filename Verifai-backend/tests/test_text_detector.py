import math

import pytest
from pydantic import ValidationError

from app.ContentDetector.text_detector import (
    TextModelUnavailableError,
    classify_probabilities,
    resolve_ai_label_id,
    unique_chunk_weights,
)
from app.Global.schemas import TextDetectionRequest


def test_text_detection_request_trims_text() -> None:
    request = TextDetectionRequest(text="  This is a sufficiently long test passage.  ")
    assert request.text == "This is a sufficiently long test passage."


def test_text_detection_request_rejects_short_or_oversized_text() -> None:
    with pytest.raises(ValidationError):
        TextDetectionRequest(text="too short")
    with pytest.raises(ValidationError):
        TextDetectionRequest(text="x" * 10_001)


@pytest.mark.parametrize(
    ("ai_probability", "expected"),
    [
        (0.82, "Likely AI-generated"),
        (0.18, "Likely human-written"),
        (0.55, "Review recommended"),
    ],
)
def test_probability_classification(ai_probability: float, expected: str) -> None:
    classification, confidence, human_probability = classify_probabilities(
        ai_probability, review_threshold=0.65
    )
    assert classification == expected
    assert confidence == pytest.approx(max(ai_probability, 1 - ai_probability))
    assert ai_probability + human_probability == pytest.approx(1.0)


@pytest.mark.parametrize("ai_probability", [math.nan, math.inf, -math.inf])
def test_probability_classification_rejects_non_finite_scores(ai_probability: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        classify_probabilities(ai_probability, review_threshold=0.65)


def test_ai_label_is_resolved_from_model_metadata() -> None:
    assert resolve_ai_label_id({0: "human", 1: "AI-generated"}, None) == 1
    assert resolve_ai_label_id({0: "synthetic", 1: "human"}, None) == 0


def test_ambiguous_model_labels_require_an_explicit_mapping() -> None:
    with pytest.raises(TextModelUnavailableError, match="does not identify"):
        resolve_ai_label_id({0: "LABEL_0", 1: "LABEL_1"}, None)
    assert resolve_ai_label_id({0: "LABEL_0", 1: "LABEL_1"}, 1) == 1


def test_overflow_windows_are_weighted_by_unique_tokens() -> None:
    assert unique_chunk_weights([512, 512, 102], stride=64) == [510, 446, 36]
