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


def test_extract_ai_stylistic_signals_detects_taglish_markers() -> None:
    from app.ContentDetector.text_detector import extract_ai_stylistic_signals

    text = (
        "Sa modernong panahon, napakahalaga ng time management para sa mga estudyante. "
        "Mahalagang tandaan na ang pagkakaroon ng maayos na study routine ay susi sa tagumpay. "
        "Hindi maikakaila na may mahalagang papel na ginagampanan ang tamang pagpaplano. "
        "Narito ang ilang mga paraan upang mas maunawaan ang proseso."
    )
    score, markers = extract_ai_stylistic_signals(text)
    assert score >= 3.0
    assert "Taglish contemporary anchor formula" in markers
    assert "Taglish didactic importance formula" in markers
    assert "Taglish undeniable assertion trope" in markers
    assert "Taglish stock role cliché" in markers
    assert "Taglish listicle/guide opener" in markers


def test_extract_ai_stylistic_signals_detects_humanized_evasion_markers() -> None:
    from app.ContentDetector.text_detector import extract_ai_stylistic_signals

    text = (
        "Here's the thing about writing thesis chapters under tight deadlines. "
        "Let's be honest, it's not just about getting passing marks; it's about staying sane. "
        "At the end of the day, what matters most is consistency and grit."
    )
    score, markers = extract_ai_stylistic_signals(text)
    assert score >= 2.5
    assert "evasive conversational pivot" in markers
    assert "conversational honesty trope" in markers
    assert "dualistic contrast formula" in markers
    assert "humanized concluding cliché" in markers


def test_extract_ai_stylistic_signals_detects_social_captions_and_bot_comments() -> None:
    from app.ContentDetector.text_detector import extract_ai_stylistic_signals

    caption = (
        "Stop scrolling if you want to ace your college exams! 📚 "
        "👉 Plan your schedule daily\n"
        "👉 Avoid doomscrolling\n"
        "Save this post for later and drop a comment below with your favorite hack! 👇 #StudyTips"
    )
    c_score, c_markers = extract_ai_stylistic_signals(caption)
    assert c_score >= 2.0
    assert "social hook formula" in c_markers
    assert "social engagement CTA" in c_markers
    assert any("emoji bullet structure" in m for m in c_markers)

    bot_comment = (
        "Such an insightful and well-written post! "
        "Couldn't agree more with your point about consistency. "
        "Thank you so much for sharing your perspective!"
    )
    b_score, b_markers = extract_ai_stylistic_signals(bot_comment)
    assert b_score >= 3.0
    assert "bot sycophantic praise" in b_markers
    assert "bot formulaic agreement" in b_markers
    assert "bot appreciation formula" in b_markers


def test_human_informal_safeguards_protect_casual_social_rants() -> None:
    from app.ContentDetector.text_detector import (
        compute_hybrid_ai_probability,
        extract_ai_stylistic_signals,
        extract_human_informal_signals,
    )

    rant = "Grabe kanina sa jeep ang init tapos na-stuck pa kami sa trapik sa may cubao gutom na gutom na ko pota haha"
    ai_score, ai_markers = extract_ai_stylistic_signals(rant)
    human_score, human_markers = extract_human_informal_signals(rant)

    assert ai_score == 0.0
    assert human_score >= 1.0
    assert any("casual colloquial markers" in m for m in human_markers)

    # If neural model outputs borderline or elevated score (e.g. 0.65), safeguard pulls it safely into human zone
    calibrated_ai = compute_hybrid_ai_probability(
        0.65,
        ai_score,
        human_marker_score=human_score,
        min_ai_threshold=0.78,
        human_max_threshold=0.46,
    )
    assert calibrated_ai <= 0.46 * 0.85
    assert calibrated_ai < 0.40


