from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from app.FakeNewsAnalyzer.news_verifier import (
    EvidenceAnalysis,
    NewsSearchClient,
    NewsVerifier,
    SearchOutcome,
    SearchResult,
    _extract_result_image,
    _headline_match_and_mutation,
    _is_evidence_page,
    _relationship,
    _source_tier,
    clean_claim_text,
    extract_claim_features,
    generate_fact_check_queries,
    generate_quote_source_queries,
    generate_search_queries,
    normalize_search_text,
    normalize_url,
    parse_publisher_social_account,
    score_initial_relevance,
)


def test_claim_cleanup_preserves_facts_and_reduces_noise() -> None:
    raw = "<b>BREAKING!!!!!</b>   Marcos   RESIGNS\n\nAS PRESIDENT!!!!"

    assert clean_claim_text(raw) == "BREAKING! Marcos RESIGNS AS PRESIDENT!"
    assert normalize_search_text(raw) == "marcos resigns president"


def test_search_normalization_preserves_negation() -> None:
    assert normalize_search_text("VIRAL: Marcos has NOT resigned") == "marcos not resigned"


@pytest.mark.parametrize("phrase", ["next week", "susunod na linggo"])
def test_claim_features_preserve_relative_week_framing(phrase: str) -> None:
    features = extract_claim_features(f"Rodrigo Duterte will return {phrase}.")

    assert phrase in features.dates


def test_query_generation_uses_multiple_deterministic_views() -> None:
    cleaned = clean_claim_text("Ferdinand Marcos Jr. resigns as President today")
    features = extract_claim_features(cleaned)

    queries = generate_search_queries(cleaned, features)

    assert 4 <= len(queries) <= 10
    assert any("fact check" in query for query in queries)
    assert any("resign" in query.lower() for query in queries)


def test_query_generation_prioritizes_quote_despite_copied_page_noise() -> None:
    paragraph = (
        "Faster Filipinos should \u201cshed our defeatist mindset,\u201d a Philippine Coast "
        "Guard official said in the West Philippine Sea dispute."
    )
    features = extract_claim_features(paragraph)

    queries = generate_search_queries(paragraph, features)

    assert '"shed our defeatist mindset"' in queries[:3]


def test_matching_quoted_search_result_survives_initial_relevance_filter() -> None:
    paragraph = (
        "Faster Filipinos should \u201cshed our defeatist mindset,\u201d a Philippine Coast "
        "Guard official said in the West Philippine Sea dispute."
    )
    features = extract_claim_features(paragraph)
    result = SearchResult(
        title="West PH Sea: Tarriela urges Filipinos to shed 'defeatist mindset'",
        url="https://inquirer.net/defeatist-mindset",
        domain="inquirer.net",
        snippet=(
            "Let us shed our defeatist mindset, because defeatism never represented what "
            "our heroes stood for, Tarriela said."
        ),
        published_date="2026-08-31",
        provider="test",
        query='"shed our defeatist mindset" (site:inquirer.net)',
    )

    score = score_initial_relevance(features, normalize_search_text(paragraph), result)

    assert score >= 40


def test_fact_check_query_runs_within_bounded_provider_limit() -> None:
    cleaned = clean_claim_text(
        "President Donald Tram binisita ang ating pangulo at nangako na papalayain Duterte Forever"
    )
    queries = generate_search_queries(cleaned, extract_claim_features(cleaned))

    assert any("fact check" in query for query in queries[:5])


def test_each_philippine_fact_check_archive_gets_a_targeted_query() -> None:
    queries = generate_fact_check_queries(
        "Duterte is returning from ICC custody",
        ["verafiles.org", "rappler.com", "tsek.ph"],
    )

    assert queries == [
        "duterte returning icc custody fact check",
        "site:verafiles.org/articles duterte returning icc custody",
        "site:rappler.com/newsbreak/fact-check duterte returning icc custody",
        "site:tsek.ph duterte returning icc custody",
    ]


def test_quote_source_query_pairs_distinctive_words_with_speaker() -> None:
    cleaned = clean_claim_text(
        "'Pag may nangyaring di maganda sa buhay nyo, isipin nyo na lang na mas matindi "
        "yung nangyari sa buhay ko VP Sara Duterte"
    )
    features = extract_claim_features(cleaned)

    queries = generate_quote_source_queries(cleaned, features)

    assert '"mas matindi" "buhay ko"' in queries[0]
    assert "VP Sara Duterte" in queries[0]


@pytest.mark.parametrize(
    ("url", "domain", "usable"),
    [
        ("https://facebook.com/example/posts/1", "facebook.com", False),
        ("https://www.youtube.com/channel/UClL_VSvGY3RB98YEdkqwItw", "youtube.com", False),
        ("https://balita.mb.com.ph/author/13/?pgno=49", "balita.mb.com.ph", False),
        ("https://apnews.com/hub/donald-trump", "apnews.com", False),
        ("https://verafiles.org/articles/fact-check-example", "verafiles.org", True),
    ],
)
def test_only_article_pages_are_used_as_news_evidence(url: str, domain: str, usable: bool) -> None:
    result = SearchResult(
        title="Result",
        url=url,
        domain=domain,
        snippet="",
        published_date=None,
        provider="test",
        query="test",
    )

    assert _is_evidence_page(result) is usable


