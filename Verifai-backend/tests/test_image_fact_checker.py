"""Tests for Image Scanner components in app.FakeNewsAnalyzer.image_fact_checker.

Covers:
- Image preprocessing (prepare_image)
- Safe OCR text cleanup (clean_ocr_text)
- Text meaningfulness checks (_has_meaningful_text)
- OCR evaluation heuristics (evaluate_ocr, _critical_text)
- PaddleOCR segment parsing and reading order
- Gemini Vision Client API handling and key rotation
- Gemini Image Detector (isolated AI detection)
- PhilippineImageFactChecker pipeline integration
"""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from PIL import Image
from pillow_heif import register_heif_opener

from app.FakeNewsAnalyzer.image_fact_checker import (
    ALLOWED_IMAGE_FORMATS,
    GeminiImageDetector,
    GeminiVisionClient,
    ImagePreprocessingError,
    OcrSegment,
    OcrUnavailableError,
    PaddleOcrEngine,
    PhilippineImageFactChecker,
    PreparedImage,
    _build_image_response,
    _critical_text,
    _has_meaningful_text,
    _insufficient_text_response,
    _ocr_failed_response,
    _parse_paddle_output,
    _reading_order_key,
    _verification_error_response,
    clean_ocr_text,
    evaluate_ocr,
    prepare_image,
)
from app.Global.schemas import ImageVerificationResponse, PhilippineImageFactCheckResponse


# ---------------------------------------------------------------------------
# Image Preprocessing Tests
# ---------------------------------------------------------------------------


def test_prepared_image_is_three_channel_for_paddleocr() -> None:
    buffer = BytesIO()
    Image.new("RGB", (80, 40), "white").save(buffer, format="PNG")

    prepared = prepare_image(buffer.getvalue(), max_pixels=1_000_000)

    assert prepared.processed.ndim == 3
    assert prepared.processed.shape[2] == 3


def test_gif_upload_is_normalized_for_ocr_and_vision() -> None:
    buffer = BytesIO()
    frames = [Image.new("RGB", (80, 40), color) for color in ("white", "black")]
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
    )

    prepared = prepare_image(buffer.getvalue(), max_pixels=1_000_000)

    assert prepared.processed.shape[2] == 3
    assert prepared.mime_type == "image/jpeg"
    assert prepared.original_bytes.startswith(b"\xff\xd8")


def test_heif_upload_is_supported_and_normalized_for_vision() -> None:
    register_heif_opener()
    buffer = BytesIO()
    Image.new("RGB", (80, 40), "white").save(buffer, format="HEIF")

    prepared = prepare_image(buffer.getvalue(), max_pixels=1_000_000)

    assert prepared.mime_type == "image/jpeg"
    assert prepared.original_bytes.startswith(b"\xff\xd8")
    assert prepared.processed.shape == (40, 80, 3)


def test_phone_resolution_image_is_downscaled_instead_of_rejected() -> None:
    buffer = BytesIO()
    Image.new("1", (5100, 5000), 1).save(buffer, format="PNG")

    prepared = prepare_image(
        buffer.getvalue(),
        max_pixels=1_000_000,
        max_source_pixels=30_000_000,
    )

    assert prepared.width * prepared.height > 25_000_000
    assert prepared.processed.shape[0] * prepared.processed.shape[1] <= 1_000_000


def test_unsupported_format_raises_preprocessing_error() -> None:
    buffer = BytesIO()
    Image.new("RGB", (50, 50), "red").save(buffer, format="BMP")

    with pytest.raises(ImagePreprocessingError, match="Only JPEG, PNG, WEBP, GIF, HEIC"):
        prepare_image(buffer.getvalue(), max_pixels=1_000_000)


def test_tiny_dimensions_raise_preprocessing_error() -> None:
    buffer = BytesIO()
    Image.new("RGB", (10, 10), "white").save(buffer, format="PNG")

    with pytest.raises(ImagePreprocessingError, match="dimensions are unsupported"):
        prepare_image(buffer.getvalue(), max_pixels=1_000_000)


