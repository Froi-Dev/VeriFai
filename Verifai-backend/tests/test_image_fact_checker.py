from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image
from pillow_heif import register_heif_opener

from app.FakeNewsAnalyzer import image_fact_checker as module
from app.FakeNewsAnalyzer.image_fact_checker import (
    GeminiImageDetector,
    GeminiVisionClient,
    OcrSegment,
    OcrUnavailableError,
    PhilippineImageFactChecker,
    PreparedImage,
    _claim_response,
    _contextual_verification_claim,
    _public_classification,
    compare_ocr_outputs,
    evaluate_ocr,
    extract_atomic_claims,
    normalize_fact_text,
    prepare_image,
)
from app.Global.schemas import PhilippineImageFactCheckResponse


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


def test_named_direct_quote_is_normalized_as_attributed_quote() -> None:
    understanding = module._normalize_understanding(
        {
            "content_type": "OPINION",
            "speaker": "Sir Jack Argota",
            "direct_quotes": ["Yung ICC madidismantle na."],
            "text_quality": "HIGH",
        }
    )

    assert understanding["content_type"] == "ATTRIBUTED_QUOTE"


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
    # Overall OCR may still be high while a critical amount remains uncertain.
    assert quality == "HIGH"
    assert uncertain == [
        {
            "text": "₱20M",
            "confidence": 0.62,
            "bounding_box": [[0, 30], [50, 30], [50, 50], [0, 50]],
            "critical": True,
        }
    ]
    assert fallback_needed is True


def test_ocr_comparison_records_correction_without_overwriting_raw_text() -> None:
    final_text, corrections, conflicts = compare_ocr_outputs(
        "Gastos: ₱2OM kada buwan",
        "Gastos: ₱20M kada buwan",
    )

    assert final_text == "Gastos: ₱20M kada buwan"
    assert corrections == [{"original": "2OM", "corrected": "20M", "confidence": "HIGH"}]
    assert conflicts == []


def test_ocr_comparison_marks_disputed_number_for_review() -> None:
    final_text, _, conflicts = compare_ocr_outputs("433 personnel", "483 personnel")

    assert final_text == "433 personnel"
    assert conflicts[0]["status"] == "OCR_CONFLICT"
    assert conflicts[0]["candidates"] == ["433", "483"]
    assert conflicts[0]["requires_review"] is True


def test_normalization_is_deterministic_and_preserves_original_values() -> None:
    normalized, values = normalize_fact_text("PNP spent PHP 20M on Aug. 27, 2026.")

    assert "PNP (Philippine National Police)" in normalized
    assert "₱20,000,000" in normalized
    assert "2026-08-27" in normalized
    assert {item["type"] for item in values} == {"AGENCY", "DATE", "MONEY"}


def test_claim_extraction_separates_atomic_statements_and_skips_rhetoric() -> None:
    claims = extract_atomic_claims(
        "Sara Duterte had 433 security personnel. The assignment cost ₱20M per month. "
        "Nakakahiya! Share this!"
    )

    assert claims == [
        "Sara Duterte had 433 security personnel",
        "The assignment cost ₱20M per month",
    ]


def test_claim_extraction_uses_tagalog_headline_and_skips_social_metadata() -> None:
    claims = extract_atomic_claims(
        "Duterte Forever · Join\n"
        "Aljohn Reyes · 19h ·\n"
        "BREAKING NEWS: President Donald Tram binisita ang\n"
        "ating pangulo at nangako na papalayain sa madaling\n"
        "panahon.\n"
        "Malapit na tayo sa kattohanan mga kapatid..."
    )

    assert claims == [
        "BREAKING NEWS: President Donald Tram binisita ang ating pangulo at nangako na "
        "papalayain sa madaling panahon"
    ]


def test_ambiguous_image_claim_uses_page_context_for_search() -> None:
    claim = (
        "President Donald Tram binisita ang ating pangulo at nangako na papalayain "
        "sa madaling panahon"
    )
    full_text = f"Duterte Forever · Join\nAljohn Reyes · 19h ·\n{claim}"

    enriched = _contextual_verification_claim(claim, full_text)

    assert enriched == f"{claim} Duterte Forever"


