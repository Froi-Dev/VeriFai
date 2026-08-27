from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from app.services.news_verifier import (
    EvidenceAnalysis,
    NewsSearchClient,
    NewsVerifier,
    SearchOutcome,
    SearchResult,
    _extract_result_image,
    _headline_match_and_mutation,
    _relationship,
    clean_claim_text,
    extract_claim_features,
    generate_search_queries,
    normalize_search_text,
    normalize_url,
    score_initial_relevance,
)


def test_claim_cleanup_preserves_facts_and_reduces_noise() -> None:
    raw = "<b>BREAKING!!!!!</b>   Marcos   RESIGNS\n\nAS PRESIDENT!!!!"

    assert clean_claim_text(raw) == "BREAKING! Marcos RESIGNS AS PRESIDENT!"
    assert normalize_search_text(raw) == "marcos resigns president"


def test_search_normalization_preserves_negation() -> None:
    assert normalize_search_text("VIRAL: Marcos has NOT resigned") == "marcos not resigned"


def test_query_generation_uses_multiple_deterministic_views() -> None:
    cleaned = clean_claim_text("Ferdinand Marcos Jr. resigns as President today")
    features = extract_claim_features(cleaned)

    queries = generate_search_queries(cleaned, features)

    assert 4 <= len(queries) <= 8
    assert any("fact check" in query for query in queries)
    assert any("resign" in query.lower() for query in queries)


def test_query_generation_searches_without_an_appended_headline_ending() -> None:
    cleaned = clean_claim_text(
        "DILG wants PNP access to homes of illegal firearm owners for inspections "
        "to kill people"
    )
    features = extract_claim_features(cleaned)

    queries = generate_search_queries(cleaned, features)

    assert '"dilg wants pnp access homes illegal firearm owners inspections"' in queries[:3]


def test_normalize_url_removes_tracking_and_fragment() -> None:
    normalized = normalize_url(
        "https://Example.com/story?id=123&utm_source=facebook&fbclid=abc#comments"
    )

    assert normalized == "https://example.com/story?id=123"


def test_normalize_url_preserves_redirect_significant_trailing_slash() -> None:
    assert normalize_url("https://example.com/story/") == "https://example.com/story/"


def test_extract_result_image_uses_google_thumbnail() -> None:
    item = {
        "pagemap": {
            "cse_thumbnail": [
                {"src": "https://cdn.example.com/news/photo.jpg?utm_source=search"}
            ]
        }
    }

    assert _extract_result_image(item) == "https://cdn.example.com/news/photo.jpg"


def test_extract_result_image_supports_nested_and_protocol_relative_images() -> None:
    item = {"images": [{"src": "//cdn.example.com/news/photo.jpg"}]}

    assert _extract_result_image(item) == "https://cdn.example.com/news/photo.jpg"


def test_appended_words_are_detected_as_a_headline_mutation() -> None:
    claim = (
        "DILG wants PNP access to homes of illegal firearm owners for inspections "
        "to kill people"
    )
    headline = "DILG wants PNP access to homes of illegal firearm owners for inspections"

    score, mutation = _headline_match_and_mutation(claim, headline)

    assert score >= 90
    assert mutation is not None
    assert "kill people" in mutation


def test_underlying_headline_outranks_an_unrelated_shared_event() -> None:
    claim_text = (
        "DILG wants PNP access to homes of illegal firearm owners for inspections "
        "to kill people"
    )
    claim = extract_claim_features(claim_text)
    real_headline = SearchResult(
        title="DILG wants PNP access to homes of illegal firearm owners for inspections",
        url="https://example.com/firearm-inspections",
        domain="example.com",
        snippet="The proposal would allow police inspections of unlicensed firearms.",
        published_date=None,
        provider="test",
        query=claim_text,
    )
    unrelated_death = SearchResult(
        title="DILG chief: PNP officer's death suggests suicide",
        url="https://example.com/pnp-officer-death",
        domain="example.com",
        snippet="The DILG discussed a PNP officer who was found dead.",
        published_date=None,
        provider="test",
        query=claim_text,
    )

    real_score = score_initial_relevance(claim, normalize_search_text(claim_text), real_headline)
    unrelated_score = score_initial_relevance(
        claim, normalize_search_text(claim_text), unrelated_death
    )

    assert real_score > unrelated_score