@pytest.mark.parametrize("domain", ["verafiles.org", "rappler.com", "tsek.ph", "pco.gov.ph"])
def test_philippine_fact_check_organizations_are_top_tier(domain: str) -> None:
    assert _source_tier(domain, verifier_settings()) == 1


def test_quote_reporting_sources_are_credible_secondary_sources() -> None:
    settings = verifier_settings()
    settings.news_tier_2_domain_list.extend(["tribune.net.ph", "smninewschannel.com"])

    assert _source_tier("tribune.net.ph", settings) == 2
    assert _source_tier("smninewschannel.com", settings) == 2


def test_query_generation_searches_without_an_appended_headline_ending() -> None:
    cleaned = clean_claim_text(
        "DILG wants PNP access to homes of illegal firearm owners for inspections to kill people"
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
            "cse_thumbnail": [{"src": "https://cdn.example.com/news/photo.jpg?utm_source=search"}]
        }
    }

    assert _extract_result_image(item) == "https://cdn.example.com/news/photo.jpg"


def test_extract_result_image_supports_nested_and_protocol_relative_images() -> None:
    item = {"images": [{"src": "//cdn.example.com/news/photo.jpg"}]}

    assert _extract_result_image(item) == "https://cdn.example.com/news/photo.jpg"


def test_appended_words_are_detected_as_a_headline_mutation() -> None:
    claim = (
        "DILG wants PNP access to homes of illegal firearm owners for inspections to kill people"
    )
    headline = "DILG wants PNP access to homes of illegal firearm owners for inspections"

    score, mutation = _headline_match_and_mutation(claim, headline)

    assert score >= 90
    assert mutation is not None
    assert "kill people" in mutation


def test_search_engine_ellipsis_is_not_treated_as_an_altered_headline() -> None:
    claim = "VP Duterte trial: Prosecution 'willing to wait' for ill-stricken Fajarda"
    truncated_result = (
        "VP Duterte trial: Prosecution 'willing to wait' for ill-stricken ..."
    )

    score, mutation = _headline_match_and_mutation(claim, truncated_result)

    assert score >= 90
    assert mutation is None