def test_quote_card_uses_visible_speaker_attribution_for_search() -> None:
    claim = (
        "'Pag may nangyaring 'di maganda sa buhay n'yo, isipin n'yo na lang na mas "
        "matindi yung nangyari sa buhay ko"
    )
    full_text = f"Daily Tribune\n{claim}\nVP Sara Duterte"

    enriched = _contextual_verification_claim(claim, full_text)

    assert enriched == f"{claim} VP Sara Duterte"


def test_unconfirmed_image_event_remains_unverified_without_contradictory_evidence() -> None:
    result = {
        "status": "SUCCESS",
        "verdict": "UNVERIFIED",
        "confidence": 35,
        "explanation": "No direct match was found.",
        "search": {"queries": ["claim fact check"]},
        "evidence": {
            "supporting": [],
            "contradicting": [],
            "related": [
                {
                    "title": "Unrelated author archive",
                    "publisher": "balita",
                    "url": "https://balita.mb.com.ph/author/13/?pgno=49",
                    "domain": "balita.mb.com.ph",
                    "published_date": "",
                    "relationship": "RELATED",
                    "explanation": "Only loosely related.",
                    "evidence_text": "An unrelated story.",
                }
            ],
            "debunks": [],
        },
    }

    response = _claim_response(
        "President Donald Tram nangako na papalayain ang pangulo",
        result,
        "HIGH",
        [],
    )

    assert response["verdict"] == "UNVERIFIED"
    assert response["explanation"] == "No direct match was found."
    assert response["evidence"][0]["relationship"] == "UNRELATED"


def test_attributed_quote_is_not_called_fake_only_because_search_found_no_match() -> None:
    result = {
        "status": "SUCCESS",
        "verdict": "UNVERIFIED",
        "confidence": 35,
        "explanation": "No direct match was found.",
        "search": {"queries": ["quote speaker"]},
        "evidence": {
            "supporting": [],
            "contradicting": [],
            "related": [],
            "debunks": [],
        },
    }

    response = _claim_response(
        "Isipin ninyo na lang na mas matindi yung nangyari sa buhay ko",
        result,
        "HIGH",
        [],
        attributed_quote=True,
    )

    assert response["verdict"] == "UNVERIFIED"


def test_true_image_result_only_shows_evidence_that_supports_the_claim() -> None:
    supporting = {
        "publisher": "SMNI NEWS CHANNEL",
        "url": "https://smninewschannel.com/confirming-article/",
        "domain": "smninewschannel.com",
        "published_date": "2026-02-23",
        "relationship": "SUPPORTS",
        "explanation": "The article contains the quote.",
        "evidence_text": "Isipin ninyo na lang na mas matindi yung nangyari sa buhay ko.",
    }
    unrelated = {
        **supporting,
        "url": "https://smninewschannel.com/different-story/",
        "relationship": "RELATED",
        "evidence_text": "A different story about the same person.",
    }
    result = {
        "status": "SUCCESS",
        "verdict": "LIKELY_TRUE",
        "confidence": 83,
        "explanation": "A credible report contains the quote.",
        "search": {"queries": ["quote speaker"]},
        "evidence": {
            "supporting": [supporting],
            "contradicting": [],
            "related": [unrelated],
            "debunks": [],
        },
    }

    response = _claim_response(
        "Isipin n'yo na lang na mas matindi yung nangyari sa buhay ko",
        result,
        "HIGH",
        [],
        attributed_quote=True,
    )

    assert response["verdict"] == "PARTIALLY_SUPPORTED"
    assert [item["url"] for item in response["evidence"]] == [supporting["url"]]