def test_policy_event_words_do_not_need_to_be_adjacent() -> None:
    claim = extract_claim_features(
        "Ferdinand Marcos Jr. signed the Maharlika Investment Fund Act into law."
    )

    assert "POLICY_APPROVED" in claim.event_categories


def test_death_claim_is_contradicted_by_alive_report() -> None:
    claim = extract_claim_features("Senator Juan Dela Cruz died today")

    relationship, rules, transformation = _relationship(
        claim,
        "Doctors said Senator Juan Dela Cruz remains alive and in stable condition.",
        72,
    )

    assert relationship == "CONTRADICTS"
    assert rules
    assert transformation is None


def test_explicit_fact_check_is_classified_as_debunk() -> None:
    claim = extract_claim_features("Mayor Ana Santos was arrested")

    relationship, _, _ = _relationship(
        claim,
        "Fact check: The false claim that Mayor Ana Santos was arrested is not true.",
        80,
    )

    assert relationship == "DEBUNKS"


def test_unrelated_footer_language_does_not_trigger_debunk() -> None:
    claim = extract_claim_features(
        "Ferdinand Marcos Jr. signed the Maharlika Investment Fund Act into law."
    )
    document = (
        "Marcos signs Maharlika Investment Fund into law. "
        "President Marcos signed the measure after Congress approved it. "
        + ("Implementation details and fund safeguards were discussed. " * 50)
        + "More stories: officials dismiss an unrelated meeting as fake news."
    )

    relationship, _, _ = _relationship(claim, document, 82)

    assert relationship == "SUPPORTS"


def test_signed_law_is_not_contradicted_by_proposal_background() -> None:
    claim = extract_claim_features("President Santos signed the Public Fund Act into law")
    document = (
        "President Santos signs Public Fund Act into law. The measure began as a proposal "
        "in Congress before both chambers approved it."
    )

    relationship, _, _ = _relationship(claim, document, 78)

    assert relationship == "SUPPORTS"


def test_scheduled_signing_is_related_not_supporting() -> None:
    claim = extract_claim_features("President Santos signed the Public Fund Act into law")
    document = "President Santos is scheduled to sign the Public Fund bill next Tuesday."

    relationship, _, transformation = _relationship(claim, document, 70)

    assert relationship == "RELATED"
    assert transformation is not None


def test_same_event_in_a_different_location_is_irrelevant() -> None:
    claim_text = (
        "Palace says there have been no reported Filipino casualties from the "
        "devastating flash floods in Nepal as of Thursday morning."
    )
    claim = extract_claim_features(claim_text)
    texas_report = SearchResult(
        title="Palace: No Filipinos affected in Texas flash floods",
        url="https://inquirer.net/texas-floods",
        domain="inquirer.net",
        snippet="There are no reported Filipino casualties in the Texas flash floods.",
        published_date=None,
        provider="test",
        query=claim_text,
    )

    assert claim.locations == ["Nepal"]
    assert score_initial_relevance(claim, normalize_search_text(claim_text), texas_report) < 40
    relationship, rules, _ = _relationship(
        claim,
        f"{texas_report.title} {texas_report.snippet}",
        70,
    )

    assert relationship == "IRRELEVANT"
    assert rules == ["The report names a different location."]


def test_same_event_in_the_same_location_can_support_the_claim() -> None:
    claim = extract_claim_features(
        "Palace says no Filipino casualties were reported after flash floods in Nepal."
    )

    relationship, _, _ = _relationship(
        claim,
        "Palace: No Filipino casualties reported in Nepal flash floods.",
        72,
    )

    assert relationship == "SUPPORTS"


class EmptySearchClient:
    def __init__(self, *, succeeded: bool) -> None:
        self.succeeded = succeeded

    async def search(
        self,
        queries: list[str],
        *,
        restricted_domains: list[str] | None,
        result_filter=None,
    ):
        del queries, restricted_domains, result_filter
        return SearchOutcome([], ["searchapi"], self.succeeded)