def test_extract_ai_stylistic_signals_detects_qa_markers() -> None:
    from app.ContentDetector.text_detector import extract_ai_stylistic_signals

    ai_qa_en = (
        "Great question! Let's break down the core differences between SQL and NoSQL databases. "
        "Here are the key differences between the two architectures: "
        "SQL databases use rigid schemas whereas NoSQL provides dynamic documents. "
        "Hope this answers your question! Let me know if you need further clarification or code examples."
    )
    score_en, markers_en = extract_ai_stylistic_signals(ai_qa_en)
    assert score_en >= 3.0
    assert "QA enthusiastic opener" in markers_en
    assert "QA comparative breakdown opener" in markers_en
    assert "QA helpfulness closer" in markers_en
    assert "QA follow-up invitation" in markers_en

    ai_qa_taglish = (
        "Ang sagot sa iyong katanungan ay nakasalalay sa tatlong mahahalagang salik. "
        "Narito ang detalyadong paliwanag tungkol sa epekto ng batas na ito sa lipunan. "
        "Sana nakatulong ang paliwanag na ito sa iyong assignment! Sabihin mo lang kung may tanong ka pa."
    )
    score_tl, markers_tl = extract_ai_stylistic_signals(ai_qa_taglish)
    assert score_tl >= 3.0
    assert "Taglish QA direct opener" in markers_tl
    assert "Taglish QA explanation opener" in markers_tl
    assert "Taglish QA helpfulness closer" in markers_tl
    assert "Taglish QA follow-up invitation" in markers_tl


def test_human_qa_safeguards_protect_concise_student_answers() -> None:
    from app.ContentDetector.text_detector import (
        compute_hybrid_ai_probability,
        extract_ai_stylistic_signals,
        extract_human_informal_signals,
    )

    human_qa = (
        "ganto kasi yan pre, isipin mo yung async/await parang nag-order ka sa fast food. "
        "di mo kailangan tumayo lang dun hanggang matapos haha"
    )
    ai_score, ai_markers = extract_ai_stylistic_signals(human_qa)
    human_score, human_markers = extract_human_informal_signals(human_qa)

    assert ai_score == 0.0
    assert human_score >= 1.0
    assert any("casual colloquial markers" in m for m in human_markers)

    calibrated_ai = compute_hybrid_ai_probability(
        0.58,
        ai_score,
        human_marker_score=human_score,
        min_ai_threshold=0.78,
        human_max_threshold=0.46,
    )
    assert calibrated_ai <= 0.46 * 0.85


def test_extract_ai_stylistic_signals_detects_personal_essay_and_about_me_markers() -> None:
    from app.ContentDetector.text_detector import extract_ai_stylistic_signals

    ai_personal = (
        "From a young age, I have always been fascinated by software engineering. "
        "When my family faced economic hardship, it was not merely a challenge; it was a defining crucible. "
        "This transformative experience taught me the profound value of resilience and empathy. "
        "Looking back on this journey, I realize that it served as a catalyst for personal growth."
    )
    p_score, p_markers = extract_ai_stylistic_signals(ai_personal)
    assert p_score >= 3.5
    assert "personal essay childhood opener" in p_markers
    assert "reflective crucible formula" in p_markers
    assert "profound lesson cliché" in p_markers
    assert "retrospective awakening formula" in p_markers
    assert "catalyst for growth formula" in p_markers

    ai_about_me = (
        "I am a passionate, driven individual who thrives at the intersection of machine learning and human cognition. "
        "Beyond my academic pursuits, I find solace in classical piano and landscape photography. "
        "My ultimate mission is to build intelligent systems that democratize knowledge for all."
    )
    a_score, a_markers = extract_ai_stylistic_signals(ai_about_me)
    assert a_score >= 3.0
    assert "about-me intersection trope" in a_markers
    assert "about-me solace cliché" in a_markers
    assert "about-me mission statement trope" in a_markers


def test_human_personal_narrative_safeguards() -> None:
    from app.ContentDetector.text_detector import (
        compute_hybrid_ai_probability,
        extract_ai_stylistic_signals,
        extract_human_informal_signals,
    )

    human_essay = (
        "Growing up, our kitchen was never quiet. My lola would wake up at four in the morning to prepare food. "
        "When money was tight, my lola would hand me a mango and tell me that nobody could steal education away."
    )
    ai_score, ai_markers = extract_ai_stylistic_signals(human_essay)
    human_score, human_markers = extract_human_informal_signals(human_essay)

    assert ai_score == 0.0
    assert human_score >= 1.0
    assert any("casual colloquial markers" in m for m in human_markers)

    calibrated_ai = compute_hybrid_ai_probability(
        0.60,
        ai_score,
        human_marker_score=human_score,
        min_ai_threshold=0.78,
        human_max_threshold=0.46,
    )
    assert calibrated_ai <= 0.46 * 0.85




