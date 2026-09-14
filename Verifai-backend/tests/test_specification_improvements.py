import json
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.FakeNewsAnalyzer.audit_logger import AuditLogger, VerificationAuditRecord
from app.FakeNewsAnalyzer.image_fact_checker import (
    _understanding_claims,
    clean_ocr_text,
)
from app.FakeNewsAnalyzer.news_verifier import (
    EvidenceAnalysis,
    NewsVerifier,
    SearchOutcome,
    SearchResult,
    are_results_semantically_related,
    claim_type,
    clean_claim_text,
    detect_modality,
    extract_atomic_claims,
    extract_claim_features,
    generate_progressive_queries,
    numerical_analysis,
    translate_tagalog_claim,
)


def make_test_settings(temp_log_path: str | None = None) -> SimpleNamespace:
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
        ],
        trusted_news_domain_list=["rappler.com", "inquirer.net", "abs-cbn.com"],
        news_tier_2_domain_list=["gmanetwork.com"],
        news_min_relevant_results=2,
        news_max_search_results=10,
        news_relevance_threshold=30,
        news_max_articles_to_scrape=4,
        news_debug=False,
        news_old_story_days=30,
        news_unrestricted_fallback=True,
        news_max_search_rounds=2,
        news_audit_log_enabled=True,
        news_audit_log_path=temp_log_path or "logs/test_audit.jsonl",
    )


class DummyScraper:
    async def scrape(self, url: str):
        return None


# ---------------------------------------------------------------------------
# 1. Atomic Claim Decomposition Tests
# ---------------------------------------------------------------------------


def test_atomic_claim_decomposition_compound_conjunction():
    compound = (
        "President Marcos approved the P6-trillion 2025 national budget "
        "and abolished the Presidential Commission on Good Government."
    )
    atomic = extract_atomic_claims(compound)
    assert len(atomic) >= 2
    assert any("budget" in c.lower() for c in atomic)
    assert any("abolished" in c.lower() or "good government" in c.lower() for c in atomic)


def test_atomic_claim_decomposition_multiple_sentences():
    text = (
        "Senator Revilla was arrested in Cavite yesterday. "
        "The Sandiganbayan issued the warrant of arrest without bail."
    )
    atomic = extract_atomic_claims(text)
    assert len(atomic) == 2
    assert any("revilla" in c.lower() for c in atomic)
    assert any("sandiganbayan" in c.lower() for c in atomic)


def test_atomic_claim_decomposition_single_assertion():
    text = "VP Sara Duterte attended the budget hearing at the Senate."
    atomic = extract_atomic_claims(text)
    assert len(atomic) == 1
    assert "Sara Duterte" in atomic[0]


# ---------------------------------------------------------------------------
# 2. Numerical / Statistical Analysis Tests
# ---------------------------------------------------------------------------


def test_numerical_analysis_with_money_and_monthly_duration():
    claim = "Families will receive ₱5,000 per month for 2 years under the new subsidy program."
    analysis = numerical_analysis(claim)

    assert analysis["required"] is True
    assert analysis["math_status"] == "CONSISTENT"
    assert "PHP 5,000 × 24 months" in str(analysis["calculation"])
    assert "PHP 120,000" in str(analysis["result"])


def test_numerical_analysis_large_multipliers():
    assert numerical_analysis("The agency spent PHP 100 billion on flood control projects.")[
        "required"
    ] is True
    assert numerical_analysis("Government allocates P2.5M for the health program.")[
        "required"
    ] is True


def test_numerical_analysis_percentage_claims():
    analysis = numerical_analysis("Poverty rate drops to 15.5% nationwide.")
    assert analysis["required"] is True
    assert "15.5%" in analysis["quantities_found"]


# ---------------------------------------------------------------------------
# 3. Enhanced Claim Analysis Tests (Type, Negation, Modality)
# ---------------------------------------------------------------------------


def test_claim_type_classification():
    assert claim_type("Government allocated ₱50 billion for health.") == "MONEY"
    assert claim_type("Poverty decreased to 14.2% in 2025.") == "STATISTIC"
    assert claim_type('Marcos said "We will not yield any territory".') == "QUOTE"
    assert claim_type("House passes new tax reform bill into law.") == "POLICY"
    assert claim_type("Mayor arrested in Davao raid.") == "EVENT"


def test_negation_detection_english_and_filipino():
    # English
    features_en = extract_claim_features("Marcos did not resign as President.")
    assert features_en.negation_detected is True

    # Filipino
    features_tl = extract_claim_features("Hindi totoo na namatay si dating Pangulong Duterte.")
    assert features_tl.negation_detected is True

    # Affirmative
    features_aff = extract_claim_features("Marcos appointed the new Chief of Staff.")
    assert features_aff.negation_detected is False


