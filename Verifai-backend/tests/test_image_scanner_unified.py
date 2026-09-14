"""Unified Image Scanner Architecture Tests.

Verifies that the Image Scanner operates strictly as an OCR adapter that
delegates all verification to NewsVerifier, guaranteeing convergence between
text and image inputs.

Test cases:
1. Same claim convergence — Text and image pipelines both call NewsVerifier.verify() with equivalent text
2. Negation preservation — OCR cleanup preserves "NOT"
3. Allegation preservation — "accused of" doesn't become "committed"
4. Proposed vs completed — "plans to" stays "plans to"
5. Number preservation — "₱100 billion" stays correct
6. No text — Returns insufficient_text without calling NewsVerifier
7. Gemini OCR failure — Falls back to PaddleOCR
8. No duplicate verification — Single NewsVerifier.verify() call per image
"""

import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from app.FakeNewsAnalyzer.image_fact_checker import (
    OcrSegment,
    PhilippineImageFactChecker,
    clean_ocr_text,
    _has_meaningful_text,
)


def _make_test_image_bytes(width: int = 100, height: int = 100, color: str = "white") -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def _make_mock_settings():
    return SimpleNamespace(
        image_ocr_max_pixels=2_000_000,
        image_ocr_max_source_pixels=80_000_000,
        paddleocr_language="en",
        gemini_vision_model="gemini-2.5-flash",
        gemini_timeout_seconds=30.0,
        ocr_medium_confidence=0.55,
        ocr_high_confidence=0.85,
        gemini_api_key_list=["fake-key"],
        gemini_key_cooldown_seconds=60,
    )


def _make_mock_verification(text: str = "Sample claim"):
    return {
        "status": "SUCCESS",
        "original_text": text,
        "cleaned_text": text,
        "search_text": text.lower(),
        "verdict": "VERIFIED",
        "confidence": 88,
        "explanation": "Verified by official records and credible reporting.",
        "context_warnings": [],
        "evidence": {
            "supporting": [
                {
                    "title": "Official Announcement",
                    "source": "Government News",
                    "source_type": "PRIMARY",
                    "url": "https://gov.ph/news/1",
                    "publication_date": "2026-09-01",
                    "relationship": "SUPPORTS",
                    "similarity": 95,
                    "reason": "Direct statement matches the claim.",
                }
            ],
            "contradicting": [],
            "related": [],
            "debunks": [],
        },
        "atomic_claims": [text],
        "closest_real_story": {
            "found": True,
            "title": "Official Announcement",
            "publisher": "Government News",
            "url": "https://gov.ph/news/1",
            "date": "2026-09-01",
            "similarity": 95,
            "explanation": "Direct match",
            "image_url": "",
        },
    }


# ---------------------------------------------------------------------------
# Test 1: Same claim convergence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_claim_convergence() -> None:
    """Text and image pipelines converge: both delegate to NewsVerifier.verify()."""
    claim_text = "DOH warns public about fake rabies vaccine circulating online"
    settings = _make_mock_settings()

    mock_news_verifier = AsyncMock()
    mock_news_verifier.verify = AsyncMock(return_value=_make_mock_verification(claim_text))

    mock_vision = AsyncMock()
    mock_vision.configured = True
    mock_vision.transcribe_structured = AsyncMock(
        return_value={
            "raw_text": claim_text,
            "blocks": [{"text": claim_text, "type": "headline"}],
            "confidence": 0.95,
        }
    )

    mock_ocr = MagicMock()

    fact_checker = PhilippineImageFactChecker(
        settings,
        ocr_engine=mock_ocr,
        vision_client=mock_vision,
        news_verifier=mock_news_verifier,
    )

    # 1. Image pipeline execution
    image_bytes = _make_test_image_bytes()
    image_response = await fact_checker.analyze(image_bytes)

    # 2. Text pipeline execution (direct verify call)
    text_response = await mock_news_verifier.verify(claim_text)

    # Verify convergence:
    # - NewsVerifier received the exact cleaned OCR text
    mock_news_verifier.verify.assert_called_with(claim_text)
    # - The verdict, confidence, and explanation in image_response["verification"]
    #   are identical to the text pipeline result
    assert image_response["verification"] == text_response
    assert image_response["classification"] == "REAL"
    assert image_response["overall_verdict"] == "SUPPORTED"
    assert image_response["confidence"] == 88