def test_debunked_assertion_overrides_verified_quote_content_type() -> None:
    supporting_quote = {
        "source": "Original interview",
        "source_type": "MAJOR_NEWS",
        "url": "https://example.com/interview",
        "publication_date": "2026-08-30",
        "relationship": "SUPPORTS",
        "reason": "The interview contains the attributed words.",
    }
    debunk = {
        "source": "VERA Files",
        "source_type": "MAJOR_NEWS",
        "url": "https://verafiles.org/",
        "publication_date": "2026-08-31",
        "relationship": "CONTRADICTS",
        "reason": "The factual assertion in the quote is false.",
    }
    claims = [
        {"verdict": "SUPPORTED", "evidence": [supporting_quote]},
        # Providers can conservatively call the combined claim unverified even
        # when a credible fact-check directly contradicts one assertion.
        {"verdict": "UNVERIFIED", "evidence": [debunk]},
    ]

    classification = _public_classification(
        {"content_type": "ATTRIBUTED_QUOTE"},
        claims,
        {
            "is_quote": True,
            "speaker": "Example Speaker",
            "attribution": "VERIFIED",
            "context": "ACCURATE",
        },
        {"consistent": True},
    )

    assert classification == "FAKE"


class FakeOcrEngine:
    def transcribe(self, image):
        del image
        return [
            OcrSegment(
                "PNP assigned 433 security personnel.",
                0.70,
                [[0, 0], [400, 0], [400, 30], [0, 30]],
            ),
            OcrSegment(
                "It costs ₱2OM per month.",
                0.65,
                [[0, 40], [400, 40], [400, 70], [0, 70]],
            ),
        ]


class FakeVisionClient:
    configured = True

    async def transcribe(self, image):
        del image
        return "PNP assigned 433 security personnel.\nIt costs ₱20M per month."


class FakeNewsVerifier:
    async def verify(self, claim):
        return {
            "status": "SUCCESS",
            "verdict": "VERIFIED",
            "confidence": 88,
            "explanation": "A matching report supports this claim.",
            "search": {"queries": [claim, f'"{claim}"']},
            "evidence": {
                "supporting": [
                    {
                        "title": "Official briefing",
                        "publisher": "Philippine News Agency",
                        "url": "https://pna.gov.ph/articles/example",
                        "domain": "pna.gov.ph",
                        "published_date": "2026-08-27",
                        "image_url": "",
                        "relationship": "SUPPORTS",
                        "similarity": 91,
                        "evidence_score": 90,
                        "source_tier": 2,
                        "explanation": "The briefing reports the same fact.",
                    }
                ],
                "contradicting": [],
                "related": [],
                "debunks": [],
            },
        }


class FailingNewsVerifier:
    async def verify(self, claim):
        raise AssertionError(f"Low-confidence OCR claim was verified: {claim}")


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


@pytest.mark.asyncio
async def test_full_pipeline_preserves_both_ocr_records_and_returns_claim_verdicts(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        module,
        "prepare_image",
        lambda image_bytes, max_pixels: PreparedImage(
            original_bytes=image_bytes,
            processed=object(),
            mime_type="image/png",
            width=600,
            height=400,
        ),
    )
    settings = SimpleNamespace(
        paddleocr_language="en",
        image_ocr_max_pixels=25_000_000,
        ocr_medium_confidence=0.75,
        ocr_high_confidence=0.90,
        gemini_api_key=None,
        gemini_vision_model="unused",
        gemini_timeout_seconds=5,
    )
    checker = PhilippineImageFactChecker(
        settings,
        ocr_engine=FakeOcrEngine(),
        vision_client=FakeVisionClient(),
        news_verifier=FakeNewsVerifier(),
    )

    report = await checker.analyze(b"original-image")
    validated = PhilippineImageFactCheckResponse.model_validate(report)

    assert validated.ocr.raw_paddle_text.endswith("₱2OM per month.")
    assert validated.ocr.gemini_transcription.endswith("₱20M per month.")
    assert "₱20,000,000" in validated.ocr.normalized_text
    assert validated.ocr.corrections[0].original == "2OM"
    assert [claim.claim_id for claim in validated.claims] == ["C1", "C2"]
    assert all(claim.verdict == "SUPPORTED" for claim in validated.claims)
    assert validated.overall_verdict == "SUPPORTED"