def test_modality_detection():
    # Speculative / Alleged
    assert detect_modality("Quiboloy might surrender to authorities this week.") == "SPECULATIVE"
    assert detect_modality("Umano'y tatakbo si Sara Duterte sa 2028.") == "SPECULATIVE"

    # Future / Proposal
    assert detect_modality("Government will implement free tuition in 2026.") == "FUTURE"
    assert detect_modality("Plano ng DSWD na magbigay ng bagong ayuda.") == "FUTURE"

    # Conditional
    assert detect_modality("If the bill passes, taxes will increase.") == "CONDITIONAL"

    # Asserted
    assert detect_modality("President signed the budget bill yesterday.") == "ASSERTED"


# ---------------------------------------------------------------------------
# 4. Adaptive Verification Loop (Multi-round Search) Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adaptive_multiround_search_triggers_for_uncovered_atomic_claims():
    compound_claim = (
        "President Marcos signed Republic Act 12000 and dismissed the Ombudsman."
    )

    class MultiRoundMockSearchClient:
        def __init__(self):
            self.round_calls = 0

        async def search(
            self,
            queries: list[str],
            restricted_domains: list[str] | None = None,
            result_filter: Callable[[SearchResult], bool] | None = None,
        ) -> SearchOutcome:
            self.round_calls += 1
            # Round 1 returns results only covering Republic Act
            if self.round_calls <= 5:
                res = SearchResult(
                    title="Marcos signs Republic Act 12000 into law",
                    url="https://www.pna.gov.ph/articles/ra12000",
                    domain="pna.gov.ph",
                    snippet="President Ferdinand R. Marcos Jr. signed Republic Act 12000.",
                    published_date="2026-09-01",
                    provider="test",
                    query="Marcos Republic Act 12000",
                    trusted=True,
                    relevance_score=80,
                )
                return SearchOutcome([res], ["mock"], True)
            else:
                # Round 2 targeted search for the uncovered Ombudsman dismissal
                res2 = SearchResult(
                    title="FACT CHECK: Marcos did NOT dismiss Ombudsman",
                    url="https://verafiles.org/articles/fact-check-ombudsman",
                    domain="verafiles.org",
                    snippet="Reports claiming Marcos dismissed the Ombudsman are baseless.",
                    published_date="2026-09-02",
                    provider="test",
                    query="dismissed Ombudsman",
                    trusted=True,
                    relevance_score=75,
                )
                return SearchOutcome([res2], ["mock"], True)

    search_client = MultiRoundMockSearchClient()
    verifier = NewsVerifier(
        make_test_settings(),
        search_client=search_client,
        scraper=DummyScraper(),
    )

    response = await verifier.verify(compound_claim)

    assert response["status"] == "SUCCESS"
    assert len(response["atomic_claims"]) >= 2
    # Multiple queries and providers recorded
    assert len(response["search"]["queries"]) > 0


# ---------------------------------------------------------------------------
# 5. Observability / Structured Audit Logging Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structured_audit_logger_creates_jsonl_record():
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "audit.jsonl"
        settings = make_test_settings(temp_log_path=str(log_file))

        class SimpleSearchClient:
            async def search(self, queries, restricted_domains=None, result_filter=None):
                return SearchOutcome([], ["mock"], True)

        verifier = NewsVerifier(
            settings,
            search_client=SimpleSearchClient(),
            scraper=DummyScraper(),
        )

        response = await verifier.verify("Ferdinand Marcos Jr. resigned today")
        assert response["verdict"] == "UNVERIFIED"

        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1

        record = json.loads(lines[-1])
        assert "verification_id" in record
        assert "timestamp" in record
        assert record["claim_raw"] == "Ferdinand Marcos Jr. resigned today"
        assert record["verdict"] == "UNVERIFIED"
        assert "stopping_reason" in record


# ---------------------------------------------------------------------------
# 6. Unresolved Numeric Claim Flagging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unresolved_numeric_claim_flagged_when_evidence_lacks_number():
    claim = "Government spent ₱999 billion on new bullet train project."

    class MismatchedNumberSearchClient:
        async def search(self, queries, restricted_domains=None, result_filter=None):
            result = SearchResult(
                title="Transportation Department discusses railway plans",
                url="https://www.inquirer.net/railway-plans",
                domain="www.inquirer.net",
                snippet="The agency held preliminary discussions on regional railway development.",
                published_date="2026-09-01",
                provider="test",
                query=queries[0] if queries else "",
                trusted=True,
                relevance_score=60,
            )
            return SearchOutcome([result], ["mock"], True)

    verifier = NewsVerifier(
        make_test_settings(),
        search_client=MismatchedNumberSearchClient(),
        scraper=DummyScraper(),
    )

    response = await verifier.verify(claim)
    assert response["numerical_analysis"] is not None
    assert response["numerical_analysis"]["required"] is True
    # Because 999 billion was not in the snippet/article text
    assert len(response["unresolved_numeric_claims"]) > 0
    assert any("999" in item for item in response["unresolved_numeric_claims"])