def test_corrupted_bytes_raise_preprocessing_error() -> None:
    with pytest.raises(ImagePreprocessingError, match="not a valid image"):
        prepare_image(b"not-an-image-payload", max_pixels=1_000_000)


# ---------------------------------------------------------------------------
# Safe Deterministic Text Cleanup Tests
# ---------------------------------------------------------------------------


def test_clean_ocr_text_empty_and_whitespace() -> None:
    assert clean_ocr_text("") == ""
    assert clean_ocr_text("   \n\t  ") == ""


def test_clean_ocr_text_rejoins_hyphenated_words() -> None:
    raw = "The Philip-\npines announced a new eco-\n   nomic measure."
    cleaned = clean_ocr_text(raw)
    assert "Philippines" in cleaned
    assert "economic" in cleaned


def test_clean_ocr_text_rejoins_broken_sentences() -> None:
    raw = "The supreme court ruled that\nthe petition was valid."
    cleaned = clean_ocr_text(raw)
    assert cleaned == "The supreme court ruled that the petition was valid."


def test_clean_ocr_text_normalizes_repeated_punctuation() -> None:
    raw = "Breaking News!!!!!! Is this true???? Yes....."
    cleaned = clean_ocr_text(raw)
    assert cleaned == "Breaking News! Is this true? Yes..."


def test_clean_ocr_text_fixes_currency_and_number_spacing() -> None:
    raw = "Allocated ₱  500, 000 and ₱ 100 billion"
    cleaned = clean_ocr_text(raw)
    assert "₱500,000" in cleaned or "₱500, 000" in cleaned
    assert "₱100 billion" in cleaned


def test_clean_ocr_text_strips_edge_artifacts() -> None:
    raw = "--- \u2022\u2022 # President speaks at ASEAN Summit | ---"
    cleaned = clean_ocr_text(raw)
    assert cleaned == "President speaks at ASEAN Summit"


# ---------------------------------------------------------------------------
# Meaningful Text Check Tests
# ---------------------------------------------------------------------------


def test_has_meaningful_text() -> None:
    assert not _has_meaningful_text("")
    assert not _has_meaningful_text("   ")
    assert not _has_meaningful_text("Short")
    assert not _has_meaningful_text("123 456 789 000")  # numbers only
    assert not _has_meaningful_text("!@#$%^ &*()_+")   # symbols only
    assert not _has_meaningful_text("A B C")           # under char threshold
    assert _has_meaningful_text("DepEd suspends classes in all public schools nationwide")


# ---------------------------------------------------------------------------
# OCR Evaluation & Critical Text Tests
# ---------------------------------------------------------------------------


def test_critical_text_detection() -> None:
    assert _critical_text("Cost is ₱500M")
    assert _critical_text("Increased by 25%")
    assert _critical_text("Published on January 15")
    assert _critical_text("Sara Duterte arrived in Davao")
    assert not _critical_text("the quick brown fox jumps")


def test_ocr_confidence_keeps_low_confidence_critical_regions() -> None:
    segments = [
        OcrSegment("Official announcement", 0.98, [[0, 0], [100, 0], [100, 20], [0, 20]]),
        OcrSegment("₱20M", 0.62, [[0, 30], [50, 30], [50, 50], [0, 50]]),
    ]

    confidence, quality, uncertain, fallback_needed = evaluate_ocr(
        segments,
        medium_threshold=0.75,
        high_threshold=0.90,
    )

    assert confidence > 0.75
    assert quality == "HIGH"
    assert len(uncertain) == 1
    assert uncertain[0]["critical"] is True
    assert fallback_needed is True


def test_evaluate_ocr_empty_segments() -> None:
    confidence, quality, uncertain, fallback_needed = evaluate_ocr(
        [],
        medium_threshold=0.75,
        high_threshold=0.90,
    )
    assert confidence == 0.0
    assert quality == "LOW"
    assert fallback_needed is True


# ---------------------------------------------------------------------------
# PaddleOCR Output Parsing & Sorting
# ---------------------------------------------------------------------------