@pytest.mark.asyncio
async def test_low_confidence_ocr_without_fallback_does_not_produce_verdicts(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        module,
        "prepare_image",
        lambda image_bytes, max_pixels: PreparedImage(
            original_bytes=image_bytes,
            processed=object(),
            mime_type="image/png",
            width=600,
            height=400,
        ),
    )

    class LowConfidenceOcr:
        def transcribe(self, image):
            del image
            return [OcrSegment("PNP arrested 433 people.", 0.40, [])]

    class NoVisionFallback:
        configured = False

    settings = SimpleNamespace(
        paddleocr_language="en",
        image_ocr_max_pixels=25_000_000,
        ocr_medium_confidence=0.75,
        ocr_high_confidence=0.90,
        gemini_api_key=None,
        gemini_vision_model="unused",
        gemini_timeout_seconds=5,
    )
    checker = PhilippineImageFactChecker(
        settings,
        ocr_engine=LowConfidenceOcr(),
        vision_client=NoVisionFallback(),
        news_verifier=FailingNewsVerifier(),
    )

    report = await checker.analyze(b"original-image")

    assert report["claims"] == []
    assert report["overall_verdict"] == "UNVERIFIABLE"
    assert report["overall_confidence"] == "LOW"
    assert "no factual verdict" in report["summary"].lower()


@pytest.mark.asyncio
async def test_unavailable_primary_ocr_uses_configured_gemini_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "prepare_image",
        lambda image_bytes, max_pixels: PreparedImage(
            original_bytes=image_bytes,
            processed=object(),
            mime_type="image/png",
            width=600,
            height=400,
        ),
    )

    class UnavailableOcr:
        def transcribe(self, image):
            del image
            raise OcrUnavailableError("PaddleOCR is unavailable")

    settings = SimpleNamespace(
        paddleocr_language="en",
        image_ocr_max_pixels=25_000_000,
        ocr_medium_confidence=0.75,
        ocr_high_confidence=0.90,
        gemini_api_key=None,
        gemini_vision_model="unused",
        gemini_timeout_seconds=5,
    )
    checker = PhilippineImageFactChecker(
        settings,
        ocr_engine=UnavailableOcr(),
        vision_client=FakeVisionClient(),
        news_verifier=FakeNewsVerifier(),
    )

    report = await checker.analyze(b"original-image")

    assert report["ocr"]["raw_paddle_text"] == ""
    assert report["ocr"]["gemini_used"] is True
    assert report["claims"]


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "image_verification"


def _vision_record(**overrides):
    record = {
        "headline": "",
        "body_text": "",
        "direct_quotes": [],
        "speaker": "",
        "publisher": "",
        "logo": "",
        "username": "",
        "dates": [],
        "post_date": "",
        "event_date": "",
        "locations": [],
        "organizations": [],
        "government_agencies": [],
        "people": [],
        "caption_text": "",
        "hashtags": [],
        "content_type": "OTHER",
        "indicators": [],
        "atomic_claims": [],
        "uncertain_text": [],
        "text_quality": "HIGH",
        "needs_ocr": False,
    }
    record.update(overrides)
    return record


class ThreeFixtureVisionClient:
    configured = True

    async def understand(self, image, *, fallback_ocr_text="", initial=None):
        assert not fallback_ocr_text
        assert initial is None
        if (image.width, image.height) == (514, 593):
            headline = (
                "Philippines Moves Closer to Nuclear Energy as DOE Advances Key "
                "Preparations for Future"
            )
            return _vision_record(
                headline=headline,
                body_text=headline,
                publisher="Iskolar ng Bayan",
                logo="Iskolar ng Bayan",
                locations=["Philippines"],
                government_agencies=["Department of Energy"],
                content_type="FACTUAL_NEWS",
                atomic_claims=[
                    "The Philippines and Department of Energy are advancing preparations "
                    "for future nuclear energy deployment."
                ],
            )
        if (image.width, image.height) == (422, 487):
            quote = (
                "'Pag may nangyaring 'di maganda sa buhay n'yo, isipin n'yo na lang na "
                "mas matindi 'yung nangyari sa buhay ko."
            )
            return _vision_record(
                body_text=quote,
                direct_quotes=[quote],
                speaker="VP Sara Duterte",
                publisher="Daily Tribune",
                logo="Daily Tribune",
                people=["Sara Duterte"],
                content_type="DIRECT_QUOTE",
                atomic_claims=[quote],
            )
        if (image.width, image.height) == (498, 605):
            quote = "Yung ICC madidismantle na. Uuwi na si Duterte!"
            return _vision_record(
                headline=f'Sir Jack Argota: "{quote}"',
                body_text=quote,
                direct_quotes=[quote],
                speaker="Sir Jack Argota",
                publisher="Unofficial TiktokvibesPh",
                username="Unofficial TiktokvibesPh",
                people=["Jack Argota", "Duterte"],
                organizations=["International Criminal Court"],
                content_type="ATTRIBUTED_QUOTE",
                indicators=["Unofficial source watermark"],
                atomic_claims=[quote],
            )
        raise AssertionError(f"Unexpected fixture dimensions: {image.width}x{image.height}")