# ---------------------------------------------------------------------------
# 7. OCR Cleanup Tests (clean_ocr_text)
# ---------------------------------------------------------------------------


def test_clean_ocr_text_removes_hyphenation_and_soft_breaks():
    broken_text = (
        "President Marcos bukas sa pagba-\n"
        "bawal ng ilang social media plat-\n"
        "forms sa bansa."
    )
    cleaned = clean_ocr_text(broken_text)
    assert "pagbabawal" in cleaned
    assert "platforms" in cleaned
    assert "\n" not in cleaned


def test_clean_ocr_text_normalizes_punctuation_and_whitespace():
    noisy_text = "   ••• Impeach court spox: 11 votes can scrap threshold?????   ••••   "
    cleaned = clean_ocr_text(noisy_text)
    assert cleaned.startswith("Impeach")
    assert cleaned.endswith("?")
    assert "?????" not in cleaned
    assert "•••" not in cleaned


# ---------------------------------------------------------------------------
# 8. Tagalog-to-English Claim Translation Tests
# ---------------------------------------------------------------------------


def test_translate_tagalog_claim_produces_english_queries():
    claim = "Sen. Robin Padilla isinusulong ang batas na No Christmas Song"
    translated = translate_tagalog_claim(claim)
    assert len(translated) > 0
    combined = " ".join(translated).casefold()
    assert "padilla" in combined
    assert any(term in combined for term in ("proposing", "pushing", "bill", "law", "song"))


def test_translate_tagalog_facebook_policy_claim():
    claim = "President Marcos, bukas sa posibilidad ng pagbabawal sa Facebook sa Pilipinas ayon kay Castro"
    translated = translate_tagalog_claim(claim)
    assert len(translated) > 0
    combined = " ".join(translated).casefold()
    assert "marcos" in combined
    assert any(term in combined for term in ("open", "ban", "prohibition", "possibility"))


# ---------------------------------------------------------------------------
# 9. Progressive Query Generation Tests
# ---------------------------------------------------------------------------


def test_generate_progressive_queries_simplification_hierarchy():
    claim = "Sen. Robin Padilla isinusulong ang batas na No Christmas Song"
    features = extract_claim_features(claim)
    prev = [claim]
    prog_queries = generate_progressive_queries(claim, features, previous_queries=prev)
    assert len(prog_queries) > 0
    # Queries should not repeat previous queries
    assert claim.casefold() not in [q.casefold() for q in prog_queries]
    # Should include entity and topic-relevant simplified terms
    assert any("padilla" in q.casefold() for q in prog_queries)


# ---------------------------------------------------------------------------
# 10. Semantic Relevance Assessment Tests
# ---------------------------------------------------------------------------


def test_are_results_semantically_related_detects_topic_match():
    claim = "Impeach court spox: 11 votes can scrap '16-vote' conviction threshold"
    features = extract_claim_features(claim)

    related_result = SearchResult(
        title="Impeachment court spox: 11 votes can scrap 16-vote threshold",
        url="https://inquirer.net/impeach-threshold-ruling",
        domain="inquirer.net",
        snippet="A spokesperson for the impeachment court said 11 senator-judges can vote to change the 16-vote conviction rule.",
        published_date="2026-08-10",
        provider="serper",
        query="impeach court threshold",
    )

    unrelated_result = SearchResult(
        title="Celebrity wedding photos in Boracay resort",
        url="https://inquirer.net/celebrity-wedding-boracay",
        domain="inquirer.net",
        snippet="Famous actors tied the knot in an intimate beach ceremony over the weekend.",
        published_date="2026-08-10",
        provider="serper",
        query="inquirer news",
    )

    assert are_results_semantically_related(features, claim, [related_result], threshold=40) is True
    assert are_results_semantically_related(features, claim, [unrelated_result], threshold=40) is False


# ---------------------------------------------------------------------------
# 11. Headline Preservation in OCR Understanding Claims
# ---------------------------------------------------------------------------


def test_understanding_claims_preserves_full_headline_as_first_candidate():
    understanding = {
        "headline": "Philippines declares December 25 as the official birthday of Jose Rizal",
        "atomic_claims": ["Jose Rizal birthday declared December 25"],
        "direct_quotes": [],
        "speaker": "",
        "content_type": "NEWS",
    }
    claims = _understanding_claims(understanding, "Philippines declares December 25 as the official birthday of Jose Rizal")
    assert len(claims) >= 1
    # Full headline should be preserved as candidate
    assert any("december 25" in c.lower() and "jose rizal" in c.lower() for c in claims)