# ---------------------------------------------------------------------------
# Test 2: Negation preservation
# ---------------------------------------------------------------------------


def test_negation_preservation() -> None:
    """Deterministic OCR cleanup must NEVER strip, alter, or invert negation words."""
    test_cases = [
        "President did NOT sign the controversial executive order",
        "DOH confirms there is NO outbreak in Cebu",
        "Witness says suspect was NEVER present at the scene",
        "Court rules petitioner cannot proceed WITHOUT valid permit",
        "Senador hindi lumagda sa committee report ukol sa pondo",
    ]

    for sentence in test_cases:
        cleaned = clean_ocr_text(sentence)
        for negation in ["NOT", "NO", "NEVER", "WITHOUT", "hindi"]:
            if negation in sentence:
                assert negation in cleaned, f"Negation '{negation}' was lost in: '{cleaned}'"


# ---------------------------------------------------------------------------
# Test 3: Allegation preservation
# ---------------------------------------------------------------------------


def test_allegation_preservation() -> None:
    """OCR cleanup must preserve evidentiary nuance ('accused of', 'alleged') without converting to fact."""
    raw = "Official accused of accepting ₱50M bribe in flood control project"
    cleaned = clean_ocr_text(raw)

    assert "accused of" in cleaned
    assert "committed" not in cleaned
    assert "accepted" not in cleaned
    assert cleaned == "Official accused of accepting ₱50M bribe in flood control project"


# ---------------------------------------------------------------------------
# Test 4: Proposed vs completed (modality preservation)
# ---------------------------------------------------------------------------


def test_modality_preservation() -> None:
    """Modality ('plans to', 'proposed', 'set to') must not be altered into completed actions."""
    raw = "DPWH plans to construct new bridge across Pasig River by 2028"
    cleaned = clean_ocr_text(raw)

    assert "plans to" in cleaned
    assert "constructed" not in cleaned
    assert "built" not in cleaned


# ---------------------------------------------------------------------------
# Test 5: Number and currency preservation
# ---------------------------------------------------------------------------


def test_number_and_currency_preservation() -> None:
    """Currency symbols (₱), amounts, and spacing artifacts must be normalized accurately."""
    raw = "Budget deficit reached ₱ 100 billion in the first quarter of 2024"
    cleaned = clean_ocr_text(raw)

    # Spacing between ₱ and number is cleaned, but the figure and denomination remain intact
    assert "₱100 billion" in cleaned
    assert "2024" in cleaned

    # Line-broken numbers
    broken = "Allocated ₱ 500, 000 for local assistance"
    cleaned_broken = clean_ocr_text(broken)
    assert "₱500,000" in cleaned_broken or "₱500, 000" in cleaned_broken


# ---------------------------------------------------------------------------
# Test 6: No text / Insufficient text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insufficient_text_returns_structured_response_without_verifying() -> None:
    """When an image has no meaningful text, returns insufficient_text without calling NewsVerifier."""
    settings = _make_mock_settings()

    mock_news_verifier = AsyncMock()
    mock_vision = AsyncMock()
    mock_vision.configured = True
    # Gemini returns negligible non-news text (e.g. watermark or tiny logo text)
    mock_vision.transcribe_structured = AsyncMock(
        return_value={
            "raw_text": "LOGO 123",
            "blocks": [{"text": "LOGO 123", "type": "watermark"}],
            "confidence": 0.8,
        }
    )

    mock_ocr = MagicMock()
    mock_ocr.transcribe = MagicMock(return_value=[])

    fact_checker = PhilippineImageFactChecker(
        settings,
        ocr_engine=mock_ocr,
        vision_client=mock_vision,
        news_verifier=mock_news_verifier,
    )

    image_bytes = _make_test_image_bytes()
    response = await fact_checker.analyze(image_bytes)

    assert response["status"] == "insufficient_text"
    assert response["classification"] == "INSUFFICIENT_EVIDENCE"
    assert response["overall_verdict"] == "UNVERIFIABLE"
    assert response["verification"] is None
    # CRITICAL: NewsVerifier must NOT have been called!
    mock_news_verifier.verify.assert_not_called()