class OcrMustRemainFallback:
    def transcribe(self, image):
        del image
        raise AssertionError("High-confidence Gemini extraction should not invoke fallback OCR")


def _fixture_evidence(
    *,
    source: str,
    url: str,
    domain: str,
    relationship: str,
    tier: int,
):
    return {
        "title": "Regression fixture evidence",
        "publisher": source,
        "url": url,
        "domain": domain,
        "published_date": "2026-08-30",
        "image_url": "",
        "relationship": relationship,
        "similarity": 95,
        "evidence_score": 95,
        "source_tier": tier,
        "explanation": "The retrieved source directly addresses the fixture claim.",
        "evidence_text": "Fixture passage",
    }


class ThreeFixtureNewsVerifier:
    async def verify(self, claim):
        lowered = claim.casefold()
        groups = {"supporting": [], "contradicting": [], "related": [], "debunks": []}
        if "nuclear" in lowered:
            verdict = "VERIFIED"
            confidence = 96
            groups["supporting"] = [
                _fixture_evidence(
                    source="Philippine Department of Energy",
                    url="https://doe.gov.ph/",
                    domain="doe.gov.ph",
                    relationship="SUPPORTS",
                    tier=1,
                ),
                _fixture_evidence(
                    source="Reuters",
                    url="https://www.reuters.com/",
                    domain="reuters.com",
                    relationship="SUPPORTS",
                    tier=2,
                ),
            ]
        elif "sara duterte" in lowered:
            verdict = "VERIFIED"
            confidence = 92
            groups["supporting"] = [
                _fixture_evidence(
                    source="Daily Tribune",
                    url="https://tribune.net.ph/",
                    domain="tribune.net.ph",
                    relationship="SUPPORTS",
                    tier=2,
                )
            ]
        else:
            verdict = "FALSE"
            confidence = 97
            groups["contradicting"] = [
                _fixture_evidence(
                    source="International Criminal Court",
                    url="https://www.icc-cpi.int/",
                    domain="icc-cpi.int",
                    relationship="CONTRADICTS",
                    tier=1,
                ),
                _fixture_evidence(
                    source="VERA Files",
                    url="https://verafiles.org/",
                    domain="verafiles.org",
                    relationship="CONTRADICTS",
                    tier=1,
                ),
            ]
        return {
            "status": "SUCCESS",
            "verdict": verdict,
            "confidence": confidence,
            "explanation": "Evidence was evaluated for this regression fixture.",
            "search": {"queries": [claim, f'"{claim}"', f"{claim} fact check"]},
            "evidence": groups,
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fixture_name", "expected_classification", "expected_content_type"),
    [
        ("real-doe-nuclear.png", "REAL", "FACTUAL_NEWS"),
        ("quote-sara-duterte.png", "QUOTE", "DIRECT_QUOTE"),
        ("fake-icc-duterte.png", "FAKE", "ATTRIBUTED_QUOTE"),
    ],
)
async def test_three_supplied_images_cover_public_classifications(
    fixture_name,
    expected_classification,
    expected_content_type,
) -> None:
    settings = SimpleNamespace(
        paddleocr_language="en",
        image_ocr_max_pixels=6_000_000,
        image_ocr_max_source_pixels=80_000_000,
        ocr_medium_confidence=0.75,
        ocr_high_confidence=0.90,
        image_max_concurrent_claims=2,
    )
    checker = PhilippineImageFactChecker(
        settings,
        ocr_engine=OcrMustRemainFallback(),
        vision_client=ThreeFixtureVisionClient(),
        news_verifier=ThreeFixtureNewsVerifier(),
    )

    report = await checker.analyze((FIXTURE_DIRECTORY / fixture_name).read_bytes())
    validated = PhilippineImageFactCheckResponse.model_validate(report)

    assert validated.classification == expected_classification
    assert validated.content_type == expected_content_type
    assert validated.claims
    assert validated.ocr.primary_engine == "Gemini Vision"
    assert validated.ocr.raw_paddle_text == ""


