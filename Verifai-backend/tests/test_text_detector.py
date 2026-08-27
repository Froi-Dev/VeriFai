import pytest
from pydantic import ValidationError

from app.schemas import TextDetectionRequest
from app.services.text_detector import classify_probabilities


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