def test_underlying_headline_outranks_an_unrelated_shared_event() -> None:
    claim_text = (
        "DILG wants PNP access to homes of illegal firearm owners for inspections to kill people"
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


def test_filipino_policy_consideration_generates_english_queries_in_first_wave() -> None:
    headline = (
        "President Marcos, bukas sa posibilidad ng pagbabawal sa Facebook sa Pilipinas "
        "ayon kay Castro."
    )
    features = extract_claim_features(headline)

    queries = generate_search_queries(headline, features)

    assert "POLICY_CONSIDERATION" in features.event_categories
    assert features.attributed_entity == "Claire Castro"
    assert extract_claim_features(headline.replace("ayon kay", "Ayon kay")).attributed_entity == (
        "Claire Castro"
    )
    # Raw claim is now prioritized first, so English semantic queries appear
    # slightly later. They must still be in the first wave of queries.
    assert "President Marcos Facebook open possible ban Castro" in queries[:5]
    assert "Marcos considering Facebook restrictions Philippines Claire Castro" in queries[:5]


def test_policy_consideration_is_not_confused_with_an_ordered_ban() -> None:
    consideration = extract_claim_features(
        "President Marcos is open to considering a possible Facebook ban, according to "
        "Claire Castro."
    )
    ordered = (
        "President Marcos ordered Facebook banned, Palace Press Officer Claire Castro "
        "announced. The restriction was implemented immediately."
    )

    relationship, _, transformation = _relationship(consideration, ordered, 82)

    assert relationship == "RELATED"
    assert transformation is not None
    assert "different policy state" in transformation


def test_unrelated_marcos_facebook_story_cannot_support_policy_claim() -> None:
    claim = extract_claim_features(
        "President Marcos, bukas sa posibilidad ng pagbabawal sa Facebook sa Pilipinas "
        "ayon kay Castro."
    )
    unrelated = (
        "President Marcos posted a Facebook message about fake news. Claire Castro discussed "
        "the post during an unrelated media interview in the Philippines."
    )

    relationship, _, _ = _relationship(claim, unrelated, 80)

    assert relationship == "IRRELEVANT"


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


@pytest.mark.parametrize(
    "unrelated_report",
    [
        "WATCH: VP Sara Duterte impeachment is 'dead'",
        (
            "Sara Duterte hopes the ICC will expedite her father's trial. "
            "The case concerns deaths during the drug war."
        ),
        (
            "Duterte propagandists eating up the dead: Sara Duterte discussed the poor "
            "state of political discourse."
        ),
    ],
)
def test_death_claim_requires_predicate_to_describe_named_person(
    unrelated_report: str,
) -> None:
    claim = extract_claim_features("Sara Duterte is dead")

    relationship, _, _ = _relationship(claim, unrelated_report, 80)

    assert relationship != "SUPPORTS"


def test_fact_check_for_same_person_debunks_death_claim() -> None:
    claim = extract_claim_features("Sara Duterte is dead")

    relationship, _, _ = _relationship(
        claim,
        "FACT CHECK: VP Sara Duterte is NOT dead. The claim is false; she remains alive.",
        90,
    )

    assert relationship == "DEBUNKS"


def test_fact_check_for_relative_does_not_debunk_named_person_death_claim() -> None:
    claim = extract_claim_features("Sara Duterte is dead")

    relationship, _, _ = _relationship(
        claim,
        "FACT CHECK: Rodrigo Duterte is not dead. Sara Duterte visited her father.",
        80,
    )

    assert relationship not in {"DEBUNKS", "CONTRADICTS"}


def test_literal_death_report_supports_same_named_person_claim() -> None:
    claim = extract_claim_features("Sara Duterte is dead")

    relationship, _, _ = _relationship(
        claim,
        "Breaking: Vice President Sara Duterte has reportedly died.",
        80,
    )

    assert relationship == "SUPPORTS"


def test_related_link_in_article_footer_cannot_decide_death_claim() -> None:
    claim = extract_claim_features("Sara Duterte is dead")
    opening = "Sara Duterte failed to declare investments, according to public documents."
    document = (
        opening
        + " Filing records and disclosure rules were discussed." * 80
        + " Related: FACT CHECK: VP Sara Duterte is NOT dead."
    )

    relationship, _, _ = _relationship(
        claim,
        document,
        55,
        support_scopes=[opening],
    )

    assert relationship not in {"SUPPORTS", "CONTRADICTS", "DEBUNKS"}


def test_attributed_filipino_quote_is_supported_by_matching_article_passage() -> None:
    claim = extract_claim_features(
        "Isipin n'yo na lang na mas matindi yung nangyari sa buhay ko. VP Sara Duterte"
    )
    article = (
        "Ayon kay VP Sara Duterte sa panayam: Isipin ninyo na lang na mas matindi "
        "yung nangyari sa buhay ko. Hindi iyon ang katapusan ninyo."
    )

    relationship, rules, transformation = _relationship(claim, article, 51)

    assert relationship == "SUPPORTS"
    assert "matching attributed quote" in rules[0]
    assert transformation is None


def test_attributed_quote_is_not_supported_when_article_omits_the_speaker() -> None:
    claim = extract_claim_features(
        "Sir Jack Argota said that the International Criminal Court will be dismantled."
    )
    article = (
        "A foreign political campaign is seeking to isolate and dismantle the International "
        "Criminal Court. The report discusses a different international controversy."
    )

    relationship, rules, transformation = _relationship(claim, article, 72)

    assert relationship == "RELATED"
    assert "does not mention the attributed speaker" in rules[0]
    assert transformation is None


def test_explicit_fact_check_is_classified_as_debunk() -> None:
    claim = extract_claim_features("Mayor Ana Santos was arrested")

    relationship, _, _ = _relationship(
        claim,
        "Fact check: The false claim that Mayor Ana Santos was arrested is not true.",
        80,
    )

    assert relationship == "DEBUNKS"


def test_unrelated_negation_does_not_contradict_an_ongoing_trial() -> None:
    claim = extract_claim_features(
        "VP Duterte trial: Prosecution willing to wait for ill-stricken Fajarda"
    )
    article = (
        "The impeachment trial is ongoing. The panel will finish presenting evidence "
        "without sacrificing either the prosecution's effort to trace the money or the "
        "defense's opportunity to respond."
    )

    relationship, _, _ = _relationship(claim, article, 60)

    assert relationship != "CONTRADICTS"


def test_trial_report_without_health_detail_does_not_support_full_headline() -> None:
    claim = extract_claim_features(
        "VP Duterte trial: Prosecution willing to wait for ill-stricken Fajarda"
    )
    article = (
        "The prosecution in Vice President Duterte's impeachment trial discussed Edward "
        "Fajarda as a possible witness in the confidential-funds proceedings."
    )

    relationship, _, _ = _relationship(claim, article, 70)

    assert relationship == "RELATED"


def test_report_missing_fajarda_does_not_support_fajarda_headline() -> None:
    claim = extract_claim_features(
        "VP Duterte trial: Prosecution willing to wait for ill-stricken Fajarda"
    )
    unrelated_person = (
        "Vice President Duterte's impeachment trial continued after another staff member "
        "was confined at a hospital, according to the prosecution."
    )

    relationship, _, _ = _relationship(claim, unrelated_person, 70)

    assert relationship == "RELATED"


def test_fact_check_about_same_person_but_different_claim_is_not_a_debunk() -> None:
    claim = extract_claim_features("VP Sara Duterte said mas matindi yung nangyari sa buhay ko")

    relationship, _, _ = _relationship(
        claim,
        (
            "Fact check: Rodrigo Duterte remains detained. VP Sara Duterte did not say "
            "that she would pick up her father from the ICC."
        ),
        43,
    )

    assert relationship != "DEBUNKS"


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


def test_near_identical_headline_with_changed_location_remains_related() -> None:
    claim_text = (
        "Alex Eala takes on home bet Mary Stoiana in the first round of the US Open "
        "singles on Monday (Manila time) in Russia."
    )
    authentic_title = (
        "Alex Eala takes on home bet Mary Stoiana in the first round of the US Open "
        "singles on Monday (Manila time) in Queens, New York"
    )
    claim = extract_claim_features(claim_text)
    report = SearchResult(
        title=authentic_title,
        url="https://inquirer.net/eala-us-open",
        domain="inquirer.net",
        snippet="Eala faces Mary Stoiana at the US Open in Queens, New York.",
        published_date=None,
        provider="test",
        query=claim_text,
    )

    assert score_initial_relevance(claim, normalize_search_text(claim_text), report) >= 40
    relationship, rules, transformation = _relationship(
        claim,
        f"{report.title} {report.snippet}",
        62,
    )

    assert relationship == "RELATED"
    assert transformation is not None
    assert "Russia" in transformation
    assert "Queens" in transformation
    assert rules == [transformation]


@pytest.mark.asyncio
async def test_changed_eala_location_returns_real_story_in_response() -> None:
    claim_text = (
        "Alex Eala takes on home bet Mary Stoiana in the first round of the US Open "
        "singles on Monday (Manila time) in Russia."
    )
    authentic_title = (
        "Alex Eala takes on home bet Mary Stoiana in the first round of the US Open "
        "singles on Monday (Manila time) in Queens, New York"
    )

    class EalaSearchClient:
        async def search(self, queries, *, restricted_domains, result_filter=None):
            del restricted_domains
            result = SearchResult(
                title=authentic_title,
                url="https://inquirer.net/eala-us-open",
                domain="inquirer.net",
                snippet="Eala faces Mary Stoiana at the US Open in Queens, New York.",
                published_date=None,
                provider="test",
                query=queries[0],
            )
            assert result_filter is None or result_filter(result)
            return SearchOutcome([result], ["test"], True)

    verifier = NewsVerifier(
        verifier_settings(),
        search_client=EalaSearchClient(),
        scraper=NoResultScraper(),
    )

    response = await verifier.verify(claim_text)

    assert response["verdict"] == "MISLEADING"
    assert response["evidence"]["related"][0]["title"] == authentic_title
    assert response["closest_real_story"]["found"] is True
    assert response["closest_real_story"]["title"] == authentic_title
    assert "Queens, New York" in response["explanation"]
    assert "Russia" in response["explanation"]


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
        self.restriction_history: list[list[str] | None] = []

    async def search(
        self,
        queries: list[str],
        *,
        restricted_domains: list[str] | None,
        result_filter=None,
    ):
        self.restricted_domains = restricted_domains
        self.restriction_history.append(restricted_domains)
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
        fact_check_domain_list=["verafiles.org", "rappler.com", "tsek.ph"],
        quote_source_domain_list=["tribune.net.ph", "smninewschannel.com"],
        philippine_news_domain_list=[
            "abs-cbn.com",
            "gmanetwork.com",
            "inquirer.net",
            "mb.com.ph",
            "philstar.com",
            "pna.gov.ph",
            "pco.gov.ph",
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
        news_unrestricted_fallback=True,
    )


@pytest.mark.asyncio
async def test_sara_duterte_death_claim_returns_false_with_exact_fact_check() -> None:
    claim_text = "Sara Duterte is dead"

    class SaraDeathSearchClient:
        async def search(self, queries, *, restricted_domains, result_filter=None):
            del restricted_domains
            results = [
                SearchResult(
                    title="FACT CHECK: VP Sara Duterte is NOT dead",
                    url="https://verafiles.org/articles/fact-check-vp-sara-duterte-is-not-dead",
                    domain="verafiles.org",
                    snippet=("The claim is false. Vice President Sara Duterte remains alive."),
                    published_date="2025-03-13",
                    provider="test",
                    query=queries[0],
                ),
                SearchResult(
                    title="WATCH: VP Sara Duterte impeachment is 'dead'",
                    url="https://rappler.com/example/sara-impeachment-dead",
                    domain="rappler.com",
                    snippet="The discussion concerned the state of impeachment proceedings.",
                    published_date="2025-08-07",
                    provider="test",
                    query=queries[0],
                ),
                SearchResult(
                    title="Sara Duterte hopes ICC will expedite father's trial",
                    url="https://inquirer.net/example/fathers-trial",
                    domain="inquirer.net",
                    snippet="The case concerns deaths during the drug war.",
                    published_date="2026-07-30",
                    provider="test",
                    query=queries[0],
                ),
            ]
            if result_filter is not None:
                results = [item for item in results if result_filter(item)]
            return SearchOutcome(results, ["test"], True)

    verifier = NewsVerifier(
        verifier_settings(),
        search_client=SaraDeathSearchClient(),
        scraper=NoResultScraper(),
    )

    response = await verifier.verify(claim_text)

    assert response["verdict"] == "FALSE"
    assert response["evidence"]["supporting"] == []
    assert [item["title"] for item in response["evidence"]["debunks"]] == [
        "FACT CHECK: VP Sara Duterte is NOT dead"
    ]


@pytest.mark.asyncio
async def test_fajarda_headline_is_supported_when_search_title_is_truncated() -> None:
    headline = "VP Duterte trial: Prosecution 'willing to wait' for ill-stricken Fajarda"

    class FajardaSearchClient:
        async def search(self, queries, *, restricted_domains, result_filter=None):
            if restricted_domains == verifier_settings().fact_check_domain_list:
                return SearchOutcome([], ["test"], True)
            result = SearchResult(
                title=("VP Duterte trial: Prosecution 'willing to wait' for ill-stricken ..."),
                url=(
                    "https://newsinfo.inquirer.net/2295748/vp-duterte-trial-prosecution-"
                    "willing-to-wait-for-ill-stricken-fajarda"
                ),
                domain="newsinfo.inquirer.net",
                snippet=(
                    "The prosecution is willing to wait until Edward Fajarda is well enough "
                    "to testify after he suffered a stroke."
                ),
                published_date="2026-08-31",
                provider="test",
                query=queries[0],
            )
            results = [result]
            if result_filter is not None:
                results = [item for item in results if result_filter(item)]
            return SearchOutcome(results, ["test"], True)

    verifier = NewsVerifier(
        verifier_settings(),
        search_client=FajardaSearchClient(),
        scraper=NoResultScraper(),
    )

    response = await verifier.verify(headline)

    assert response["verdict"] == "LIKELY_TRUE"
    assert response["evidence"]["supporting"][0]["url"].endswith(
        "willing-to-wait-for-ill-stricken-fajarda"
    )
    assert response["evidence"]["contradicting"] == []


@pytest.mark.asyncio
async def test_defeatist_mindset_quote_finds_original_report_despite_page_noise() -> None:
    paragraph = (
        "Faster Filipinos should \u201cshed our defeatist mindset,\u201d a Philippine Coast "
        "Guard (PCG) official said on Monday, in an apparent swipe at naysayers in the "
        "country's fight for its sovereign rights in the West Philippine Sea."
    )

    class DefeatistMindsetSearchClient:
        async def search(self, queries, *, restricted_domains, result_filter=None):
            if restricted_domains == verifier_settings().fact_check_domain_list:
                return SearchOutcome([], ["test"], True)
            if '"shed our defeatist mindset"' not in queries[:3]:
                return SearchOutcome([], ["test"], True)
            result = SearchResult(
                title=(
                    "West PH Sea: Tarriela urges Filipinos to shed 'defeatist mindset'"
                ),
                url=(
                    "https://www.inquirer.net/486843/west-ph-sea-tarriela-urges-"
                    "filipinos-to-shed-defeatist-mindset/"
                ),
                domain="www.inquirer.net",
                snippet=(
                    "Filipinos should shed our defeatist mindset, a Philippine Coast Guard "
                    "official said on Monday in the fight for sovereign rights in the West "
                    "Philippine Sea."
                ),
                published_date="2026-08-31",
                provider="test",
                query='"shed our defeatist mindset"',
            )
            results = [result]
            if result_filter is not None:
                results = [item for item in results if result_filter(item)]
            return SearchOutcome(results, ["test"], True)

    verifier = NewsVerifier(
        verifier_settings(),
        search_client=DefeatistMindsetSearchClient(),
        scraper=NoResultScraper(),
    )

    response = await verifier.verify(paragraph)

    assert response["verdict"] == "LIKELY_TRUE"
    assert response["evidence"]["supporting"][0]["publisher"] == "Inquirer.net"
    assert response["closest_real_story"]["found"] is False


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

    # The required domain-restricted searches must be present.
    # Progressive search may add additional unrestricted rounds (None).
    history = search_client.restriction_history
    assert verifier_settings().fact_check_domain_list in history
    assert verifier_settings().philippine_news_domain_list in history
    # Unrestricted fallback searches are also expected
    assert None in history or [] in history
    assert (
        result["search"]["outlet_domains_searched"]
        == verifier_settings().philippine_news_domain_list
    )


@pytest.mark.asyncio
async def test_filipino_facebook_policy_claim_is_supported_with_required_context() -> None:
    headline = (
        "President Marcos, bukas sa posibilidad ng pagbabawal sa Facebook sa Pilipinas "
        "ayon kay Castro."
    )

    class PolicySearchClient:
        async def search(self, queries, *, restricted_domains, result_filter=None):
            if restricted_domains == verifier_settings().fact_check_domain_list:
                return SearchOutcome([], ["test"], True)
            documents = [
                (
                    "Malacañang open to broader restrictions on digital platforms",
                    "https://pco.gov.ph/news_releases/policy-platform-restrictions/",
                    "pco.gov.ph",
                    "President Marcos is open to considering Facebook restrictions in the "
                    "Philippines, Palace Press Officer Claire Castro said. Any ban would first "
                    "be studied.",
                ),
                (
                    "Palace open to social media ban amid violence, fake news concerns",
                    "https://gmanetwork.com/news/palace-open-social-media-ban/story/",
                    "gmanetwork.com",
                    "Claire Castro said President Marcos is open to studying whether Facebook "
                    "or another harmful platform should be removed in the Philippines.",
                ),
                (
                    "No Facebook ban for now, other platforms may face restrictions — Palace",
                    "https://inquirer.net/no-facebook-ban-for-now/",
                    "inquirer.net",
                    "Palace Press Officer Claire Castro clarified that President Marcos has "
                    "not ordered a Facebook ban in the Philippines, while possible platform "
                    "restrictions remain under study.",
                ),
            ]
            results = [
                SearchResult(
                    title=title,
                    url=url,
                    domain=domain,
                    snippet=snippet,
                    published_date="2026-08-25",
                    provider="test",
                    query=queries[0],
                )
                for title, url, domain, snippet in documents
            ]
            if result_filter is not None:
                results = [result for result in results if result_filter(result)]
            return SearchOutcome(results, ["test"], True)

    verifier = NewsVerifier(
        verifier_settings(),
        search_client=PolicySearchClient(),
        scraper=NoResultScraper(),
    )

    result = await verifier.verify(headline)

    assert result["verdict"] == "VERIFIED"
    assert result["context_warnings"] == [
        "The government was only open to studying the possibility; no ban was ordered."
    ]
    assert {item["domain"] for item in result["evidence"]["supporting"]} == {
        "pco.gov.ph",
        "gmanetwork.com",
        "inquirer.net",
    }
    assert any(q.startswith("President Marcos Facebook open possible ban") for q in result["search"]["queries"][:5])


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
        "DILG wants PNP access to homes of illegal firearm owners for inspections to kill people"
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
                            "The DILG proposed inspections involving owners of illegal firearms."
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


def test_credible_related_story_does_not_make_specific_claim_false() -> None:
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

    assert verdict == "UNVERIFIED"
    assert confidence == 42
    assert "remains unverified" in explanation


def test_old_evidence_cannot_support_tagalog_next_week_claim() -> None:
    verifier = NewsVerifier(
        verifier_settings(),
        search_client=EmptySearchClient(succeeded=True),
        scraper=NoopScraper(),
    )
    analysis = EvidenceAnalysis(
        result=SearchResult(
            title="Duterte remains in ICC custody",
            url="https://rappler.com/duterte-icc-custody",
            domain="rappler.com",
            snippet="The former president remains in ICC custody.",
            published_date="2025-03-19",
            provider="test",
            query="Duterte uuwi susunod na linggo",
        ),
        article=None,
        relationship="SUPPORTS",
        similarity=85,
        evidence_score=85,
        source_tier=1,
        recency_score=10,
        explanation="Direct support.",
    )

    verdict, _, explanation = verifier._decide_verdict(
        [analysis],
        extract_claim_features("Si Rodrigo Duterte ay uuwi sa susunod na linggo."),
        datetime(2026, 9, 14, tzinfo=UTC),
    )

    assert verdict == "MISLEADING"
    assert "publication date" in explanation


def test_same_publisher_subdomains_are_not_independent_support() -> None:
    verifier = NewsVerifier(
        verifier_settings(),
        search_client=EmptySearchClient(succeeded=True),
        scraper=NoopScraper(),
    )
    analyses = [
        EvidenceAnalysis(
            result=SearchResult(
                title=f"Mayor Santos arrested - report {index}",
                url=f"https://{subdomain}.inquirer.net/story-{index}",
                domain=f"{subdomain}.inquirer.net",
                snippet="Mayor Santos was arrested after an investigation.",
                published_date="2026-08-29",
                provider="test",
                query="Mayor Santos arrested",
            ),
            article=None,
            relationship="SUPPORTS",
            similarity=85,
            evidence_score=85,
            source_tier=1,
            recency_score=100,
            explanation="Direct support.",
        )
        for index, subdomain in enumerate(("newsinfo", "cebudailynews"), start=1)
    ]

    verdict, _, explanation = verifier._decide_verdict(
        analyses,
        extract_claim_features("Mayor Santos was arrested"),
        datetime.now(UTC),
    )

    assert verdict == "LIKELY_TRUE"
    assert "independent confirmation is limited" in explanation


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


def test_breaking_news_prefix_does_not_extract_news_as_entity() -> None:
    claim_text = clean_claim_text(
        "BREAKING NEWS: President Donald Tram binisita ang ating pangulo at nangako na papalayain sa madaling panahon."
    )
    features = extract_claim_features(claim_text)
    assert "NEWS" not in features.entities
    assert "BREAKING" not in features.entities
    assert any("Donald" in e for e in features.entities)


def test_unrelated_international_article_matching_entity_is_irrelevant() -> None:
    claim_text = clean_claim_text(
        "BREAKING NEWS: President Donald Tram binisita ang ating pangulo at nangako na papalayain sa madaling panahon."
    )
    features = extract_claim_features(claim_text)
    article_text = (
        "Iran rejects President Donald Trump claims of US control over Hormuz as lies in the Persian Gulf."
    )
    relationship, rules, transformation = _relationship(features, article_text, 35)

    assert relationship == "IRRELEVANT"
    assert transformation is None


def test_parse_publisher_social_account_recognizes_known_handles() -> None:
    # Threads
    threads_info = parse_publisher_social_account("https://www.threads.com/@dailytribuneph/post/Dc-mfgQnyhK")
    assert threads_info is not None
    assert threads_info[0] == "Daily Tribune"
    assert threads_info[1] == "tribune.net.ph"

    # Facebook
    fb_info = parse_publisher_social_account("https://www.facebook.com/tribunephl/posts/123456789")
    assert fb_info is not None
    assert fb_info[0] == "Daily Tribune"

    # X / Twitter
    x_info = parse_publisher_social_account("https://x.com/rapplerdotcom/status/987654321")
    assert x_info is not None
    assert x_info[0] == "Rappler"

    # Random / personal account returns None without matching hint
    assert parse_publisher_social_account("https://www.facebook.com/john.doe.123/posts/1") is None
    assert parse_publisher_social_account("https://x.com/randomuser/status/1") is None


def test_is_evidence_page_permits_official_publisher_social_channels() -> None:
    # Official Daily Tribune Threads post should be permitted as evidence
    assert _is_evidence_page(
        "https://www.threads.com/@dailytribuneph/post/Dc-mfgQnyhK",
        publisher_hint="Daily Tribune",
    ) is True

    # Generic or unknown social posts are blocked
    assert _is_evidence_page("https://www.facebook.com/randomuser/posts/123") is False
    assert _is_evidence_page("https://x.com/someuser/status/123") is False


def test_source_tier_recognizes_official_publisher_social_channel() -> None:
    settings = verifier_settings()
    # Official Threads URL should evaluate to Tier 2 (Major News)
    tier = _source_tier("threads.com", settings, url="https://www.threads.com/@dailytribuneph/post/Dc-mfgQnyhK")
    assert tier == 2

    # Regular unverified social URL should evaluate to Tier 4
    regular_tier = _source_tier("threads.com", settings, url="https://www.threads.com/@random_user/post/123")
    assert regular_tier == 4


def test_generate_search_queries_suppresses_bare_entity_query_for_quotes() -> None:
    claim_text = (
        "'Pag may nangyaring 'di maganda sa buhay n'yo, isipin n'yo na lang "
        "na mas matindi 'yung nangyari sa buhay ko. VP Sara Duterte"
    )
    cleaned = clean_claim_text(claim_text)
    features = extract_claim_features(cleaned)

    queries = generate_search_queries(cleaned, features)

    # Bare politician name alone should NOT be present in queries
    for q in queries:
        assert q.lower().strip() not in {"sara duterte", "vp sara duterte", "vp sara"}


def test_generate_quote_source_queries_includes_publisher_and_unrestricted_variations() -> None:
    claim_text = (
        "'Pag may nangyaring 'di maganda sa buhay n'yo, isipin n'yo na lang "
        "na mas matindi 'yung nangyari sa buhay ko. VP Sara Duterte"
    )
    cleaned = clean_claim_text(claim_text)
    features = extract_claim_features(cleaned)

    queries = generate_quote_source_queries(cleaned, features, publisher="Daily Tribune")

    # Should have publisher queries and unrestricted quote queries
    assert any("daily tribune" in q.lower() or "tribune.net.ph" in q.lower() for q in queries)
    assert any("mas matindi" in q for q in queries)
    assert len(queries) >= 3


def test_relationship_detects_support_for_quote_card_in_social_post() -> None:
    claim_text = (
        "'Pag may nangyaring 'di maganda sa buhay n'yo, isipin n'yo na lang "
        "na mas matindi 'yung nangyari sa buhay ko. VP Sara Duterte"
    )
    cleaned = clean_claim_text(claim_text)
    features = extract_claim_features(cleaned)

    post_snippet = (
        "... mas matindi 'yung nangyari sa buhay ko. VP Sara Duterte tribune.net.ph tribunephl "
        "dailytribuneph DailyTribunePH KaTRIBU dailytribuneofficial"
    )
    relationship, rules, transformation = _relationship(features, post_snippet, 80)

    assert relationship == "SUPPORTS"


@pytest.mark.asyncio
async def test_searchapi_ai_mode_uses_cited_links_not_generated_overview_as_evidence() -> None:
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["engine"] == "google_ai_mode"
        assert request.url.params["gl"] == "ph"
        assert request.headers["Authorization"] == "Bearer ai-mode-secret"
        return httpx.Response(
            200,
            json={
                "markdown": "An AI-generated overview that must not become evidence.",
                "reference_links": [
                    {
                        "title": "Official announcement",
                        "link": "https://pco.gov.ph/news/example",
                        "snippet": "Official source text.",
                    }
                ],
                "web_results": [
                    {
                        "title": "Independent reporting",
                        "link": "https://www.gmanetwork.com/news/example",
                        "snippet": "Independent report.",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        settings = SimpleNamespace(
            searchapi_ai_mode_api_key=SimpleNamespace(get_secret_value=lambda: "ai-mode-secret"),
            searchapi_api_key=None,
            serper_api_key_list=[],
            google_search_api_key=None,
            google_cse_id=None,
            news_search_provider_list=["searchapi_ai_mode"],
            searchapi_ai_mode_max_queries=1,
            news_search_timeout_seconds=5.0,
            news_max_concurrent_search_requests=2,
            news_min_relevant_results=1,
        )
        client = NewsSearchClient(settings, client=mock_client)
        outcome = await client.search(["test claim", "unused query"], restricted_domains=None)

    assert outcome.any_provider_succeeded is True
    assert outcome.providers_used == ["searchapi_ai_mode"]
    assert [result.url for result in outcome.results] == [
        "https://pco.gov.ph/news/example",
        "https://www.gmanetwork.com/news/example",
    ]
    assert all("overview" not in result.snippet.lower() for result in outcome.results)


@pytest.mark.asyncio
async def test_serper_key_fallback_on_429_or_403() -> None:
    calls: list[str] = []

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        key = request.headers.get("X-API-KEY", "")
        calls.append(key)
        if key == "key-exhausted":
            return httpx.Response(429, json={"message": "Quota exceeded"})
        if key == "key-unauthorized":
            return httpx.Response(403, json={"message": "Unauthorized.", "statusCode": 403})
        if key == "key-active":
            return httpx.Response(
                200,
                json={
                    "organic": [
                        {
                            "title": "Legitimate News Title",
                            "link": "https://inquirer.net/story-123",
                            "snippet": "Story snippet text",
                        }
                    ]
                },
            )
        return httpx.Response(500, json={"error": "Unknown key"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        settings = SimpleNamespace(
            serper_api_key_list=["key-exhausted", "key-unauthorized", "key-active"],
            news_search_provider_list=["serper"],
            news_search_timeout_seconds=5.0,
            news_max_concurrent_search_requests=4,
            news_min_relevant_results=1,
        )
        search_client = NewsSearchClient(settings, client=mock_client)
        outcome = await search_client.search(["test query"], restricted_domains=None)

        assert outcome.any_provider_succeeded is True
        assert len(outcome.results) == 1
        assert outcome.results[0].title == "Legitimate News Title"
        assert calls == ["key-exhausted", "key-unauthorized", "key-active"]
        assert "key-exhausted" in search_client._exhausted_serper_keys
        assert "key-unauthorized" in search_client._exhausted_serper_keys
        assert "key-active" not in search_client._exhausted_serper_keys


@pytest.mark.asyncio
async def test_serper_key_fallback_on_not_enough_credits_message() -> None:
    calls: list[str] = []

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        key = request.headers.get("X-API-KEY", "")
        calls.append(key)
        if key == "key-no-credits":
            return httpx.Response(400, json={"message": "Not enough credits"})
        if key == "key-valid":
            return httpx.Response(
                200,
                json={
                    "organic": [
                        {
                            "title": "GMA News Report",
                            "link": "https://gmanetwork.com/news/story-456",
                            "snippet": "Report snippet",
                        }
                    ]
                },
            )
        return httpx.Response(500)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        settings = SimpleNamespace(
            serper_api_key_list=["key-no-credits", "key-valid"],
            news_search_provider_list=["serper"],
            news_search_timeout_seconds=5.0,
            news_max_concurrent_search_requests=4,
            news_min_relevant_results=1,
        )
        search_client = NewsSearchClient(settings, client=mock_client)
        outcome = await search_client.search(["query"], restricted_domains=None)

        assert outcome.any_provider_succeeded is True
        assert len(outcome.results) == 1
        assert outcome.results[0].domain == "gmanetwork.com"
        assert calls == ["key-no-credits", "key-valid"]


@pytest.mark.asyncio
async def test_serper_all_keys_exhausted_falls_back_to_next_provider() -> None:
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "serper.dev" in url:
            return httpx.Response(429, json={"message": "Quota exceeded"})
        if "searchapi.io" in url:
            return httpx.Response(
                200,
                json={
                    "organic_results": [
                        {
                            "title": "SearchAPI Fallback Result",
                            "link": "https://rappler.com/article",
                            "snippet": "SearchAPI snippet",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_client:
        settings = SimpleNamespace(
            serper_api_key_list=["serper-k1", "serper-k2"],
            searchapi_api_key=SimpleNamespace(get_secret_value=lambda: "searchapi-secret"),
            google_search_api_key=None,
            google_cse_id=None,
            news_search_provider_list=["serper", "searchapi"],
            news_search_timeout_seconds=5.0,
            news_max_concurrent_search_requests=4,
            news_min_relevant_results=1,
        )
        search_client = NewsSearchClient(settings, client=mock_client)
        outcome = await search_client.search(["test fallback"], restricted_domains=None)

        assert outcome.any_provider_succeeded is True
        assert len(outcome.results) == 1
        assert outcome.results[0].title == "SearchAPI Fallback Result"
        assert outcome.providers_used == ["serper", "searchapi"]
        assert "serper" in search_client._exhausted_providers
