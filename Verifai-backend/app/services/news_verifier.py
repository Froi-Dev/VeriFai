import asyncio
import html as html_module
import ipaddress
import logging
import math
import re
import socket
import unicodedata
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from app.core.config import Settings

logger = logging.getLogger(__name__)

Relationship = Literal["SUPPORTS", "CONTRADICTS", "RELATED", "DEBUNKS", "IRRELEVANT"]

NOISE_PHRASES = (
    "breaking news",
    "must see",
    "just in",
    "breaking",
    "exclusive",
    "shocking",
    "confirmed",
    "viral",
    "watch",
)
STOPWORDS = {
    "a",
    "an",
    "ang",
    "are",
    "as",
    "at",
    "ay",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "ito",
    "its",
    "mga",
    "ng",
    "of",
    "on",
    "sa",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "will",
    "with",
}
TRUTH_TOKENS = {
    "not",
    "no",
    "never",
    "without",
    "before",
    "after",
    "dead",
    "alive",
    "denies",
    "confirmed",
    "false",
}
NEGATION_WORDS = {
    "not",
    "no",
    "never",
    "denied",
    "denies",
    "false",
    "fake",
    "incorrect",
    "untrue",
    "didn't",
    "didnt",
    "without",
    "hasn't",
    "hasnt",
}
DEBUNK_PHRASES = (
    "fact check",
    "false claim",
    "fake news",
    "not true",
    "no evidence",
    "denies claim",
    "debunked",
    "fabricated",
    "misleading claim",
    "hoax",
    "untrue",
)
RELATIVE_DATES = (
    "today",
    "yesterday",
    "tomorrow",
    "this morning",
    "tonight",
    "last night",
    "this week",
    "last week",
)

EVENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "DEATH": ("died", "dead", "dies", "death", "passed away", "killed"),
    "HEALTH": (
        "hospitalized",
        "hospitalised",
        "sick",
        "ill",
        "medical emergency",
        "recovering",
        "stable condition",
    ),
    "ARREST": ("arrested", "detained", "in custody", "warrant", "apprehended"),
    "CONVICTION": ("convicted", "found guilty", "acquitted"),
    "LEGAL": (
        "charged",
        "accused",
        "investigated",
        "questioned",
        "case filed",
        "trial ongoing",
    ),
    "RESIGNATION": ("resigned", "resigns", "resignation", "steps down", "quit"),
    "ELECTION": ("wins", "loses", "elected", "votes", "election", "candidate"),
    "DISASTER": (
        "earthquake",
        "typhoon",
        "flood",
        "eruption",
        "storm",
        "landslide",
        "landfall",
    ),
    "POLICY_APPROVED": (
        "law approved",
        "signed into law",
        "law passed",
        "implemented",
        "executive order signed",
    ),
    "POLICY_PROPOSAL": (
        "proposal",
        "proposed",
        "draft",
        "bill filed",
        "under discussion",
        "not yet passed",
    ),
}

EVENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "DEATH": (r"\b(di(?:e[ds]?|ed)|dead|death|kill(?:ed)?)\b",),
    "HEALTH": (r"\bhospitali[sz](?:e|ed|ation)\b", r"\bstable condition\b"),
    "ARREST": (r"\b(arrest(?:ed)?|detain(?:ed)?|apprehend(?:ed)?)\b",),
    "CONVICTION": (r"\bconvict(?:ed|ion)?\b", r"\bfound guilty\b"),
    "RESIGNATION": (r"\bresign(?:ed|s|ation|ing)?\b", r"\bsteps? down\b"),
    "POLICY_APPROVED": (
        r"\bsign(?:ed|s)?\b.{0,90}\b(?:law|act|bill)\b",
        r"\b(?:law|act|bill)\b.{0,90}\bsign(?:ed|s)?\b",
        r"\bapprov(?:e|ed|es|al)\b.{0,90}\b(?:law|act|bill)\b",
    ),
    "POLICY_PROPOSAL": (r"\b(?:propos(?:al|ed)|draft|bill filed|under discussion)\b",),
}

CONTRADICTION_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    "DEATH": (
        (r"\b(alive|recovering|stable condition|released from hospital)\b", "alive/health"),
        (r"\b(no|denies?|denied|false|fake)\b.{0,45}\b(death|dead|died|killed)\b", "death denial"),
    ),
    "ARREST": (
        (r"\b(no|denies?|denied|not)\b.{0,35}\b(arrest|arrested|warrant)\b", "arrest denial"),
        (r"\b(no warrant|not in custody|was not detained)\b", "no custody"),
    ),
    "CONVICTION": (
        (r"\b(trial ongoing|not convicted|no conviction|pleaded not guilty)\b", "no conviction"),
        (r"\b(charged|accused|investigated)\b.{0,35}\b(not guilty|trial)\b", "case pending"),
    ),
    "RESIGNATION": (
        (
            r"\b(denies?|denied|no|not)\b.{0,40}\b(resign|resignation|stepping down)\b",
            "resignation denial",
        ),
        (r"\b(remains|stays) in office\b", "remains in office"),
    ),
    "POLICY_APPROVED": (
        (r"\b(proposal|draft|bill filed|under discussion|not yet passed)\b", "proposal, not law"),
    ),
    "DISASTER": (
        (r"\b(no landfall expected|may pass nearby|forecast only)\b", "forecast, not impact"),
    ),
}

TRANSFORMATIONS: dict[tuple[str, str], str] = {
    (
        "DEATH",
        "HEALTH",
    ): "A hospitalization or health report may have been changed into a death claim.",
    ("ARREST", "LEGAL"): "Questioning or an investigation may have been presented as an arrest.",
    (
        "CONVICTION",
        "LEGAL",
    ): "An accusation or pending case may have been presented as a conviction.",
    (
        "POLICY_APPROVED",
        "POLICY_PROPOSAL",
    ): "A proposal or filed bill may have been presented as approved law.",
}

TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}

PUBLISHER_NAMES = {
    "abs-cbn.com": "ABS-CBN News",
    "apnews.com": "Associated Press",
    "bbc.com": "BBC",
    "cnn.com": "CNN",
    "gmanetwork.com": "GMA News",
    "inquirer.net": "Inquirer.net",
    "mb.com.ph": "Manila Bulletin",
    "philstar.com": "Philstar.com",
    "rappler.com": "Rappler",
    "reuters.com": "Reuters",
    "verafiles.org": "VERA Files",
}


class SearchProviderError(RuntimeError):
    """Raised when a configured search provider cannot return a valid response."""


class UnsafeArticleUrlError(RuntimeError):
    """Raised when an article URL could reach a local or non-public address."""