class RecordingSearchClient(EmptySearchClient):
    def __init__(self) -> None:
        super().__init__(succeeded=True)
        self.restricted_domains: list[str] | None | object = object()

    async def search(
        self,
        queries: list[str],
        *,
        restricted_domains: list[str] | None,
        result_filter=None,
    ):
        self.restricted_domains = restricted_domains
        return await super().search(
            queries,
            restricted_domains=restricted_domains,
            result_filter=result_filter,
        )


class NoopScraper:
    async def scrape(self, url: str):
        raise AssertionError(f"Scraper should not be called for {url}")


class NoResultScraper:
    async def scrape(self, url: str):
        del url
        return None


class SimulatedFallbackSearchClient(NewsSearchClient):
    def _provider_is_configured(self, provider: str) -> bool:
        return provider in {"searchapi", "serper"}

    async def _search_provider(self, client, provider: str, query: str):
        del client
        if provider == "searchapi":
            raise httpx.ReadTimeout("simulated provider timeout")
        return [
            SearchResult(
                title="Mayor Santos arrested on corruption charges",
                url="https://rappler.com/example-story",
                domain="rappler.com",
                snippet="Mayor Santos was arrested Tuesday.",
                published_date=None,
                provider=provider,
                query=query,
            )
        ]


def verifier_settings() -> SimpleNamespace:
    return SimpleNamespace(
        philippine_news_domain_list=[
            "abs-cbn.com",
            "gmanetwork.com",
            "inquirer.net",
            "mb.com.ph",
            "philstar.com",
            "pna.gov.ph",
            "rappler.com",
            "sunstar.com.ph",
        ],
        trusted_news_domain_list=[
            "rappler.com",
            "inquirer.net",
            "abs-cbn.com",
            "cnn.com",
        ],
        news_tier_2_domain_list=["gmanetwork.com", "reuters.com"],
        news_min_relevant_results=3,
        news_max_search_results=20,
        news_relevance_threshold=40,
        news_max_articles_to_scrape=6,
        news_debug=False,
        news_old_story_days=30,
    )


@pytest.mark.asyncio
async def test_provider_timeout_falls_back_to_next_provider() -> None:
    settings = SimpleNamespace(
        news_search_provider_list=["searchapi", "serper"],
        news_search_timeout_seconds=2,
        news_min_relevant_results=1,
        news_max_search_results=10,
    )
    client = SimulatedFallbackSearchClient(settings)

    outcome = await client.search(
        ["Mayor Santos arrested"],
        restricted_domains=["rappler.com"],
    )

    assert outcome.any_provider_succeeded is True
    assert outcome.providers_used == ["searchapi", "serper"]
    assert outcome.results[0].provider == "serper"


@pytest.mark.asyncio
async def test_no_search_results_is_unverified_not_false() -> None:
    verifier = NewsVerifier(
        verifier_settings(),
        search_client=EmptySearchClient(succeeded=True),
        scraper=NoopScraper(),
    )

    result = await verifier.verify("Marcos resigns as President today")

    assert result["status"] == "SUCCESS"
    assert result["verdict"] == "UNVERIFIED"
    assert "does not mean the claim is false" in result["explanation"]


@pytest.mark.asyncio
async def test_verifier_searches_all_configured_philippine_outlets() -> None:
    search_client = RecordingSearchClient()
    verifier = NewsVerifier(
        verifier_settings(),
        search_client=search_client,
        scraper=NoopScraper(),
    )

    result = await verifier.verify("Marcos resigns as President today")

    assert search_client.restricted_domains == verifier_settings().philippine_news_domain_list
    assert (
        result["search"]["outlet_domains_searched"]
        == verifier_settings().philippine_news_domain_list
    )


