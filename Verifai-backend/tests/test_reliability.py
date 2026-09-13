import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.FakeNewsAnalyzer.image_fact_checker import PhilippineImageFactChecker
from app.FakeNewsAnalyzer.news_verifier import (
    ClaimFeatures,
    EvidenceAnalysis,
    NewsVerifier,
    SearchResult,
)
from app.Global.cache import ResultCache
from app.Global.middleware import RequestIdMiddleware


@pytest.mark.asyncio
async def test_result_cache_coalesces_simultaneous_misses() -> None:
    cache = ResultCache(None)
    calls = 0

    async def produce() -> dict[str, int]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"value": 42}

    results = await asyncio.gather(
        *(cache.get_or_compute("same-key", 60, produce) for _ in range(5))
    )

    assert calls == 1
    assert [value for value, _ in results] == [{"value": 42}] * 5
    assert sum(cache_hit for _, cache_hit in results) == 4


@pytest.mark.asyncio
async def test_result_cache_does_not_store_failed_analysis() -> None:
    cache = ResultCache(None)
    calls = 0

    async def produce() -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"status": "SEARCH_UNAVAILABLE"}

    for _ in range(2):
        _, cache_hit = await cache.get_or_compute(
            "failed-key",
            60,
            produce,
            cache_when=lambda value: value["status"] == "SUCCESS",
        )
        assert cache_hit is False

    assert calls == 2


def test_request_id_is_returned_and_valid_client_id_is_preserved() -> None:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as client:
        generated = client.get("/").headers["X-Request-ID"]
        supplied = client.get(
            "/", headers={"X-Request-ID": "support_ref_1234"}
        ).headers["X-Request-ID"]

    assert len(generated) == 32
    assert supplied == "support_ref_1234"


def test_evidence_is_ranked_deduplicated_and_capped() -> None:
    settings = SimpleNamespace(
        philippine_news_domain_list=[],
        trusted_news_domain_list=[],
        news_tier_2_domain_list=[],
        news_max_evidence_items=8,
        news_max_related_evidence=3,
        news_debug=False,
    )
    verifier = NewsVerifier(settings, search_client=object(), scraper=object())
    analyses = []
    for relationship, count in (("SUPPORTS", 3), ("RELATED", 7)):
        for index in range(count):
            domain = f"source-{relationship.lower()}-{index}.example"
            analyses.append(
                EvidenceAnalysis(
                    result=SearchResult(
                        title=f"{relationship[:3]}-{index}",
                        url=f"https://{domain}/story",
                        domain=domain,
                        snippet=f"Independent report {index}",
                        published_date=None,
                        provider="test",
                        query="claim",
                    ),
                    article=None,
                    relationship=relationship,
                    similarity=80 - index,
                    evidence_score=90 - index,
                    source_tier=2,
                    recency_score=80,
                    explanation="Relevant evidence.",
                )
            )

    response = verifier._response(
        status="SUCCESS",
        raw_text="claim",
        cleaned="claim",
        search_text="claim",
        features=ClaimFeatures([], [], [], [], [], []),
        verdict="LIKELY_TRUE",
        confidence=80,
        explanation="Supported.",
        analyses=analyses,
        queries=["claim"],
        providers_used=["test"],
        total_results=len(analyses),
        articles_scraped=0,
        debug_scores=[],
        rule_matches=[],
    )

    assert len(response["evidence"]["supporting"]) == 3
    assert len(response["evidence"]["related"]) == 3
    assert sum(len(group) for group in response["evidence"].values()) == 6


@pytest.mark.asyncio
async def test_image_claim_limit_is_shared_across_simultaneous_analyses() -> None:
    class TrackingVerifier:
        active = 0
        maximum = 0

        async def verify(self, claim: str) -> dict:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return {
                "status": "SEARCH_UNAVAILABLE",
                "verdict": "UNVERIFIED",
                "confidence": 0,
                "explanation": "Unavailable.",
                "search": {"queries": [claim]},
                "evidence": {
                    "supporting": [],
                    "contradicting": [],
                    "related": [],
                    "debunks": [],
                },
            }

    verifier = TrackingVerifier()
    checker = PhilippineImageFactChecker(
        SimpleNamespace(image_max_concurrent_claims=2),
        ocr_engine=object(),
        vision_client=object(),
        news_verifier=verifier,
    )

    await asyncio.gather(
        checker._verify_claims(["a", "b", "c"], "HIGH", []),
        checker._verify_claims(["d", "e", "f"], "HIGH", []),
    )

    assert verifier.maximum == 2