def test_parse_paddle_output_legacy_format() -> None:
    # Standard format: [[[box], (text, score)]]
    raw_output = [
        [
            [[[0, 0], [100, 0], [100, 20], [0, 20]], ("Headline News", 0.95)],
            [[[0, 30], [100, 30], [100, 50], [0, 50]], ("Sub-headline text", 0.88)],
        ]
    ]
    segments = _parse_paddle_output(raw_output)
    assert len(segments) == 2
    assert segments[0].text == "Headline News"
    assert segments[0].confidence == 0.95
    assert segments[1].text == "Sub-headline text"


def test_reading_order_sorts_top_to_bottom_left_to_right() -> None:
    seg_top = OcrSegment("Top", 0.9, [[10, 10], [50, 10], [50, 20], [10, 20]])
    seg_bottom = OcrSegment("Bottom", 0.9, [[10, 80], [50, 80], [50, 90], [10, 90]])

    assert _reading_order_key(seg_top) < _reading_order_key(seg_bottom)


# ---------------------------------------------------------------------------
# Gemini Vision Client Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_pool_rotates_after_quota_error_without_exposing_keys_in_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.headers["x-goog-api-key"] == "quota-full-key":
            return httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}})
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "Visible text"}]}}]},
        )

    settings = SimpleNamespace(
        gemini_api_key_list=["quota-full-key", "available-key"],
        gemini_vision_model="gemini-test",
        gemini_timeout_seconds=5,
        gemini_key_cooldown_seconds=60,
    )
    client = GeminiVisionClient(settings)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    image = PreparedImage(b"image", object(), "image/png", 100, 100)

    try:
        assert await client.transcribe(image) == "Visible text"
    finally:
        await client.aclose()

    assert [request.headers["x-goog-api-key"] for request in requests] == [
        "quota-full-key",
        "available-key",
    ]
    assert all("key=" not in str(request.url) for request in requests)


@pytest.mark.asyncio
async def test_gemini_structured_transcription_parses_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"raw_text": "PBBM leads cabinet meeting", "blocks": [{"text": "PBBM leads cabinet meeting", "type": "headline"}], "confidence": 0.97}'
                            }
                        ]
                    }
                }
            ]
        }
        return httpx.Response(200, json=payload)

    settings = SimpleNamespace(
        gemini_api_key_list=["test-key"],
        gemini_vision_model="gemini-test",
        gemini_timeout_seconds=5,
        gemini_key_cooldown_seconds=60,
    )
    client = GeminiVisionClient(settings)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    image = PreparedImage(b"image", object(), "image/png", 100, 100)

    try:
        result = await client.transcribe_structured(image)
        assert result["raw_text"] == "PBBM leads cabinet meeting"
        assert len(result["blocks"]) == 1
        assert result["blocks"][0]["type"] == "headline"
        assert result["confidence"] == 0.97
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Isolated Gemini Image Detector Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_image_detector_normalizes_structured_result() -> None:
    class FakeGeminiClient:
        configured = True
        model = "gemini-test"

        async def generate(self, image, prompt, *, generation_config):
            del image, prompt, generation_config
            return (
                '{"classification":"Inconclusive","confidence":63,'
                '"ai_probability":44,"summary":"Mixed visual signals.",'
                '"signals":["Lighting is internally consistent"],'
                '"limitations":"No provenance or metadata was inspected."}'
            )

    detector = GeminiImageDetector(FakeGeminiClient())
    result = await detector.analyze(PreparedImage(b"image", object(), "image/png", 100, 100))

    assert result["classification"] == "Inconclusive"
    assert result["authentic_probability"] == 56
    assert result["model"] == "gemini-test"


# ---------------------------------------------------------------------------
# Response Builders & Schema Compatibility Tests
# ---------------------------------------------------------------------------