class FacebookPolicyVisionClient:
    configured = True

    async def understand(self, image, *, fallback_ocr_text="", initial=None):
        del image
        assert not fallback_ocr_text
        assert initial is None
        headline = (
            "President Marcos, bukas sa posibilidad ng pagbabawal sa Facebook sa Pilipinas "
            "ayon kay Castro."
        )
        return _vision_record(
            headline=headline,
            body_text=headline,
            people=["President Ferdinand Marcos Jr.", "Claire Castro"],
            organizations=["Facebook"],
            locations=["Philippines"],
            content_type="FACTUAL_NEWS",
            atomic_claims=[headline],
        )


class FacebookPolicyNewsVerifier:
    async def verify(self, claim):
        assert claim == (
            "President Marcos, bukas sa posibilidad ng pagbabawal sa Facebook sa Pilipinas "
            "ayon kay Castro."
        )
        supporting = [
            _fixture_evidence(
                source="Presidential Communications Office",
                url="https://pco.gov.ph/news_releases/policy-platform-restrictions/",
                domain="pco.gov.ph",
                relationship="SUPPORTS",
                tier=1,
            ),
            _fixture_evidence(
                source="GMA News",
                url="https://gmanetwork.com/news/palace-open-social-media-ban/story/",
                domain="gmanetwork.com",
                relationship="SUPPORTS",
                tier=2,
            ),
            _fixture_evidence(
                source="Inquirer.net",
                url="https://inquirer.net/no-facebook-ban-for-now/",
                domain="inquirer.net",
                relationship="SUPPORTS",
                tier=1,
            ),
        ]
        for item in supporting:
            item["explanation"] = (
                "The source matches the entities and attribution and describes only policy "
                "consideration, not an ordered or implemented ban."
            )
        return {
            "status": "SUCCESS",
            "verdict": "VERIFIED",
            "confidence": 96,
            "explanation": "Multiple independent credible reports support the conditional claim.",
            "context_warnings": [
                "The government was only open to studying the possibility; no ban was ordered."
            ],
            "search": {
                "queries": [
                    claim,
                    "President Marcos Facebook open possible ban Castro",
                    "Marcos considering Facebook restrictions Philippines Claire Castro",
                ]
            },
            "evidence": {
                "supporting": supporting,
                "contradicting": [],
                "related": [],
                "debunks": [],
            },
        }


@pytest.mark.asyncio
async def test_exact_filipino_facebook_headline_returns_real_with_context_and_sources() -> None:
    settings = SimpleNamespace(
        paddleocr_language="en",
        image_ocr_max_pixels=6_000_000,
        image_ocr_max_source_pixels=80_000_000,
        ocr_medium_confidence=0.75,
        ocr_high_confidence=0.90,
        image_max_concurrent_claims=2,
    )
    checker = PhilippineImageFactChecker(
        settings,
        ocr_engine=OcrMustRemainFallback(),
        vision_client=FacebookPolicyVisionClient(),
        news_verifier=FacebookPolicyNewsVerifier(),
    )

    report = await checker.analyze((FIXTURE_DIRECTORY / "real-doe-nuclear.png").read_bytes())
    validated = PhilippineImageFactCheckResponse.model_validate(report)

    assert validated.classification == "REAL"
    assert validated.content_type == "FACTUAL_NEWS"
    assert validated.key_context == [
        "The government was only open to studying the possibility; no ban was ordered."
    ]
    assert {item.source for item in validated.claims[0].evidence} == {
        "Presidential Communications Office",
        "GMA News",
        "Inquirer.net",
    }
    assert validated.claims[0].evidence[0].source_type == "PRIMARY"
    assert validated.claims[0].claim_type == "POLICY"
    assert {item.normalized_value for item in validated.entities} >= {
        "Claire Castro",
        "Facebook",
        "Philippines",
    }
