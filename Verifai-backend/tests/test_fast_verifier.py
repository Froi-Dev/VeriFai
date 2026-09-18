import json
import time
from io import BytesIO
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

from app.FakeNewsAnalyzer.fast_verifier import FastNewsVerifier
from app.FakeNewsAnalyzer.image_fact_checker import GeminiVisionClient, PhilippineImageFactChecker
from app.FakeNewsAnalyzer.news_verifier import (
    NewsSearchClient,
    NewsVerifier,
    SearchOutcome,
    SearchResult,
)
from app.Global.config import settings
from app.Global.schemas import ImageVerificationResponse, NewsVerificationResponse

CLAIM = "President Marcos signed the Maharlika Investment Fund Act into law."
URL = "https://www.pna.gov.ph/articles/1200000"


def outcome(success=True, empty=False):
    return SearchOutcome(
        []
        if empty
        else [
            SearchResult(
                title=CLAIM,
                url=URL,
                domain="www.pna.gov.ph",
                snippet=CLAIM,
                published_date=None,
                provider="serper",
                query=CLAIM,
            )
        ],
        ["serper"],
        success,
    )


def decision(verdict="VERIFIED", url=URL):
    return json.dumps(
        {
            "verdict": verdict,
            "confidence": 90,
            "explanation": "The source confirms the claim.",
            "sources": [{"title": "PNA", "url": url, "relationship": "SUPPORTS"}],
            "reasoning": "The provided snippet reports the law signing.",
        }
    )


@pytest.fixture
def setup_engine():
    config = settings.model_copy(update={"news_audit_log_enabled": False})
    fallback = NewsVerifier(config, search_client=AsyncMock(), scraper=AsyncMock())
    fallback.verify = AsyncMock(return_value={"fallback": True})
    gemini = AsyncMock()
    gemini.generate.return_value = decision()
    search = AsyncMock()
    search.search.return_value = outcome()
    engine = FastNewsVerifier(config, gemini_client=gemini, search_client=search, fallback=fallback)
    return engine, gemini, search, fallback


@pytest.mark.asyncio
async def test_fast_contract_uses_snippets_without_scraping(setup_engine):
    engine, gemini, search, fallback = setup_engine
    result = NewsVerificationResponse.model_validate(await engine.verify(CLAIM))
    assert result.verdict == "VERIFIED"
    assert result.adjudication_source == "llm"
    assert result.search.articles_scraped == 0
    assert result.evidence.supporting[0].url == URL
    assert result.search.outlet_domains_searched == []
    search.search.assert_awaited_once_with([CLAIM], restricted_domains=None)
    assert gemini.generate.call_args.kwargs["model"] == "gemini-3.5-flash-lite"
    fallback.verify.assert_not_awaited()
    fallback.scraper.scrape.assert_not_awaited()


@pytest.mark.asyncio
async def test_separate_claims_keep_verdicts_and_plain_explanations(setup_engine):
    engine, gemini, _, _ = setup_engine
    payload = json.loads(decision())
    payload["claim_results"] = [
        {
            "claim": "The law was signed.",
            "verdict": "VERIFIED",
            "explanation": "The signing is substantiated by the report.",
            "source_urls": [URL],
        },
        {
            "claim": "The law took effect yesterday.",
            "verdict": "UNVERIFIED",
            "explanation": "The date is unsubstantiated.",
            "source_urls": [],
        },
    ]
    gemini.generate.return_value = json.dumps(payload)
    response = await engine.verify("The law was signed and took effect yesterday.")
    parsed = NewsVerificationResponse.model_validate(response)
    assert len(parsed.claim_results) == 2
    assert parsed.atomic_claims == [c.claim for c in parsed.claim_results]
    assert [c.verdict for c in parsed.claim_results] == ["VERIFIED", "UNVERIFIED"]
    assert "substantiated" not in json.dumps(response)
    from app.FakeNewsAnalyzer.image_fact_checker import _build_image_response

    image = ImageVerificationResponse.model_validate(
        _build_image_response(
            {"cleaned_text": response["original_text"]},
            response,
            {},
        )
    )
    assert [c["verdict"] for c in image.claims] == ["VERIFIED", "UNVERIFIED"]