def test_build_image_response_schema_validation() -> None:
    ocr_result = {
        "raw_text": "DOH confirms zero rabies cases in Manila",
        "cleaned_text": "DOH confirms zero rabies cases in Manila",
        "blocks": [{"text": "DOH confirms zero rabies cases in Manila", "type": "headline"}],
        "confidence": 0.94,
        "provider": "gemini",
        "fallback_used": False,
    }
    verification = {
        "status": "SUCCESS",
        "original_text": "DOH confirms zero rabies cases in Manila",
        "cleaned_text": "DOH confirms zero rabies cases in Manila",
        "search_text": "doh zero rabies cases manila",
        "verdict": "VERIFIED",
        "confidence": 90,
        "explanation": "Confirmed by Manila Health Department.",
        "context_warnings": [],
        "evidence": {
            "supporting": [
                {
                    "title": "Health Bulletin",
                    "source": "Manila PIO",
                    "source_type": "PRIMARY",
                    "url": "https://manila.gov.ph/bulletin",
                    "publication_date": "2026-09-01",
                    "relationship": "SUPPORTS",
                    "similarity": 92,
                    "reason": "Official announcement confirms zero cases.",
                }
            ],
            "contradicting": [],
            "related": [],
            "debunks": [],
        },
        "atomic_claims": ["DOH confirms zero rabies cases in Manila"],
        "closest_real_story": {
            "found": True,
            "title": "Health Bulletin",
            "publisher": "Manila PIO",
            "url": "https://manila.gov.ph/bulletin",
            "date": "2026-09-01",
            "similarity": 92,
            "explanation": "Match",
            "image_url": "",
        },
    }
    timing = {
        "image_processing_ms": 15.2,
        "gemini_ocr_ms": 450.0,
        "cleanup_ms": 1.1,
        "verification_ms": 820.5,
        "total_ms": 1286.8,
    }

    resp = _build_image_response(ocr_result, verification, timing)

    # Validates with both ImageVerificationResponse and backward-compatible alias
    model_obj = ImageVerificationResponse.model_validate(resp)
    legacy_obj = PhilippineImageFactCheckResponse.model_validate(resp)

    assert model_obj.input_type == "image"
    assert model_obj.status == "success"
    assert model_obj.classification == "REAL"
    assert model_obj.overall_verdict == "SUPPORTED"
    assert model_obj.confidence == 90
    assert len(model_obj.claims) == 1
    assert model_obj.claims[0]["evidence"][0]["relationship"] == "SUPPORTS"
    assert model_obj.summary == resp["reasoning_summary"]
    assert legacy_obj.classification == "REAL"


def test_insufficient_text_response_validates_schema() -> None:
    ocr_result = {
        "raw_text": "LOGO",
        "cleaned_text": "LOGO",
        "blocks": [],
        "confidence": None,
        "provider": "gemini",
        "fallback_used": False,
    }
    timing = {"image_processing_ms": 10.0, "total_ms": 500.0}

    resp = _insufficient_text_response(ocr_result, timing)
    model_obj = ImageVerificationResponse.model_validate(resp)

    assert model_obj.status == "insufficient_text"
    assert model_obj.classification == "INSUFFICIENT_EVIDENCE"
    assert model_obj.verification is None
    assert model_obj.confidence == 0


def test_ocr_failed_response_validates_schema() -> None:
    timing = {"total_ms": 350.0}
    resp = _ocr_failed_response(timing)
    model_obj = ImageVerificationResponse.model_validate(resp)

    assert model_obj.status == "ocr_failed"
    assert model_obj.classification == "INSUFFICIENT_EVIDENCE"


def test_verification_error_response_validates_schema() -> None:
    ocr_result = {
        "raw_text": "Valid headline text here",
        "cleaned_text": "Valid headline text here",
        "blocks": [],
        "confidence": 0.9,
        "provider": "gemini",
        "fallback_used": False,
    }
    timing = {"total_ms": 1200.0}
    resp = _verification_error_response(ocr_result, timing, Exception("Service Error"))
    model_obj = ImageVerificationResponse.model_validate(resp)

    assert model_obj.status == "verification_error"
    assert model_obj.classification == "INSUFFICIENT_EVIDENCE"