@pytest.mark.asyncio
async def test_general_web_results_are_excluded_from_news_evidence() -> None:
    claim = "Mayor Santos arrested on corruption charges"

    class MixedWebSearchClient:
        async def search(self, queries, *, restricted_domains, result_filter=None):
            del queries, restricted_domains, result_filter
            return SearchOutcome(
                [
                    SearchResult(
                        title=claim,
                        url="https://ultimate-guitar.com/mayor-santos-chords",
                        domain="ultimate-guitar.com",
                        snippet="Chords and tabs for Mayor Santos.",
                        published_date=None,
                        provider="test",
                        query=claim,
                    ),
                    SearchResult(
                        title=claim,
                        url="https://rappler.com/mayor-santos-arrested",
                        domain="rappler.com",
                        snippet="Mayor Santos was arrested after a corruption investigation.",
                        published_date=None,
                        provider="test",
                        query=claim,
                    ),
                ],
                ["test"],
                True,
            )

    verifier = NewsVerifier(
        verifier_settings(),
        search_client=MixedWebSearchClient(),
        scraper=NoResultScraper(),
    )

    result = await verifier.verify(claim)
    evidence = [item for group in result["evidence"].values() for item in group]

    assert result["search"]["total_results"] == 1
    assert evidence
    assert {item["domain"] for item in evidence} == {"rappler.com"}


@pytest.mark.asyncio
async def test_altered_headline_returns_the_underlying_report_as_closest_match() -> None:
    claim = (
        "DILG wants PNP access to homes of illegal firearm owners for inspections "
        "to kill people"
    )

    class AlteredHeadlineSearchClient:
        async def search(self, queries, *, restricted_domains, result_filter=None):
            del queries, restricted_domains, result_filter
            return SearchOutcome(
                [
                    SearchResult(
                        title=(
                            "DILG wants PNP access to homes of illegal firearm owners "
                            "for inspections"
                        ),
                        url="https://gmanetwork.com/news/firearm-inspections",
                        domain="gmanetwork.com",
                        snippet=(
                            "The DILG proposed inspections involving owners of illegal "
                            "firearms."
                        ),
                        published_date=None,
                        provider="test",
                        query=claim,
                        image_url="https://cdn.example.com/firearms.jpg",
                    ),
                    SearchResult(
                        title="DILG chief: PNP officer's death suggests suicide",
                        url="https://inquirer.net/pnp-officer-death",
                        domain="inquirer.net",
                        snippet="The DILG discussed a PNP officer who was found dead.",
                        published_date=None,
                        provider="test",
                        query=claim,
                    ),
                ],
                ["test"],
                True,
            )

    verifier = NewsVerifier(
        verifier_settings(),
        search_client=AlteredHeadlineSearchClient(),
        scraper=NoResultScraper(),
    )

    result = await verifier.verify(claim)

    assert result["verdict"] == "MISLEADING"
    assert result["closest_real_story"]["title"].endswith("for inspections")
    assert "kill people" in result["closest_real_story"]["explanation"]
    assert result["closest_real_story"]["image_url"].endswith("firearms.jpg")
    assert result["evidence"]["supporting"] == []


def test_credible_related_story_makes_specific_claim_likely_false() -> None:
    verifier = NewsVerifier(
        verifier_settings(),
        search_client=EmptySearchClient(succeeded=True),
        scraper=NoopScraper(),
    )
    search_result = SearchResult(
        title="BBM visits Pangasinan",
        url="https://rappler.com/bbm-pangasinan-visit",
        domain="rappler.com",
        snippet="The president attended an event in Pangasinan.",
        published_date=None,
        provider="test",
        query="BBM Pangasinan",
        image_url="https://cdn.example.com/bbm.jpg",
    )
    analysis = EvidenceAnalysis(
        result=search_result,
        article=None,
        relationship="RELATED",
        similarity=45,
        evidence_score=60,
        source_tier=1,
        recency_score=55,
        explanation="This report covers a related visit but no helicopter crash.",
    )

    verdict, confidence, explanation = verifier._decide_verdict(
        [analysis],
        extract_claim_features("BBM was in a helicopter crash in Pangasinan"),
        datetime.now(UTC),
    )

    assert verdict == "LIKELY_FALSE"
    assert confidence == 52
    assert "likely false" in explanation


@pytest.mark.asyncio
async def test_total_provider_failure_is_search_unavailable() -> None:
    verifier = NewsVerifier(
        verifier_settings(),
        search_client=EmptySearchClient(succeeded=False),
        scraper=NoopScraper(),
    )

    result = await verifier.verify("Marcos resigns as President today")

    assert result["status"] == "SEARCH_UNAVAILABLE"
    assert result["verdict"] == "UNVERIFIED"
    assert result["confidence"] == 0