@pytest.mark.asyncio
async def test_claim_without_real_citation_is_not_labelled_true(setup_engine):
    engine, gemini, _, _ = setup_engine
    payload = json.loads(decision())
    payload["claim_results"] = [
        {
            "claim": "The law was signed.",
            "verdict": "VERIFIED",
            "explanation": "It happened.",
            "source_urls": ["https://invented.example/story"],
        }
    ]
    gemini.generate.return_value = json.dumps(payload)
    response = await engine.verify(CLAIM)
    assert response["claim_results"][0]["verdict"] == "UNVERIFIED"
    assert response["claim_results"][0]["source_urls"] == []


@pytest.mark.asyncio
async def test_no_results_is_unverified_without_model_or_scraper(setup_engine):
    engine, gemini, search, fallback = setup_engine
    search.search.return_value = outcome(empty=True)
    result = NewsVerificationResponse.model_validate(await engine.verify(CLAIM))
    assert result.verdict == "UNVERIFIED"
    assert result.status == "SUCCESS"
    gemini.generate.assert_not_awaited()
    fallback.verify.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["search", "gemini"])
async def test_exhaustion_uses_deterministic_fallback(setup_engine, failure):
    engine, gemini, search, fallback = setup_engine
    if failure == "search":
        search.search.return_value = outcome(success=False, empty=True)
    else:
        gemini.generate.side_effect = ValueError("No usable model response")
    assert await engine.verify(CLAIM) == {"fallback": True}
    fallback.verify.assert_awaited_once_with(CLAIM)
    assert fallback.adjudicator is None


@pytest.mark.asyncio
async def test_hallucinated_citation_cannot_verify(setup_engine):
    engine, gemini, _, fallback = setup_engine
    gemini.generate.return_value = decision(url="https://invented.example/story")
    result = await engine.verify(CLAIM)
    assert result["verdict"] == "UNVERIFIED"
    assert not result["evidence"]["supporting"]
    fallback.verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_image_uses_headline_and_preserves_response(setup_engine):
    engine, gemini, _, fallback = setup_engine
    gemini.configured = True
    gemini.transcribe_structured.return_value = {
        "raw_text": "Follow us\n" + CLAIM + "\nA different story in the caption",
        "blocks": [
            {"text": "Follow us", "type": "ui_element"},
            {"text": CLAIM, "type": "headline"},
            {"text": "A different story in the caption", "type": "caption"},
        ],
        "confidence": 0.98,
    }
    paddle = AsyncMock()
    checker = PhilippineImageFactChecker(
        engine.settings,
        vision_client=gemini,
        news_verifier=engine,
        ocr_engine=paddle,
    )
    image = BytesIO()
    Image.new("RGB", (100, 100)).save(image, format="PNG")
    result = ImageVerificationResponse.model_validate(await checker.analyze(image.getvalue()))
    assert result.status == "success"
    assert result.ocr.cleaned_text == CLAIM
    assert "Follow us" in result.ocr.raw_text
    assert result.metadata.verification_engine == "FastNewsVerifier"
    NewsVerificationResponse.model_validate(result.verification)
    gemini.generate.assert_awaited_once()
    paddle.transcribe.assert_not_called()
    fallback.verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_shared_key_rotation_cooldown_and_recovery(monkeypatch):
    config = settings.model_copy(update={"gemini_key_cooldown_seconds": 60})
    client = GeminiVisionClient(config)
    client.api_keys = ["limited", "good", "also-good"]
    now = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: now)
    calls = []

    def handler(request):
        key = request.headers["x-goog-api-key"]
        calls.append(key)
        if key == "limited":
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": decision()}]},
                    }
                ]
            },
        )

    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        for _ in range(4):
            await client.generate(None, "claim", model="gemini-3.5-flash-lite")
        assert calls == ["limited", "good", "good", "also-good", "good"]
        assert client._cooldowns["limited"] == now + 60
        now += 61
        assert "limited" in await client._available_keys()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_serper_failure_uses_searchapi(monkeypatch):
    from pydantic import SecretStr

    config = settings.model_copy(
        update={
            "serper_api_keys": SecretStr("test-serper"),
            "serper_api_key": None,
            "searchapi_api_key": SecretStr("test-searchapi"),
            "news_search_provider_order": "serper,searchapi",
            "news_min_relevant_results": 1,
        }
    )
    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "google.serper.dev":
            return httpx.Response(500)
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {"title": CLAIM, "link": URL, "snippet": CLAIM},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        search = NewsSearchClient(config, client=http)
        monkeypatch.setattr(search, "_provider_is_configured", lambda p: True)
        result = await search.search([CLAIM], restricted_domains=None)
    assert result.any_provider_succeeded
    assert result.results[0].url == URL
    assert calls == ["google.serper.dev", "www.searchapi.io"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["rate_limit", "invalid_json"])
