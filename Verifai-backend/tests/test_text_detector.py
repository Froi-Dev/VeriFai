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


def test_extract_ai_stylistic_signals_detects_conversational_and_didactic_markers() -> None:
    from app.ContentDetector.text_detector import extract_ai_stylistic_signals

    text = (
        "Sure thing! I would be glad to help you understand this concept. "
        "At its core, it leverages fundamental principles—such as modularity and encapsulation—to operate. "
        "Feel free to ask if you have any questions!"
    )
    score, markers = extract_ai_stylistic_signals(text)
    assert score >= 2.5
    assert "conversational opener" in markers
    assert "conversational willingness" in markers
    assert "conversational closer" in markers
    assert "didactic framing" in markers


def test_extract_ai_stylistic_signals_detects_listicles_and_encyclopedic_formulas() -> None:
    from app.ContentDetector.text_detector import extract_ai_stylistic_signals

    text = (
        "Photosynthesis is the fundamental biological process by which organisms convert light. "
        "This critical mechanism sustains life. Here is a breakdown:\n"
        "1. **Light Reactions**: Capture energy.\n"
        "2. **Calvin Cycle**: Fix carbon.\n"
        "3. **Oxygen Release**: Generates oxygen.\n"
        "In conclusion, it plays a vital role."
    )
    score, markers = extract_ai_stylistic_signals(text)
    assert score >= 3.0
    assert any("listicle" in m for m in markers)


def test_extract_ai_stylistic_signals_detects_explanatory_and_cosmological_formulas() -> None:
    from app.ContentDetector.text_detector import extract_ai_stylistic_signals

    text = (
        "The Big Bang Theory explains how the universe began. Around 13.8 billion years ago, "
        "the universe was extremely hot and packed into a very small, dense state. "
        "It then started expanding and has continued to expand ever since. "
        "Scientists believe in the Big Bang because there is evidence for it. "
        "In simple words, it was the process that eventually led to the universe we see today."
    )
    score, markers = extract_ai_stylistic_signals(text)
    assert score >= 4.0
    assert "simplifying summary formula" in markers
    assert "teleological progress formula" in markers
    assert "stock cosmological formula" in markers
    assert "stock temporal continuation" in markers
    assert "didactic evidentiary formula" in markers


def test_extract_ai_stylistic_signals_ignores_clean_human_text() -> None:
    from app.ContentDetector.text_detector import extract_ai_stylistic_signals

    human_text = (
        "UPDATE! THE LEMERY DOG IS SAFE! The dog who was allegedly ordered to be captured "
        "by his owner Hart Yu on September 13 in Lemery, Batangas, has been returned and is now safe! "
        "This was confirmed by Animal Kingdom Foundation."
    )
    score, markers = extract_ai_stylistic_signals(human_text)
    assert score == 0.0
    assert len(markers) == 0


def test_compute_hybrid_ai_probability_boosts_formulaic_ai() -> None:
    from app.ContentDetector.text_detector import compute_hybrid_ai_probability

    # Low raw probability (e.g. 0.05) with high stylistic score (3.0) should boost above AI threshold
    boosted = compute_hybrid_ai_probability(0.05, 3.0, min_ai_threshold=0.8748)
    assert boosted >= 0.89

    # Already confident AI score is preserved
    confident = compute_hybrid_ai_probability(0.95, 3.0, min_ai_threshold=0.8748)
    assert confident == 0.95

    # Human score with 0 stylistic score is completely untouched
    human = compute_hybrid_ai_probability(0.002, 0.0, min_ai_threshold=0.8748)
    assert human == 0.002


def test_compute_hybrid_ai_probability_with_calibrated_thresholds_does_not_clamp_to_constant() -> None:
    from app.ContentDetector.text_detector import compute_hybrid_ai_probability

    # With modern calibrated thresholds (~0.50 AI threshold, ~0.26 human threshold):
    # Mild markers (scores 1.1 vs 1.6) must produce distinct, smoothly scaled probabilities
    prob_mild_1 = compute_hybrid_ai_probability(
        0.10, 1.1, min_ai_threshold=0.50237, human_max_threshold=0.26515
    )
    prob_mild_2 = compute_hybrid_ai_probability(
        0.10, 1.6, min_ai_threshold=0.50237, human_max_threshold=0.26515
    )
    assert prob_mild_1 < prob_mild_2
    assert prob_mild_1 != pytest.approx(0.49237, abs=1e-4)

    # Strong markers (score >= 2.5) must elevate into confident AI zone (> 0.88)
    strong = compute_hybrid_ai_probability(
        0.10, 2.8, min_ai_threshold=0.50237, human_max_threshold=0.26515
    )
    assert strong >= 0.88