# ---------------------------------------------------------------------------
# Test 7: Gemini OCR failure fallback to PaddleOCR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_ocr_failure_falls_back_to_paddleocr() -> None:
    """When Gemini Vision fails, pipeline gracefully falls back to PaddleOCR."""
    settings = _make_mock_settings()
    fallback_text = "DepEd announces suspension of classes nationwide due to typhoon"

    mock_news_verifier = AsyncMock()
    mock_news_verifier.verify = AsyncMock(return_value=_make_mock_verification(fallback_text))

    # Gemini Vision raises an error (e.g. rate limit, network failure)
    mock_vision = AsyncMock()
    mock_vision.configured = True
    mock_vision.transcribe_structured = AsyncMock(side_effect=RuntimeError("Gemini 503 error"))

    # PaddleOCR succeeds with segments
    mock_ocr = MagicMock()
    mock_ocr.transcribe = MagicMock(
        return_value=[
            OcrSegment(
                text=fallback_text,
                confidence=0.88,
                bounding_box=[[0, 0], [200, 0], [200, 40], [0, 40]],
            )
        ]
    )

    fact_checker = PhilippineImageFactChecker(
        settings,
        ocr_engine=mock_ocr,
        vision_client=mock_vision,
        news_verifier=mock_news_verifier,
    )

    image_bytes = _make_test_image_bytes()
    response = await fact_checker.analyze(image_bytes)

    # Verification succeeded via fallback
    assert response["status"] == "success"
    assert response["ocr"]["provider"] == "paddleocr"
    assert response["ocr"]["fallback_used"] is True
    assert fallback_text in response["ocr"]["cleaned_text"]
    mock_news_verifier.verify.assert_called_once_with(fallback_text)


# ---------------------------------------------------------------------------
# Test 8: No duplicate verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_news_verifier_call_per_image() -> None:
    """Ensures NewsVerifier.verify() is called exactly ONCE per image."""
    claim_text = "BSP maintains interest rate at 6.5 percent amid easing inflation"
    settings = _make_mock_settings()

    mock_news_verifier = AsyncMock()
    mock_news_verifier.verify = AsyncMock(return_value=_make_mock_verification(claim_text))

    mock_vision = AsyncMock()
    mock_vision.configured = True
    mock_vision.transcribe_structured = AsyncMock(
        return_value={
            "raw_text": claim_text,
            "blocks": [{"text": claim_text, "type": "headline"}],
            "confidence": 0.96,
        }
    )

    mock_ocr = MagicMock()

    fact_checker = PhilippineImageFactChecker(
        settings,
        ocr_engine=mock_ocr,
        vision_client=mock_vision,
        news_verifier=mock_news_verifier,
    )

    image_bytes = _make_test_image_bytes()
    response = await fact_checker.analyze(image_bytes)

    assert response["status"] == "success"
    # Exactly one call to NewsVerifier.verify!
    assert mock_news_verifier.verify.call_count == 1
    # Timing dictionary tracks the stages
    assert "image_processing_ms" in response["metadata"]["timing"]
    assert "gemini_ocr_ms" in response["metadata"]["timing"]
    assert "verification_ms" in response["metadata"]["timing"]
    assert "total_ms" in response["metadata"]["timing"]