@dataclass(frozen=True)
class ClaimFeatures:
    entities: list[str]
    keywords: list[str]
    event_categories: list[str]
    dates: list[str]
    locations: list[str]
    tokens: list[str]


@dataclass
class SearchResult:
    title: str
    url: str
    domain: str
    snippet: str
    published_date: str | None
    provider: str
    query: str
    image_url: str = ""
    trusted: bool = False
    relevance_score: int = 0


@dataclass(frozen=True)
class SearchOutcome:
    results: list[SearchResult]
    providers_used: list[str]
    any_provider_succeeded: bool


@dataclass(frozen=True)
class Article:
    headline: str
    article_text: str
    author: str
    publisher: str
    published_date: str | None
    updated_date: str | None
    canonical_url: str
    image_url: str


@dataclass
class EvidenceAnalysis:
    result: SearchResult
    article: Article | None
    relationship: Relationship
    similarity: int
    evidence_score: int
    source_tier: int
    recency_score: int
    explanation: str
    headline_match: int = 0
    rule_matches: list[str] = field(default_factory=list)
    transformation: str | None = None


def clean_claim_text(value: str) -> str:
    cleaned = unicodedata.normalize("NFKC", html_module.unescape(value))
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = cleaned.translate(
        str.maketrans(
            {
                "“": '"',
                "”": '"',
                "„": '"',
                "’": "'",
                "‘": "'",
                "`": "'",
            }
        )
    )
    cleaned = re.sub(r"([!?.,])\1+", r"\1", cleaned)
    cleaned = re.sub(r"[★☆◆◇■□►▶●•]+", " ", cleaned)
    cleaned = re.sub(r"\b([\w'-]+)(?:\s+\1){2,}\b", r"\1", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def normalize_search_text(value: str) -> str:
    normalized = clean_claim_text(value).lower()
    for phrase in NOISE_PHRASES:
        normalized = re.sub(rf"\b{re.escape(phrase)}\b", " ", normalized)
    normalized = re.sub(r"[^\w\s'-]", " ", normalized, flags=re.UNICODE)
    tokens = [
        token for token in normalized.split() if token not in STOPWORDS or token in TRUTH_TOKENS
    ]
    return " ".join(tokens)


def tokenize(value: str) -> list[str]:
    return re.findall(r"[\w]+(?:['-][\w]+)?", value.lower(), flags=re.UNICODE)


def stem_token(token: str) -> str:
    irregular = {
        "resignation": "resign",
        "resigned": "resign",
        "resigns": "resign",
        "resigning": "resign",
        "hospitalisation": "hospital",
        "hospitalization": "hospital",
        "hospitalized": "hospital",
        "hospitalised": "hospital",
        "dies": "die",
        "died": "die",
        "killed": "kill",
    }
    if token in irregular:
        return irregular[token]
    for suffix in ("ingly", "ation", "ments", "ment", "ingly", "edly", "ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def detect_event_categories(value: str) -> list[str]:
    lowered = value.lower()
    detected = [
        category
        for category, phrases in EVENT_KEYWORDS.items()
        if any(re.search(rf"\b{re.escape(phrase)}\b", lowered) for phrase in phrases)
        or any(
            re.search(pattern, lowered, flags=re.IGNORECASE)
            for pattern in EVENT_PATTERNS.get(category, ())
        )
    ]
    return detected


def extract_claim_features(cleaned_text: str) -> ClaimFeatures:
    tokens = tokenize(cleaned_text)
    keywords: list[str] = []
    for token in tokens:
        if token in STOPWORDS and token not in TRUTH_TOKENS:
            continue
        stemmed = stem_token(token)
        if len(stemmed) > 1 and stemmed not in keywords:
            keywords.append(stemmed)

    entity_matches = re.findall(
        r"\b(?:[A-Z][\w.-]+|[A-Z]{2,})(?:\s+(?:[A-Z][\w.-]+|[A-Z]{2,}|Jr\.?|Sr\.?)){0,4}",
        cleaned_text,
    )
    entities: list[str] = []
    blocked = {phrase.upper() for phrase in NOISE_PHRASES}
    for match in entity_matches:
        candidate = match.strip(" .,:;!?")
        parts = candidate.split()
        while parts and (parts[0].upper() in blocked or parts[0].lower() in STOPWORDS):
            parts.pop(0)
        while parts and (
            parts[-1].lower() in STOPWORDS
            or any(parts[-1].lower() in phrases for phrases in EVENT_KEYWORDS.values())
        ):
            parts.pop()
        candidate = " ".join(parts)
        if len(candidate) >= 2 and candidate.lower() not in {item.lower() for item in entities}:
            entities.append(candidate)

    date_pattern = (
        r"\b(?:today|yesterday|tomorrow|this morning|tonight|last night|this week|last week)\b"
        r"|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?\b"
        r"|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"
        r"|\b(?:19|20)\d{2}\b"
    )
    dates = list(dict.fromkeys(re.findall(date_pattern, cleaned_text, flags=re.IGNORECASE)))

    # Locations are critical facts for otherwise near-identical stories (for
    # example, two reports about Filipino casualties in different floods).
    # Keep this deliberately conservative: only proper-noun phrases following
    # common location prepositions are treated as places.
    location_matches = re.findall(
        r"\b(?:in|at|near|across|throughout|outside|inside|around)\s+(?:the\s+)?"
        r"([A-Z][\w.-]*(?:\s+[A-Z][\w.-]*){0,3})",
        cleaned_text,
    )
    locations = list(
        dict.fromkeys(match.strip(" .,:;!?") for match in location_matches if match.strip())
    )
    return ClaimFeatures(
        entities=entities[:10],
        keywords=keywords[:30],
        event_categories=detect_event_categories(cleaned_text),
        dates=dates[:10],
        locations=locations[:10],
        tokens=tokens,
    )


def generate_search_queries(cleaned_text: str, features: ClaimFeatures) -> list[str]:
    search_text = normalize_search_text(cleaned_text)
    queries: list[str] = []

    def add(query: str) -> None:
        query = " ".join(query.split()).strip()
        if query and query.lower() not in {item.lower() for item in queries}:
            queries.append(query[:300])

    add(search_text)

    # A common misinformation pattern keeps a real headline intact and appends
    # a short, inflammatory ending. Search a couple of progressively trimmed
    # headline prefixes early, before the extra words can steer retrieval to a
    # different event. The unquoted full claim remains the first query so
    # ordinary prose and paraphrases still work as expected.
    search_tokens = search_text.split()
    if len(search_tokens) >= 7:
        for trim_count in (2, 4):
            prefix = search_tokens[:-trim_count]
            if len(prefix) >= 5:
                add(f'"{" ".join(prefix)}"')

    add(f'"{search_text}"')
    add(" ".join(features.keywords[:10]))
    event_terms = [EVENT_KEYWORDS[category][0] for category in features.event_categories]
    add(" ".join([*features.entities[:2], *event_terms[:2]]))
    phrase_tokens = search_text.split()[:12]
    if len(phrase_tokens) >= 3:
        add(f'"{" ".join(phrase_tokens)}"')
    add(" ".join([*features.entities[:2], *event_terms[:2], "fact check"]))
    if features.event_categories:
        related_terms = EVENT_KEYWORDS[features.event_categories[0]][:3]
        add(" ".join([*features.entities[:2], *related_terms]))
    if features.dates:
        add(" ".join([*features.entities[:2], *event_terms[:2], *features.dates[:1]]))
    return queries[:8]


def normalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    host = parsed.hostname.lower().rstrip(".")
    port = parsed.port
    netloc = host
    if (
        port
        and not (parsed.scheme.lower() == "http" and port == 80)
        and not (parsed.scheme.lower() == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in TRACKING_PARAMETERS and not key.lower().startswith("utm_")
        )
    )
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urlunparse((parsed.scheme.lower(), netloc, path, "", query, ""))


def domain_matches(domain: str, configured_domain: str) -> bool:
    return domain == configured_domain or domain.endswith(f".{configured_domain}")


def _fuzzy_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    try:
        from rapidfuzz import fuzz

        return float(fuzz.token_set_ratio(left, right)) / 100.0
    except ImportError:
        return SequenceMatcher(None, left.lower(), right.lower()).ratio()


def _set_overlap(left: list[str], right: list[str]) -> float:
    left_set = {item.lower() for item in left}
    right_set = {item.lower() for item in right}
    if not left_set:
        return 0.0
    return len(left_set & right_set) / len(left_set)


def _entity_overlap(left: list[str], right: list[str]) -> float:
    if not left:
        return 0.0
    matched = 0
    for left_entity in left:
        left_tokens = {
            stem_token(token) for token in tokenize(left_entity) if token not in {"jr", "sr", "the"}
        }
        for right_entity in right:
            right_tokens = {
                stem_token(token)
                for token in tokenize(right_entity)
                if token not in {"jr", "sr", "the"}
            }
            token_match = (
                len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
                if left_tokens and right_tokens
                else 0.0
            )
            if token_match >= 0.5 or _fuzzy_ratio(left_entity, right_entity) >= 0.7:
                matched += 1
                break
    return matched / len(left)


def _locations_conflict(left: list[str], right: list[str]) -> bool:
    """Return true only when both texts name places and none of them match."""
    if not left or not right:
        return False
    return not any(
        _fuzzy_ratio(left_location, right_location) >= 0.82
        for left_location in left
        for right_location in right
    )


def _tfidf_cosine(left: str, right: str) -> float:
    left_terms = [stem_token(token) for token in tokenize(left) if token not in STOPWORDS]
    right_terms = [stem_token(token) for token in tokenize(right) if token not in STOPWORDS]
    if not left_terms or not right_terms:
        return 0.0
    left_count = Counter(left_terms)
    right_count = Counter(right_terms)
    vocabulary = set(left_count) | set(right_count)
    left_vector: dict[str, float] = {}
    right_vector: dict[str, float] = {}
    for term in vocabulary:
        document_frequency = int(term in left_count) + int(term in right_count)
        inverse_document_frequency = math.log(3 / (document_frequency + 1)) + 1
        left_vector[term] = (
            (1 + math.log(left_count[term])) * inverse_document_frequency if left_count[term] else 0
        )
        right_vector[term] = (
            (1 + math.log(right_count[term])) * inverse_document_frequency
            if right_count[term]
            else 0
        )
    dot_product = sum(left_vector[term] * right_vector[term] for term in vocabulary)
    left_norm = math.sqrt(sum(value * value for value in left_vector.values()))
    right_norm = math.sqrt(sum(value * value for value in right_vector.values()))
    return dot_product / (left_norm * right_norm) if left_norm and right_norm else 0.0


def score_initial_relevance(claim: ClaimFeatures, search_text: str, result: SearchResult) -> int:
    combined = f"{result.title} {result.snippet}"
    candidate = extract_claim_features(clean_claim_text(combined))
    entity_score = _entity_overlap(claim.entities, candidate.entities)
    event_score = 1.0 if set(claim.event_categories) & set(candidate.event_categories) else 0.0
    keyword_score = _set_overlap(claim.keywords, candidate.keywords)
    headline_coverage = _set_overlap(candidate.keywords, claim.keywords)
    title_score = _fuzzy_ratio(search_text, result.title)
    snippet_score = _fuzzy_ratio(search_text, result.snippet)
    date_score = 1.0 if not claim.dates or result.published_date else 0.4
    score = (
        entity_score * 22
        + event_score * 18
        + keyword_score * 16
        + headline_coverage * 20
        + title_score * 12
        + snippet_score * 7
        + date_score * 5
    )
    if _locations_conflict(claim.locations, candidate.locations):
        # A shared subject and event must not make a story from a different
        # place eligible as evidence for the submitted claim.
        score = min(score, 25)
    return max(0, min(100, round(score)))


def _parse_published_date(value: str | None, now: datetime) -> datetime | None:
    if not value:
        return None
    lowered = value.strip().lower()
    relative = re.fullmatch(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", lowered)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        days = {
            "minute": amount / 1440,
            "hour": amount / 24,
            "day": amount,
            "week": amount * 7,
            "month": amount * 30,
            "year": amount * 365,
        }[unit]
        return now - timedelta(days=days)
    try:
        parsed = date_parser.parse(value, fuzzy=True)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _extract_result_date(item: dict[str, Any]) -> str | None:
    direct = item.get("date") or item.get("published_date") or item.get("publishedDate")
    if direct:
        return str(direct)
    metatags = (
        item.get("pagemap", {}).get("metatags", []) if isinstance(item.get("pagemap"), dict) else []
    )
    for metadata in metatags:
        for key in ("article:published_time", "datepublished", "date", "datecreated"):
            if metadata.get(key):
                return str(metadata[key])
    return None


def _extract_result_image(item: dict[str, Any]) -> str:
    candidates: list[object] = [
        item.get("thumbnail"),
        item.get("thumbnailUrl"),
        item.get("image"),
        item.get("imageUrl"),
        item.get("image_url"),
        item.get("images"),
    ]
    pagemap = item.get("pagemap")
    if isinstance(pagemap, dict):
        for collection_name in ("cse_image", "cse_thumbnail"):
            collection = pagemap.get(collection_name)
            if isinstance(collection, list):
                candidates.extend(
                    entry.get("src")
                    for entry in collection
                    if isinstance(entry, dict)
                )
        metatags = pagemap.get("metatags")
        if isinstance(metatags, list):
            for metadata in metatags:
                if not isinstance(metadata, dict):
                    continue
                candidates.extend(
                    metadata.get(key)
                    for key in ("og:image", "twitter:image", "twitter:image:src")
                )

    def strings(value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [
                candidate
                for key in ("url", "src", "link", "imageUrl", "thumbnailUrl")
                if isinstance((candidate := value.get(key)), str)
            ]
        if isinstance(value, list):
            return [candidate for entry in value for candidate in strings(entry)]
        return []

    for candidate in candidates:
        for raw_url in strings(candidate):
            if raw_url.startswith("//"):
                raw_url = f"https:{raw_url}"
            normalized = normalize_url(html_module.unescape(raw_url))
            if normalized:
                return normalized
    return ""


class NewsSearchClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _provider_is_configured(self, provider: str) -> bool:
        if provider == "google":
            return bool(self.settings.google_search_api_key and self.settings.google_cse_id)
        if provider == "searchapi":
            return self.settings.searchapi_api_key is not None
        if provider == "serper":
            return self.settings.serper_api_key is not None
        return False

    async def search(
        self,
        queries: list[str],
        *,
        restricted_domains: list[str] | None,
        result_filter: Callable[[SearchResult], bool] | None = None,
    ) -> SearchOutcome:
        collected: list[SearchResult] = []
        providers_used: list[str] = []
        any_success = False
        query_limit = min(5, len(queries))
        timeout = httpx.Timeout(self.settings.news_search_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for provider in self.settings.news_search_provider_list:
                if not self._provider_is_configured(provider):
                    continue
                providers_used.append(provider)
                provider_succeeded = False
                for query_index, base_query in enumerate(queries[:query_limit]):
                    query = self._restrict_query(base_query, restricted_domains)
                    try:
                        batch = await self._search_provider(client, provider, query)
                    except (SearchProviderError, httpx.HTTPError, ValueError):
                        logger.warning("News search provider %s failed; trying fallback", provider)
                        break
                    any_success = True
                    provider_succeeded = True
                    collected.extend(batch)
                    collected = deduplicate_results(collected)
                    useful_results = (
                        [item for item in collected if result_filter(item)]
                        if result_filter
                        else collected
                    )
                    # Always try the first three query views. In particular, the
                    # second and third views remove possible appended wording
                    # from an altered headline.
                    if (
                        query_index >= 2
                        and len(useful_results) >= self.settings.news_min_relevant_results
                    ):
                        break
                useful_results = (
                    [item for item in collected if result_filter(item)]
                    if result_filter
                    else collected
                )
                if (
                    provider_succeeded
                    and len(useful_results) >= self.settings.news_min_relevant_results
                ):
                    break
        return SearchOutcome(
            # The verifier scores and caps the combined results. Capping here by
            # provider order could discard a much stronger match found by a
            # later, trimmed query.
            results=collected,
            providers_used=providers_used,
            any_provider_succeeded=any_success,
        )

    @staticmethod
    def _restrict_query(query: str, domains: list[str] | None) -> str:
        if not domains:
            return query
        restrictions = " OR ".join(f"site:{domain}" for domain in domains)
        return f"{query} ({restrictions})"

    async def _search_provider(
        self, client: httpx.AsyncClient, provider: str, query: str
    ) -> list[SearchResult]:
        if provider == "google":
            assert self.settings.google_search_api_key is not None
            response = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                headers={"X-Goog-Api-Key": self.settings.google_search_api_key.get_secret_value()},
                params={
                    "cx": self.settings.google_cse_id,
                    "q": query,
                    "num": 10,
                },
            )
            items_key = "items"
        elif provider == "searchapi":
            assert self.settings.searchapi_api_key is not None
            response = await client.get(
                "https://www.searchapi.io/api/v1/search",
                headers={
                    "Authorization": (
                        f"Bearer {self.settings.searchapi_api_key.get_secret_value()}"
                    )
                },
                params={
                    "engine": "google",
                    "q": query,
                    "num": 10,
                },
            )
            items_key = "organic_results"
        elif provider == "serper":
            assert self.settings.serper_api_key is not None
            response = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": self.settings.serper_api_key.get_secret_value()},
                json={"q": query, "num": 10},
            )
            items_key = "organic"
        else:
            raise SearchProviderError(f"Unsupported provider: {provider}")

        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SearchProviderError(f"{provider} returned an invalid response") from exc
        if not isinstance(payload, dict) or payload.get("error"):
            raise SearchProviderError(f"{provider} returned an error response")
        items = payload.get(items_key, [])
        if not isinstance(items, list):
            raise SearchProviderError(f"{provider} returned malformed results")

        results: list[SearchResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_url = str(item.get("link") or item.get("url") or "")
            url = normalize_url(raw_url)
            if not url:
                continue
            domain = urlparse(url).hostname or ""
            if any(
                domain_matches(domain.lower(), blocked)
                for blocked in ("google.com", "searchapi.io", "serper.dev")
            ):
                continue
            results.append(
                SearchResult(
                    title=html_module.unescape(str(item.get("title") or "Untitled result")),
                    url=url,
                    domain=domain.lower(),
                    snippet=html_module.unescape(str(item.get("snippet") or "")),
                    published_date=_extract_result_date(item),
                    provider=provider,
                    query=query,
                    image_url=_extract_result_image(item),
                )
            )
        return results


def deduplicate_results(results: list[SearchResult]) -> list[SearchResult]:
    unique: list[SearchResult] = []
    seen_urls: set[str] = set()
    for result in results:
        normalized = normalize_url(result.url)
        dedupe_key = normalized.rstrip("/")
        if not normalized or dedupe_key in seen_urls:
            continue
        duplicate_title = next(
            (
                existing
                for existing in unique
                if _fuzzy_ratio(existing.title, result.title) >= 0.96 and len(existing.title) >= 20
            ),
            None,
        )
        if duplicate_title is not None:
            continue
        result.url = normalized
        seen_urls.add(dedupe_key)
        unique.append(result)
    return unique


async def _validate_public_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeArticleUrlError("Only public HTTP and HTTPS URLs are allowed")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "0.0.0.0"} or host.endswith(".localhost"):
        raise UnsafeArticleUrlError("Local network URLs are not allowed")
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise UnsafeArticleUrlError("Article hostname could not be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise UnsafeArticleUrlError("Local or reserved network addresses are not allowed")


class ArticleScraper:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def scrape(self, value: str) -> Article | None:
        current_url = normalize_url(value)
        if not current_url:
            return None
        timeout = httpx.Timeout(self.settings.news_scrape_timeout_seconds)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            for redirect_count in range(self.settings.news_max_redirects + 1):
                await _validate_public_url(current_url)
                try:
                    async with client.stream(
                        "GET", current_url, follow_redirects=False
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            if redirect_count >= self.settings.news_max_redirects:
                                return None
                            location = response.headers.get("location")
                            if not location:
                                return None
                            current_url = normalize_url(urljoin(current_url, location))
                            if not current_url:
                                return None
                            continue
                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "").lower()
                        if not any(
                            allowed in content_type
                            for allowed in ("text/html", "application/xhtml+xml")
                        ):
                            return None
                        declared_size = int(response.headers.get("content-length", "0") or 0)
                        if declared_size > self.settings.news_max_article_bytes:
                            return None
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > self.settings.news_max_article_bytes:
                                return None
                        return self._extract_article(
                            body.decode(response.encoding or "utf-8", errors="replace"),
                            current_url,
                        )
                except (httpx.HTTPError, ValueError):
                    logger.info("Article retrieval failed for %s", current_url, exc_info=True)
                    return None
        return None

    @staticmethod
    def _extract_article(document: str, source_url: str) -> Article | None:
        soup = BeautifulSoup(document, "html.parser")
        for element in soup(["script", "style", "nav", "footer", "aside", "form", "noscript"]):
            element.decompose()

        def meta_value(*names: str) -> str:
            for name in names:
                element = soup.find("meta", attrs={"property": name}) or soup.find(
                    "meta", attrs={"name": name}
                )
                if element and element.get("content"):
                    return str(element["content"]).strip()
            return ""

        headline = meta_value("og:title", "twitter:title")
        if not headline and soup.title:
            headline = soup.title.get_text(" ", strip=True)
        article_text = ""
        author = meta_value("author", "article:author")
        published = meta_value("article:published_time", "datePublished", "date") or None
        updated = meta_value("article:modified_time", "dateModified") or None
        publisher = meta_value("og:site_name", "application-name")
        raw_image_url = meta_value("og:image", "twitter:image", "twitter:image:src")
        image_url = normalize_url(urljoin(source_url, raw_image_url)) if raw_image_url else ""
        canonical_element = soup.find("link", attrs={"rel": "canonical"})
        canonical = source_url
        if canonical_element and canonical_element.get("href"):
            candidate = normalize_url(urljoin(source_url, str(canonical_element["href"])))
            canonical = candidate or source_url
        try:
            import trafilatura

            article_text = (
                trafilatura.extract(
                    document,
                    include_comments=False,
                    include_tables=False,
                    no_fallback=False,
                )
                or ""
            )
        except (ImportError, RuntimeError, ValueError):
            logger.debug("Trafilatura extraction failed", exc_info=True)
        if not article_text:
            main = soup.find("article") or soup.find("main") or soup.body
            article_text = main.get_text(" ", strip=True) if main else ""
        article_text = " ".join(article_text.split())[:250_000]
        if len(article_text) < 80:
            return None
        return Article(
            headline=clean_claim_text(headline),
            article_text=article_text,
            author=clean_claim_text(author),
            publisher=clean_claim_text(publisher),
            published_date=published,
            updated_date=updated,
            canonical_url=canonical,
            image_url=image_url,
        )


def _source_tier(domain: str, settings: Settings) -> int:
    if any(domain_matches(domain, item) for item in settings.trusted_news_domain_list):
        return 1
    if domain == "gov.ph" or domain.endswith(".gov.ph") or domain_matches(domain, "verafiles.org"):
        return 1
    if any(domain_matches(domain, item) for item in settings.news_tier_2_domain_list):
        return 2
    if any(name in domain for name in ("facebook.com", "x.com", "twitter.com", "reddit.com")):
        return 4
    return 3


def _publisher_name(result: SearchResult, article: Article | None) -> str:
    if article and article.publisher:
        return article.publisher
    for domain, name in PUBLISHER_NAMES.items():
        if domain_matches(result.domain, domain):
            return name
    return result.domain.removeprefix("www.")


def _recency_score(date_value: str | None, now: datetime) -> int:
    published = _parse_published_date(date_value, now)
    if published is None:
        return 55
    age_days = max(0, (now - published).days)
    if age_days <= 7:
        return 100
    if age_days <= 30:
        return 85
    if age_days <= 365:
        return 65
    return 35


def _negates_category(document: str, category: str) -> bool:
    words = tokenize(document)
    aliases = EVENT_KEYWORDS.get(category, ())
    for alias in aliases:
        alias_words = tokenize(alias)
        for index in range(0, len(words) - len(alias_words) + 1):
            if words[index : index + len(alias_words)] != alias_words:
                continue
            window = words[max(0, index - 4) : index]
            if any(word in NEGATION_WORDS for word in window):
                return True
    return False


def _relationship(
    claim: ClaimFeatures,
    document: str,
    similarity: int,
) -> tuple[Relationship, list[str], str | None]:
    lowered = document.lower()
    document_features = extract_claim_features(clean_claim_text(document[:30_000]))
    opening_features = extract_claim_features(clean_claim_text(document[:2_000]))
    if _locations_conflict(claim.locations, opening_features.locations):
        return "IRRELEVANT", ["The report names a different location."], None
    entity_overlap = _entity_overlap(claim.entities, document_features.entities)
    keyword_overlap = _set_overlap(claim.keywords, document_features.keywords)
    relevant_context = entity_overlap > 0 or keyword_overlap >= 0.2 or similarity >= 45
    rule_matches: list[str] = []

    # Article extractors can retain unrelated-story links near the footer. Limit
    # debunk rules to the headline, snippet, and opening article context.
    debunk_scope = lowered[:2000]
    if relevant_context and any(phrase in debunk_scope for phrase in DEBUNK_PHRASES):
        rule_matches.append("Explicit fact-check or debunk language matched the claim context.")
        return "DEBUNKS", rule_matches, None

    for category in claim.event_categories:
        if _negates_category(document, category) and relevant_context:
            rule_matches.append(f"{category}: event is explicitly negated")
            return "CONTRADICTS", rule_matches, None
        for pattern, label in CONTRADICTION_PATTERNS.get(category, ()):
            if category == "POLICY_APPROVED" and category in document_features.event_categories:
                continue
            if re.search(pattern, lowered, flags=re.IGNORECASE) and relevant_context:
                rule_matches.append(f"{category}: {label}")
                return "CONTRADICTS", rule_matches, None

    if "POLICY_APPROVED" in claim.event_categories and relevant_context:
        pending_pattern = (
            r"\b(?:set|scheduled|expected|due|plans?|planned|will)\b.{0,45}"
            r"\b(?:sign|signing|signature)\b|\bup for signature\b"
        )
        if re.search(pending_pattern, lowered[:1500], flags=re.IGNORECASE):
            transformation = (
                "A scheduled or pending signing may have been presented as already completed."
            )
            rule_matches.append(transformation)
            return "RELATED", rule_matches, transformation

    for claim_event in claim.event_categories:
        for article_event in document_features.event_categories:
            transformation = TRANSFORMATIONS.get((claim_event, article_event))
            if (
                transformation
                and claim_event not in document_features.event_categories
                and relevant_context
            ):
                rule_matches.append(transformation)
                return "RELATED", rule_matches, transformation

    same_event = bool(set(claim.event_categories) & set(document_features.event_categories))
    if relevant_context and (
        (same_event and similarity >= 45 and keyword_overlap >= 0.35)
        or (similarity >= 65 and keyword_overlap >= 0.30)
    ):
        return "SUPPORTS", rule_matches, None
    if relevant_context and similarity >= 35 and keyword_overlap >= 0.25:
        return "RELATED", rule_matches, None
    return "IRRELEVANT", rule_matches, None


def _similarity_score(
    claim: ClaimFeatures,
    cleaned_text: str,
    result: SearchResult,
    article: Article | None,
    now: datetime,
) -> tuple[int, dict[str, int]]:
    body = article.article_text if article else ""
    headline = article.headline if article and article.headline else result.title
    document = f"{headline} {result.snippet} {body}"
    document_features = extract_claim_features(clean_claim_text(document[:30_000]))
    entity = round(_entity_overlap(claim.entities, document_features.entities) * 100)
    event = 100 if set(claim.event_categories) & set(document_features.event_categories) else 0
    tfidf = round(_tfidf_cosine(cleaned_text, document) * 100)
    fuzzy = round(_fuzzy_ratio(cleaned_text, headline) * 100)
    keyword = round(_set_overlap(claim.keywords, document_features.keywords) * 100)
    date = _recency_score(
        (article.published_date if article else None) or result.published_date,
        now,
    )
    weighted = round(
        entity * 0.25 + event * 0.20 + tfidf * 0.20 + fuzzy * 0.15 + keyword * 0.10 + date * 0.10
    )
    location = 0 if _locations_conflict(claim.locations, document_features.locations) else 100
    if location == 0:
        weighted = min(weighted, 25)
    return max(0, min(100, weighted)), {
        "entity": entity,
        "event": event,
        "tfidf": tfidf,
        "fuzzy_title": fuzzy,
        "keyword": keyword,
        "date": date,
        "location": location,
    }


def _relationship_explanation(
    relationship: Relationship,
    transformation: str | None,
    rule_matches: list[str],
) -> str:
    if transformation:
        return transformation
    if relationship == "DEBUNKS":
        return "This source explicitly labels the matching claim as false or misleading."
    if relationship == "CONTRADICTS":
        detail = rule_matches[0] if rule_matches else "a critical fact conflicts"
        return f"This report contradicts the claim because {detail.lower()}."
    if relationship == "SUPPORTS":
        return "This report directly matches the claim's entities and reported event."
    if relationship == "RELATED":
        return "This report covers a closely related event but does not confirm the exact claim."
    return "The result is not sufficiently related to the claim."


def _headline_match_and_mutation(claim_text: str, headline: str) -> tuple[int, str | None]:
    """Score a headline against the leading claim and detect appended wording."""
    claim_terms = [
        stem_token(token)
        for token in tokenize(claim_text)
        if token not in STOPWORDS and len(stem_token(token)) > 1
    ]
    headline_terms = [
        stem_token(token)
        for token in tokenize(headline)
        if token not in STOPWORDS and len(stem_token(token)) > 1
    ]
    if not claim_terms or not headline_terms:
        return 0, None

    leading_claim = claim_terms[: len(headline_terms)]
    prefix_similarity = _fuzzy_ratio(" ".join(leading_claim), " ".join(headline_terms))
    headline_coverage = _set_overlap(headline_terms, claim_terms)
    claim_coverage = _set_overlap(claim_terms, headline_terms)
    score = round(
        prefix_similarity * 45 + headline_coverage * 35 + claim_coverage * 20
    )

    # Only call this a mutation when a substantial real headline matches the
    # beginning of the submitted text and meaningful words were added. This is
    # intentionally stricter than general fuzzy similarity.
    if (
        len(headline_terms) >= 5
        and len(claim_terms) > len(headline_terms)
        and prefix_similarity >= 0.86
        and headline_coverage >= 0.85
    ):
        headline_counts = Counter(headline_terms)
        extras: list[str] = []
        for term in claim_terms:
            if headline_counts[term]:
                headline_counts[term] -= 1
            else:
                extras.append(term)
        if extras:
            added_words = " ".join(extras[:6])
            return (
                max(score, 90),
                "A real headline appears to have been altered by adding "
                f'“{added_words}.” The linked report does not confirm that added wording.',
            )
    return max(0, min(100, score)), None


class NewsVerifier:
    def __init__(
        self,
        settings: Settings,
        *,
        search_client: NewsSearchClient | None = None,
        scraper: ArticleScraper | None = None,
    ) -> None:
        self.settings = settings
        self.search_client = search_client or NewsSearchClient(settings)
        self.scraper = scraper or ArticleScraper(settings)

    async def verify(self, raw_text: str) -> dict[str, Any]:
        now = datetime.now(UTC)
        cleaned = clean_claim_text(raw_text)
        search_text = normalize_search_text(cleaned)
        features = extract_claim_features(cleaned)
        queries = generate_search_queries(cleaned, features)

        def relevance_filter(result: SearchResult) -> bool:
            return (
                score_initial_relevance(features, search_text, result)
                >= self.settings.news_relevance_threshold
            )

        # Search national and regional Philippine outlets, not the unrestricted
        # web. This discovery scope is intentionally broader than the trusted
        # list, which remains only a credibility signal.
        outlet_domains = self.settings.philippine_news_domain_list
        search_outcome = await self.search_client.search(
            queries,
            restricted_domains=outlet_domains,
            result_filter=relevance_filter,
        )
        results = deduplicate_results(
            [
                result
                for result in search_outcome.results
                if any(domain_matches(result.domain, domain) for domain in outlet_domains)
            ]
        )
        providers_used = list(search_outcome.providers_used)
        any_provider_succeeded = search_outcome.any_provider_succeeded

        for result in results:
            result.trusted = any(
                domain_matches(result.domain, domain)
                for domain in self.settings.trusted_news_domain_list
            )
            result.relevance_score = score_initial_relevance(features, search_text, result)
        relevant = sorted(
            (
                result
                for result in results
                if result.relevance_score >= self.settings.news_relevance_threshold
            ),
            # Match quality chooses candidates; source reputation is used later
            # when weighing evidence and deciding the verdict.
            key=lambda item: (item.relevance_score, item.trusted),
            reverse=True,
        )[: self.settings.news_max_search_results]

        if not any_provider_succeeded and not results:
            return self._empty_response(
                status="SEARCH_UNAVAILABLE",
                raw_text=raw_text,
                cleaned=cleaned,
                search_text=search_text,
                features=features,
                queries=queries,
                providers_used=providers_used,
                total_results=0,
                explanation=(
                    "The configured search providers are temporarily unavailable. "
                    "The claim has not been classified as false and remains unverified."
                ),
            )

        scrape_targets = relevant[: self.settings.news_max_articles_to_scrape]
        scraped = await asyncio.gather(
            *(self._safe_scrape(result.url) for result in scrape_targets)
        )
        article_by_url = {
            result.url: article
            for result, article in zip(scrape_targets, scraped, strict=True)
            if article is not None
        }

        analyses: list[EvidenceAnalysis] = []
        debug_scores: list[dict[str, object]] = []
        all_rules: list[str] = []
        for result in relevant:
            article = article_by_url.get(result.url)
            similarity, components = _similarity_score(features, cleaned, result, article, now)
            document = " ".join(
                (
                    article.headline if article else result.title,
                    result.snippet,
                    article.article_text if article else "",
                )
            )
            relationship, rules, transformation = _relationship(features, document, similarity)
            headline_candidates = [result.title]
            if article and article.headline:
                headline_candidates.append(article.headline)
            headline_matches = [
                _headline_match_and_mutation(cleaned, headline)
                for headline in headline_candidates
            ]
            headline_match, headline_mutation = max(
                headline_matches,
                key=lambda item: (item[0], item[1] is not None),
            )
            if headline_mutation and relationship in {"SUPPORTS", "RELATED"}:
                relationship = "RELATED"
                transformation = headline_mutation
                rules = [*rules, headline_mutation]
            if relationship == "IRRELEVANT":
                continue
            tier = _source_tier(result.domain, self.settings)
            date_value = (article.published_date if article else None) or result.published_date
            recency = _recency_score(date_value, now)
            relationship_weight = {
                "SUPPORTS": 100,
                "CONTRADICTS": 92,
                "DEBUNKS": 100,
                "RELATED": 55,
                "IRRELEVANT": 0,
            }[relationship]
            source_weight = {1: 100, 2: 80, 3: 50, 4: 20}[tier]
            evidence_score = round(
                similarity * 0.30
                + source_weight * 0.25
                + relationship_weight * 0.25
                + recency * 0.10
                + 100 * 0.10
            )
            analyses.append(
                EvidenceAnalysis(
                    result=result,
                    article=article,
                    relationship=relationship,
                    similarity=similarity,
                    evidence_score=max(0, min(100, evidence_score)),
                    source_tier=tier,
                    recency_score=recency,
                    explanation=_relationship_explanation(relationship, transformation, rules),
                    headline_match=headline_match,
                    rule_matches=rules,
                    transformation=transformation,
                )
            )
            all_rules.extend(rules)
            if self.settings.news_debug:
                debug_scores.append(
                    {
                        "url": result.url,
                        "relationship": relationship,
                        "total": similarity,
                        **components,
                    }
                )

        analyses.sort(key=lambda item: item.evidence_score, reverse=True)
        verdict, confidence, explanation = self._decide_verdict(analyses, features, now)
        return self._response(
            status="SUCCESS",
            raw_text=raw_text,
            cleaned=cleaned,
            search_text=search_text,
            features=features,
            verdict=verdict,
            confidence=confidence,
            explanation=explanation,
            analyses=analyses,
            queries=queries,
            providers_used=providers_used,
            total_results=len(results),
            articles_scraped=len(article_by_url),
            debug_scores=debug_scores,
            rule_matches=list(dict.fromkeys(all_rules)),
        )

    async def _safe_scrape(self, url: str) -> Article | None:
        try:
            return await self.scraper.scrape(url)
        except (UnsafeArticleUrlError, OSError, RuntimeError):
            logger.info("Article was not scraped: %s", url, exc_info=True)
            return None

    def _decide_verdict(
        self,
        analyses: list[EvidenceAnalysis],
        features: ClaimFeatures,
        now: datetime,
    ) -> tuple[str, int, str]:
        credible = [item for item in analyses if item.source_tier <= 2]
        supports = [item for item in credible if item.relationship == "SUPPORTS"]
        contradicts = [item for item in credible if item.relationship == "CONTRADICTS"]
        debunks = [item for item in credible if item.relationship == "DEBUNKS"]
        transformations = [item for item in credible if item.transformation]
        independent_supporters = {item.result.domain for item in supports}
        independent_contradictions = {item.result.domain for item in [*contradicts, *debunks]}

        has_relative_date = any(
            relative in " ".join(features.dates).lower() for relative in RELATIVE_DATES
        )
        old_matches = []
        if has_relative_date:
            for item in [*supports, *transformations]:
                date_value = (
                    item.article.published_date if item.article else None
                ) or item.result.published_date
                published = _parse_published_date(date_value, now)
                if published and (now - published).days > self.settings.news_old_story_days:
                    old_matches.append(item)
        recent_support = [item for item in supports if item not in old_matches]

        if debunks and supports and len(independent_supporters) >= 2:
            return (
                "UNVERIFIED",
                65,
                (
                    "Credible sources conflict about the claim. The available evidence "
                    "does not support a definitive verdict yet."
                ),
            )
        if debunks:
            confidence = min(99, 88 + len(independent_contradictions) * 4)
            publishers = self._publisher_summary(debunks)
            return (
                "FALSE",
                confidence,
                f"Credible fact-checking from {publishers} explicitly rejects this claim.",
            )
        if len(independent_contradictions) >= 2:
            publishers = self._publisher_summary([*contradicts, *debunks])
            return (
                "FALSE",
                min(98, 84 + len(independent_contradictions) * 4),
                (
                    f"Multiple independent credible reports from {publishers} contradict "
                    "the claim's critical facts."
                ),
            )
        if old_matches and not recent_support:
            return (
                "MISLEADING",
                min(94, 72 + max(item.evidence_score for item in old_matches) // 5),
                (
                    "A related real story was found, but its publication date does not "
                    "match the claim's current framing. The claim appears to reuse old "
                    "news as a current event."
                ),
            )
        if transformations and not supports:
            closest = transformations[0]
            return (
                "MISLEADING",
                min(94, 65 + closest.evidence_score // 4),
                closest.transformation
                or "A related real event appears to have been presented with changed context.",
            )
        if contradicts:
            publishers = self._publisher_summary(contradicts)
            return (
                "LIKELY_FALSE",
                min(92, 62 + max(item.evidence_score for item in contradicts) // 3),
                (
                    f"Credible reporting from {publishers} conflicts with the claim, but "
                    "there is not yet enough independent evidence for a definitive false "
                    "verdict."
                ),
            )
        if len(independent_supporters) >= 2:
            publishers = self._publisher_summary(supports)
            return (
                "VERIFIED",
                min(98, 80 + len(independent_supporters) * 4),
                (
                    f"Multiple independent credible reports from {publishers} support "
                    "the claim's central event and entities."
                ),
            )
        if supports:
            publishers = self._publisher_summary(supports)
            return (
                "LIKELY_TRUE",
                min(91, 58 + max(item.evidence_score for item in supports) // 3),
                (
                    f"Credible reporting from {publishers} supports the claim, but "
                    "independent confirmation is limited."
                ),
            )
        related = [item for item in credible if item.relationship == "RELATED"]
        if related:
            return (
                "LIKELY_FALSE",
                min(72, 40 + related[0].evidence_score // 5),
                (
                    "Reliable sources report related stories, but none match the main "
                    "event in this claim. This story is likely false."
                ),
            )
        if analyses:
            return (
                "UNVERIFIED",
                min(65, 30 + analyses[0].evidence_score // 3),
                (
                    "We found related coverage, but not enough direct evidence to "
                    "confirm the exact claim."
                ),
            )
        return (
            "UNVERIFIED",
            35,
            (
                "We could not find enough matching coverage to confirm the exact "
                "claim. That does not mean the claim is false."
            ),
        )

    @staticmethod
    def _publisher_summary(items: list[EvidenceAnalysis]) -> str:
        names = list(dict.fromkeys(_publisher_name(item.result, item.article) for item in items))
        if len(names) <= 2:
            return " and ".join(names)
        return f"{', '.join(names[:2])}, and others"

    def _evidence_item(self, analysis: EvidenceAnalysis) -> dict[str, Any]:
        article = analysis.article
        result = analysis.result
        return {
            "title": article.headline if article and article.headline else result.title,
            "publisher": _publisher_name(result, article),
            "url": article.canonical_url if article else result.url,
            "domain": result.domain,
            "published_date": (
                article.published_date
                if article and article.published_date
                else result.published_date
            ),
            "image_url": article.image_url if article and article.image_url else result.image_url,
            "relationship": analysis.relationship,
            "similarity": analysis.similarity,
            "evidence_score": analysis.evidence_score,
            "source_tier": analysis.source_tier,
            "explanation": analysis.explanation,
        }

    def _response(
        self,
        *,
        status: str,
        raw_text: str,
        cleaned: str,
        search_text: str,
        features: ClaimFeatures,
        verdict: str,
        confidence: int,
        explanation: str,
        analyses: list[EvidenceAnalysis],
        queries: list[str],
        providers_used: list[str],
        total_results: int,
        articles_scraped: int,
        debug_scores: list[dict[str, object]],
        rule_matches: list[str],
    ) -> dict[str, Any]:
        groups = {
            "supporting": [],
            "contradicting": [],
            "related": [],
            "debunks": [],
        }
        group_names = {
            "SUPPORTS": "supporting",
            "CONTRADICTS": "contradicting",
            "RELATED": "related",
            "DEBUNKS": "debunks",
        }
        for analysis in analyses:
            group = group_names.get(analysis.relationship)
            if group:
                groups[group].append(self._evidence_item(analysis))

        closest_candidates = [
            item for item in analyses if item.relationship in {"RELATED", "CONTRADICTS", "DEBUNKS"}
        ]
        closest = (
            max(
                closest_candidates,
                key=lambda item: (item.headline_match, item.similarity, item.evidence_score),
            )
            if closest_candidates
            else None
        )
        closest_story = {
            "found": closest is not None and verdict not in {"VERIFIED", "LIKELY_TRUE"},
            "title": "",
            "publisher": "",
            "url": "",
            "date": "",
            "similarity": 0,
            "explanation": "",
            "image_url": "",
        }
        if closest_story["found"] and closest:
            item = self._evidence_item(closest)
            closest_story.update(
                {
                    "title": item["title"],
                    "publisher": item["publisher"],
                    "url": item["url"],
                    "date": item["published_date"] or "",
                    "similarity": item["similarity"],
                    "explanation": closest.explanation,
                    "image_url": item["image_url"],
                }
            )

        return {
            "status": status,
            "original_text": raw_text,
            "cleaned_text": cleaned,
            "search_text": search_text,
            "detected": {
                "entities": features.entities,
                "keywords": features.keywords,
                "event_categories": features.event_categories,
                "dates": features.dates,
            },
            "verdict": verdict,
            "confidence": confidence,
            "explanation": explanation,
            "evidence": groups,
            "closest_real_story": closest_story,
            "search": {
                "queries": queries,
                "providers_used": providers_used,
                "outlet_domains_searched": self.settings.philippine_news_domain_list,
                "total_results": total_results,
                "articles_scraped": articles_scraped,
            },
            "debug": {
                "enabled": self.settings.news_debug,
                "similarity_scores": debug_scores if self.settings.news_debug else [],
                "rule_matches": rule_matches if self.settings.news_debug else [],
            },
        }

    def _empty_response(
        self,
        *,
        status: str,
        raw_text: str,
        cleaned: str,
        search_text: str,
        features: ClaimFeatures,
        queries: list[str],
        providers_used: list[str],
        total_results: int,
        explanation: str,
    ) -> dict[str, Any]:
        return self._response(
            status=status,
            raw_text=raw_text,
            cleaned=cleaned,
            search_text=search_text,
            features=features,
            verdict="UNVERIFIED",
            confidence=0,
            explanation=explanation,
            analyses=[],
            queries=queries,
            providers_used=providers_used,
            total_results=total_results,
            articles_scraped=0,
            debug_scores=[],
            rule_matches=[],
        )