async def test_all_gemini_keys_attempted_before_fallback(setup_engine, mode):
    engine, _, _, fallback = setup_engine
    client = GeminiVisionClient(engine.settings)
    client.api_keys = [f"test-key-{i}" for i in range(8)]
    calls = []

    def handler(request):
        calls.append(request.headers["x-goog-api-key"])
        if mode == "rate_limit":
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "not JSON"}]},
                    }
                ]
            },
        )

    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    engine.gemini_client = client
    try:
        assert await engine.verify(CLAIM) == {"fallback": True}
        assert calls == client.api_keys
        fallback.verify.assert_awaited_once()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_http_routes_preserve_contracts_and_cache(setup_engine, monkeypatch):
    from fastapi import FastAPI

    from app.FakeNewsAnalyzer import news
    from app.Global.cache import ResultCache
    from app.Global.dependencies import UserPrincipal, get_current_principal

    engine, gemini, _, _ = setup_engine
    gemini.configured = True
    gemini.transcribe_structured.return_value = {
        "raw_text": CLAIM,
        "blocks": [{"text": CLAIM, "type": "headline"}],
        "confidence": 0.99,
    }
    image_checker = PhilippineImageFactChecker(
        engine.settings,
        vision_client=gemini,
        news_verifier=engine,
    )
    monkeypatch.setattr(news, "news_verifier", engine)
    monkeypatch.setattr(news, "image_fact_checker", image_checker)
    monkeypatch.setattr(news, "result_cache", ResultCache(None))
    monkeypatch.setattr(news, "record_scan", lambda **kwargs: None)
    monkeypatch.setattr(news.limiter, "enabled", False)
    app = FastAPI()
    app.include_router(news.router, prefix="/api/v1")
    app.dependency_overrides[get_current_principal] = lambda: UserPrincipal(
        user_id=1,
        role="user",
    )
    image = BytesIO()
    Image.new("RGB", (100, 100)).save(image, format="PNG")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as http:
        for expected_cache in ("MISS", "HIT"):
            text_response = await http.post("/api/v1/news/verify", json={"text": CLAIM})
            image_response = await http.post(
                "/api/v1/news/verify-image",
                files={"image": ("news.png", image.getvalue(), "image/png")},
            )
            assert text_response.status_code == image_response.status_code == 200
            assert text_response.headers["X-Cache"] == expected_cache
            assert image_response.headers["X-Cache"] == expected_cache
            NewsVerificationResponse.model_validate(text_response.json())
            ImageVerificationResponse.model_validate(image_response.json())
    assert gemini.generate.await_count == 2
    gemini.transcribe_structured.assert_awaited_once()
