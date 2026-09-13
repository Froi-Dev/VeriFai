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

from app.Global.config import Settings

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
    "pag",
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
        "ill-stricken",
        "medical emergency",
        "recovering",
        "stable condition",
        "stroke",
        "icu",
        "intensive care",
        "confined",
        "medical condition",
        "health scare",
        "collapsed",
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
    "TRIAL": (
        "trial",
        "impeachment",
        "impeachment trial",
        "prosecution",
        "prosecutor",
        "witness",
        "testify",
        "testimony",
        "hearing",
        "court proceeding",
        "cross-examination",
        "witness stand",
        "senate court",
        "impeachment court",
        "presiding officer",
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
        "already banned",
        "banned",
        "ipinagbawal",
    ),
    "POLICY_CONSIDERATION": (
        "bukas sa posibilidad",
        "maaaring ipagbawal",
        "open to the possibility",
        "under study",
        "possible ban",
        "possible restrictions",
    ),
    "POLICY_PROPOSAL": (
        "proposal",
        "proposed",
        "draft",
        "bill filed",
        "under discussion",
        "not yet passed",
        "panukalang pagbabawal",
        "panukala",
    ),
    "NUCLEAR_PREPARATION": (
        "nuclear energy preparations",
        "moving closer to nuclear energy",
        "nuclear power plans",
        "atomic energy plans advance",
        "nuclear plant sites",
    ),
    "RETURN_FROM_CUSTODY": (
        "return to the philippines",
        "returning to the philippines",
        "coming home",
        "uuwi",
        "released from custody",
    ),
    "INSTITUTION_DISMANTLED": (
        "will be dismantled",
        "being dismantled",
        "madidismantle",
        "abolish the court",
    ),
    "SATIRE": (
        "satire",
        "parody",
        "satirical",
        "humor",
        "comedy",
        "joke",
        "not real news",
    ),
}

EVENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "DEATH": (r"\b(di(?:e[ds]?|ed)|dead|death|kill(?:ed)?)\b",),
    "HEALTH": (
        r"\bhospitali[sz](?:e|ed|ation)\b",
        r"\bstable condition\b",
        r"\b(?:stroke|icu|intensive\s+care)\b",
        r"\bill[- ]stricken\b",
        r"\bconfined\s+(?:in|at)\b",
    ),
    "ARREST": (r"\b(arrest(?:ed)?|detain(?:ed)?|apprehend(?:ed)?)\b",),
    "CONVICTION": (r"\bconvict(?:ed|ion)?\b", r"\bfound guilty\b"),
    "TRIAL": (
        r"\b(?:impeachment\s+)?trial\b",
        r"\bprosecuti(?:on|or)\b",
        r"\btestif(?:y|ied|ies)\b",
        r"\btestimon(?:y|ies)\b",
        r"\bhearing(?:s)?\b.{0,60}\b(?:senate|house|court|committee)\b",
        r"\bwitness\s+stand\b",
        r"\bcross[- ]examin(?:e|ed|ation)\b",
        r"\bimpeach(?:ed|ment|ing)?\b",
    ),
    "RESIGNATION": (r"\bresign(?:ed|s|ation|ing)?\b", r"\bsteps? down\b"),
    "POLICY_APPROVED": (
        r"\bsign(?:ed|s)?\b.{0,90}\b(?:law|act|bill)\b",
        r"\b(?:law|act|bill)\b.{0,90}\bsign(?:ed|s)?\b",
        r"\bapprov(?:e|ed|es|al)\b.{0,90}\b(?:law|act|bill)\b",
        r"\b(?:order(?:ed)?|approv(?:e|ed)|implement(?:ed)?)\b.{0,80}"
        r"\b(?:ban|bann(?:ed|ing)|prohibit(?:ed|ion)|restriction)\b",
        r"\b(?:already\s+)?banned\b",
        r"\b(?:iniutos|ipinagbawal|ipinatupad)\b.{0,80}\b(?:facebook|meta|platform)\b",
    ),
    "POLICY_CONSIDERATION": (
        r"\b(?:bukas\s+sa\s+posibilidad(?:\s+ng\s+pagbabawal)?|"
        r"maaaring\s+ipagbawal|under\s+study|possible\s+(?:ban|restrictions?))\b",
        r"\b(?:pinag-?aaralan|pag-?aaralan|open\s+to(?:\s+the\s+possibility)?|"
        r"consider(?:s|ed|ing)?|study(?:ing)?)\b.{0,100}"
        r"\b(?:ban|bann(?:ed|ing)|remov(?:e|al|ing)|restrict(?:ion|ions|ed|ing)?)\b",
        r"\b(?:ban|bann(?:ed|ing)|remov(?:e|al|ing)|restrict(?:ion|ions|ed|ing)?)\b"
        r".{0,100}\b(?:pinag-?aaralan|pag-?aaralan|open\s+to|consider(?:s|ed|ing)?|"
        r"study(?:ing)?)\b",
    ),
    "POLICY_PROPOSAL": (
        r"\b(?:propos(?:al|ed)|draft|bill filed|under discussion|"
        r"panukalang\s+pagbabawal|panukala)\b",
    ),
    "NUCLEAR_PREPARATION": (
        r"\b(?:mov(?:e|es|ing) closer|advanc(?:e|es|ed|ing)|prepar(?:e|es|ed|ing|ations?)|"
        r"plan(?:s|ned|ning)?|develop(?:s|ed|ing|ment)?|identif(?:y|ies|ied))\b.{0,80}"
        r"\b(?:nuclear|atomic)\s+(?:energy|power|plant|program|expertise)\b",
        r"\b(?:nuclear|atomic)\s+(?:energy|power|plant|program|expertise)\b.{0,80}"
        r"\b(?:advanc(?:e|es|ed|ing)|prepar(?:e|es|ed|ing|ations?)|plan(?:s|ned|ning)?|"
        r"develop(?:s|ed|ing|ment)?|site(?:s|d)?|rebuild(?:s|ing)?)\b",
    ),
    "RETURN_FROM_CUSTODY": (
        r"\b(?:return(?:s|ed|ing)?\s+(?:home|to\s+the\s+philippines)|coming\s+home|uuwi|"
        r"release(?:d)?\s+from\s+(?:icc\s+)?custody)\b",
    ),
    "INSTITUTION_DISMANTLED": (
        r"\b(?:dismantl(?:e|ed|ing)|madidismantle|abolish(?:ed|ing)?|dissolv(?:e|ed|ing))\b",
    ),
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
    "TRIAL": (
        (
            r"\b(?:no|not|without)\s+"
            r"(?:(?:an?|the|any|current|ongoing|impeachment)\s+){0,2}"
            r"(?:trial|impeachment|hearing|prosecution)\b|"
            r"\b(?:denies?|denied)\s+(?:(?:an?|the|any)\s+){0,2}"
            r"(?:trial|impeachment|hearing|prosecution)\b",
            "trial/impeachment denial",
        ),
        (
            r"\b(?:case\s+dismissed|charges?\s+dropped|acquitt(?:ed|al))\b",
            "case dismissed or acquitted",
        ),
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
    "RETURN_FROM_CUSTODY": (
        (
            r"\b(?:not\s+(?:returning|coming\s+home)|remains?\s+(?:in\s+)?(?:icc\s+)?custody|"
            r"continue(?:s|d)?\s+to\s+be\s+detained|release\s+(?:was\s+)?(?:denied|rejected))\b",
            "continued detention/no return",
        ),
    ),
}

TRANSFORMATIONS: dict[tuple[str, str], str] = {
    (
        "DEATH",
        "HEALTH",
    ): "A hospitalization or health report may have been changed into a death claim.",
    ("ARREST", "LEGAL"): "Questioning or an investigation may have been presented as an arrest.",
    ("ARREST", "TRIAL"): "A trial or hearing may have been presented as an arrest.",
    (
        "CONVICTION",
        "LEGAL",
    ): "An accusation or pending case may have been presented as a conviction.",
    (
        "CONVICTION",
        "TRIAL",
    ): "An ongoing trial may have been presented as a conviction.",
    (
        "POLICY_APPROVED",
        "POLICY_PROPOSAL",
    ): "A proposal or filed bill may have been presented as approved law.",
    (
        "POLICY_APPROVED",
        "POLICY_CONSIDERATION",
    ): "A policy under study may have been presented as already ordered or implemented.",
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
    "pco.gov.ph": "Presidential Communications Office",
    "philstar.com": "Philstar.com",
    "rappler.com": "Rappler",
    "reuters.com": "Reuters",
    "smninewschannel.com": "SMNI News",
    "tribune.net.ph": "Daily Tribune",
    "tsek.ph": "Tsek.ph",
    "verafiles.org": "VERA Files",
}

SOURCE_WEIGHTS: dict[str, float] = {
    "primary_official": 1.00,
    "reuters": 0.95,
    "ap": 0.95,
    "afp": 0.95,
    "major_national_news": 0.85,
    "established_local_news": 0.75,
    "fact_check_org": 0.95,
    "verified_social_account": 0.55,
    "unknown_news_site": 0.30,
    "blog": 0.15,
    "social_post": 0.10,
}

PRIMARY_SOURCE_DOMAINS: dict[str, list[str]] = {
    "official_gov": [
        "officialgazette.gov.ph", "gov.ph", "pco.gov.ph", "dfa.gov.ph",
        "doj.gov.ph", "dilg.gov.ph", "comelec.gov.ph", "dbm.gov.ph",
        "doh.gov.ph", "doe.gov.ph", "senate.gov.ph", "house.gov.ph",
        "pia.gov.ph", "pna.gov.ph", "deped.gov.ph", "ovp.gov.ph",
        "pnp.gov.ph",
    ],
    "international_official": [
        "whitehouse.gov", "state.gov", "un.org", "icc-cpi.int",
    ],
}

WIRE_SERVICES = {"reuters.com", "apnews.com", "afp.com"}

FACT_CHECK_ORGS = {"verafiles.org", "rappler.com", "tsek.ph"}

SYNDICATION_PATTERNS = (
    re.compile(r"\b(?:according to|ayon sa|source:\s*)(?:reuters|associated press|ap|afp|agence france[- ]presse)\b", re.IGNORECASE),
    re.compile(r"\b(?:reuters|associated press|ap|afp)\s+(?:reported|report|says|said)\b", re.IGNORECASE),
    re.compile(r"(?:—|-)\s*(?:Reuters|AP|AFP)\s*$", re.MULTILINE),
    re.compile(r"\((?:Reuters|AP|AFP)\)", re.IGNORECASE),
)

RELATIVE_DATE_PATTERNS: dict[str, int | tuple[int, int]] = {
    "today": 0, "yesterday": -1, "tomorrow": 1,
    "this morning": 0, "tonight": 0, "last night": -1,
    "this week": (0, 6), "last week": (-7, -1), "next week": (7, 13),
    "recently": (-7, 0), "just now": 0, "breaking": 0,
    "kahapon": -1, "kanina": 0, "bukas": 1,
    "ngayong araw": 0, "ngayong linggo": (0, 6),
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
    attributed_entity: str = ""


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
    evidence_text: str = ""


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
    if "POLICY_APPROVED" in detected:
        words = re.findall(r"[\w'-]+", lowered, flags=re.UNICODE)
        approval_words = {
            "approved",
            "banned",
            "implemented",
            "iniutos",
            "ipinagbawal",
            "ipinatupad",
            "ordered",
            "passed",
            "sign",
            "signs",
            "signed",
        }
        nonfinal_words = {
            *NEGATION_WORDS,
            "before",
            "could",
            "if",
            "may",
            "might",
            "should",
            "would",
        }
        affirmed = any(
            word in approval_words
            and not any(marker in nonfinal_words for marker in words[max(0, index - 5) : index])
            for index, word in enumerate(words)
        )
        if not affirmed:
            detected.remove("POLICY_APPROVED")
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
        r"\b(?:in|at|near|across|throughout|outside|inside|around|sa)\s+(?:the\s+)?"
        r"([A-Z][\w.-]*(?:\s+[A-Z][\w.-]*){0,3}"
        r"(?:,\s*[A-Z][\w.-]*(?:\s+[A-Z][\w.-]*){0,2})?)",
        cleaned_text,
    )
    locations = list(
        dict.fromkeys(
            match.strip(" .,:;!?")
            for match in location_matches
            if match.strip().casefold() not in {"facebook", "meta"}
        )
    )
    attribution_match = re.search(
        r"\b(?i:ayon\s+kay|according\s+to|attributed\s+to|said\s+by)\s+"
        r"(?P<name>[A-Z][\w.-]+(?:\s+[A-Z][\w.-]+){0,3})\b",
        cleaned_text,
    )
    attributed_entity = attribution_match.group("name").strip() if attribution_match else ""
    if attributed_entity.casefold() == "castro":
        attributed_entity = "Claire Castro"

    return ClaimFeatures(
        entities=entities[:10],
        keywords=keywords[:30],
        event_categories=detect_event_categories(cleaned_text),
        dates=dates[:10],
        locations=locations[:10],
        tokens=tokens,
        attributed_entity=attributed_entity,
    )


def _policy_semantic_queries(cleaned_text: str, features: ClaimFeatures) -> list[str]:
    """Translate Filipino policy-state wording into compact English discovery queries."""
    policy_states = {"POLICY_CONSIDERATION", "POLICY_PROPOSAL"}
    if not policy_states.intersection(features.event_categories):
        return []

    lowered = cleaned_text.casefold()
    president = "President Marcos" if "marcos" in lowered else ""
    platform = "Facebook" if "facebook" in lowered else "Meta" if "meta" in lowered else ""
    country = "Philippines" if re.search(r"\b(?:pilipinas|philippines)\b", lowered) else ""
    attribution = features.attributed_entity
    if not any((president, platform, attribution)):
        return []

    queries = [
        " ".join(
            part
            for part in (
                president,
                platform,
                "open possible ban",
                attribution.split()[-1] if attribution else "",
            )
            if part
        ),
        " ".join(
            part
            for part in (
                "Marcos" if president else "",
                "considering",
                platform,
                "restrictions",
                country,
                attribution,
            )
            if part
        ),
    ]
    return list(dict.fromkeys(query for query in queries if query.strip()))


def generate_contradiction_queries(cleaned_text: str, features: ClaimFeatures) -> list[str]:
    """Generate queries that specifically search for evidence contradicting the claim."""
    queries: list[str] = []

    def add(query: str) -> None:
        query = " ".join(query.split()).strip()
        if query and query.lower() not in {item.lower() for item in queries}:
            queries.append(query[:300])

    # Negation queries for each event category
    negation_map = {
        "DEATH": ["alive", "not dead", "still alive", "recovering"],
        "ARREST": ["not arrested", "no warrant", "no arrest"],
        "RETURN_FROM_CUSTODY": ["remains detained", "not returning", "remains in custody",
                                "release denied"],
        "POLICY_APPROVED": ["not yet approved", "still under review", "proposal only"],
        "RESIGNATION": ["denies resignation", "remains in office"],
    }
    for category in features.event_categories:
        if category in negation_map:
            for negation in negation_map[category][:2]:
                entity_str = " ".join(features.entities[:2])
                add(f"{entity_str} {negation}")

    # Fact-check queries
    entity_str = " ".join(features.entities[:3])
    if entity_str:
        add(f"{entity_str} fact check")
        add(f"{entity_str} false claim")
        add(f"{entity_str} fake news")

    return queries[:5]


def generate_primary_source_queries(
    cleaned_text: str, features: ClaimFeatures
) -> list[str]:
    """Generate site:-scoped queries targeting authoritative primary sources."""
    queries: list[str] = []
    search_text = normalize_search_text(cleaned_text)
    entity_str = " ".join(features.entities[:2])
    event_terms = [EVENT_KEYWORDS[cat][0] for cat in features.event_categories]

    def add(query: str) -> None:
        query = " ".join(query.split()).strip()
        if query and query.lower() not in {item.lower() for item in queries}:
            queries.append(query[:300])

    lowered = cleaned_text.casefold()

    # Map claim topics to primary source domains
    domain_hints: list[str] = []
    if re.search(r"\b(?:icc|international criminal court)\b", lowered):
        domain_hints.append("icc-cpi.int")
    if re.search(r"\b(?:doh|department of health)\b", lowered):
        domain_hints.append("doh.gov.ph")
    if re.search(r"\b(?:doe|department of energy|nuclear)\b", lowered):
        domain_hints.append("doe.gov.ph")
    if re.search(r"\b(?:comelec|commission on elections|election)\b", lowered):
        domain_hints.append("comelec.gov.ph")
    if re.search(r"\b(?:dfa|department of foreign affairs|passport|visa)\b", lowered):
        domain_hints.append("dfa.gov.ph")
    if re.search(r"\b(?:trump|white\s*house|united states|us president)\b", lowered):
        domain_hints.extend(["whitehouse.gov", "state.gov"])
    if re.search(r"\b(?:united nations|un )\b", lowered):
        domain_hints.append("un.org")
    # Always include PCO and PNA for Philippine political claims
    if features.entities:
        domain_hints.extend(["pco.gov.ph", "pna.gov.ph"])

    for domain in dict.fromkeys(domain_hints):
        search_terms = " ".join([*features.entities[:2], *event_terms[:2]])
        add(f"site:{domain} {search_terms}")

    return queries[:4]


def resolve_relative_dates(text: str, reference_date: datetime) -> dict[str, str]:
    """Convert relative date phrases to absolute date ranges for temporal verification."""
    resolved: dict[str, str] = {}
    lowered = text.casefold()
    for phrase, offset in RELATIVE_DATE_PATTERNS.items():
        if phrase in lowered:
            if isinstance(offset, tuple):
                start = reference_date + timedelta(days=offset[0])
                end = reference_date + timedelta(days=offset[1])
                resolved[phrase] = f"{start.date().isoformat()} to {end.date().isoformat()}"
            else:
                target = reference_date + timedelta(days=offset)
                resolved[phrase] = target.date().isoformat()
    return resolved


def generate_search_queries(cleaned_text: str, features: ClaimFeatures) -> list[str]:
    search_text = normalize_search_text(cleaned_text)
    queries: list[str] = []
    event_terms = [EVENT_KEYWORDS[category][0] for category in features.event_categories]

    def add(query: str) -> None:
        query = " ".join(query.split()).strip()
        if query and query.lower() not in {item.lower() for item in queries}:
            queries.append(query[:300])

    add(search_text)

    # A short verbatim quotation is often the strongest discovery key in a
    # copied news paragraph. Search it before longer derived views so browser
    # artifacts (for example, a stray "Faster" accessibility label) cannot
    # prevent the original report from being found.
    quoted_phrases = re.findall(
        r"(?:[\"\u201c\u201d])([^\"\u201c\u201d]{4,160})(?:[\"\u201c\u201d])",
        cleaned_text,
    )
    for phrase in quoted_phrases[:2]:
        normalized_phrase = normalize_search_text(phrase)
        if len(normalized_phrase.split()) >= 3:
            add(f'"{normalized_phrase}"')

    # Literal Filipino OCR is often a poor match for English newsroom and
    # government headlines. Put the strongest semantic translation in the
    # first provider wave while retaining the original wording as query one.
    semantic_policy_queries = _policy_semantic_queries(cleaned_text, features)
    for query in semantic_policy_queries:
        add(query)

    # A common misinformation pattern keeps a real headline intact and appends
    # a short, inflammatory ending. Search a couple of progressively trimmed
    # headline prefixes early, before the extra words can steer retrieval to a
    # different event. The unquoted full claim remains the first query so
    # ordinary prose and paraphrases still work as expected.
    search_tokens = search_text.split()
    if len(search_tokens) >= 7:
        for trim_count in (2,):
            prefix = search_tokens[:-trim_count]
            if len(prefix) >= 5:
                add(f'"{" ".join(prefix)}"')

    if event_terms:
        add(" ".join([*features.entities[:2], *event_terms[:2]]))
    lowered = cleaned_text.casefold()
    primary_domain = ""
    if "NUCLEAR_PREPARATION" in features.event_categories or re.search(
        r"\b(?:doe|department of energy)\b", lowered
    ):
        primary_domain = "doe.gov.ph"
    elif re.search(r"\b(?:icc|international criminal court)\b", lowered):
        primary_domain = "icc-cpi.int"
    elif re.search(r"\b(?:doh|department of health)\b", lowered):
        primary_domain = "doh.gov.ph"
    elif re.search(r"\b(?:comelec|commission on elections)\b", lowered):
        primary_domain = "comelec.gov.ph"
    if primary_domain:
        add(f"site:{primary_domain} " + " ".join([*features.entities[:2], *event_terms[:2]]))
    # Fact-check pages are often the strongest evidence for viral claims. Keep
    # this view inside the first provider request wave instead of placing it at
    # the end where bounded search limits may never execute it.
    add(" ".join([*features.entities[:3], *event_terms[:2], "fact check"]))
    add(f'"{search_text}"')
    add(" ".join(features.keywords[:10]))
    add(" ".join([*features.entities[:2], *event_terms[:2]]))
    phrase_tokens = search_text.split()[:12]
    if len(phrase_tokens) >= 3:
        add(f'"{" ".join(phrase_tokens)}"')
    if features.event_categories:
        related_terms = EVENT_KEYWORDS[features.event_categories[0]][:3]
        add(" ".join([*features.entities[:2], *related_terms]))
    if features.dates:
        add(" ".join([*features.entities[:2], *event_terms[:2], *features.dates[:1]]))
    return queries[:8]


FACT_CHECK_SECTION_PATHS = {
    "rappler.com": "rappler.com/newsbreak/fact-check",
    "tsek.ph": "tsek.ph",
    "verafiles.org": "verafiles.org/articles",
}


def generate_fact_check_queries(claim_text: str, domains: list[str]) -> list[str]:
    """Build explicit searches for each configured Philippine fact-check archive."""
    search_text = normalize_search_text(claim_text)
    claim_view = " ".join(search_text.split()[:24])
    queries = [f"{claim_view} fact check"] if claim_view else []
    for domain in domains:
        section = FACT_CHECK_SECTION_PATHS.get(domain, domain)
        query = f"site:{section} {claim_view}".strip()
        if query.casefold() not in {item.casefold() for item in queries}:
            queries.append(query)
    return queries[:5]


def generate_quote_source_queries(claim_text: str, features: ClaimFeatures) -> list[str]:
    """Build compact quote-and-speaker searches for publisher archives."""
    speaker = next(
        (
            entity
            for entity in reversed(features.entities)
            if re.search(
                r"\b(?:Atty\.?|Gov\.?|Mayor|President|Sen\.?|Senator|Sec\.?|Secretary|VP)\b",
                entity,
                re.IGNORECASE,
            )
        ),
        features.entities[-1] if features.entities else "",
    )
    search_text = normalize_search_text(claim_text)
    speaker_tokens = set(normalize_search_text(speaker).split())
    quote_tokens = [token for token in search_text.split() if token not in speaker_tokens]
    quote_tokens = [token.replace("'", "") for token in quote_tokens]
    distinctive_tokens = quote_tokens[-11:]
    distinctive_phrase = " ".join(distinctive_tokens)
    queries = []
    # Short fragments survive normal differences between social-card OCR and
    # an article transcript (for example, n'yo versus ninyo).
    if len(distinctive_tokens) >= 6:
        middle = len(distinctive_tokens) // 2
        middle_pair = " ".join(distinctive_tokens[middle : middle + 2])
        ending_pair = " ".join(distinctive_tokens[-2:])
        queries.append(f'"{middle_pair}" "{ending_pair}" "{speaker}"'.strip())
    loose_tokens = [
        token
        for token in quote_tokens
        if token
        not in {
            "ako",
            "ang",
            "ay",
            "di",
            "hindi",
            "lang",
            "may",
            "na",
            "ng",
            "nito",
            "nyo",
            "pag",
            "sa",
            "yung",
        }
    ][-8:]
    if len(loose_tokens) >= 4:
        queries.append(f'{" ".join(loose_tokens)} "{speaker}"'.strip())
    if len(distinctive_tokens) >= 6:
        queries.append(f'{distinctive_phrase} "{speaker}"'.strip())
    if len(distinctive_phrase.split()) >= 4:
        queries.append(f'"{distinctive_phrase}" "{speaker}"'.strip())
    queries.append(f'"{search_text}"')
    return list(dict.fromkeys(query for query in queries if query.strip('" ')))[:3]


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


def _is_evidence_page(result: SearchResult) -> bool:
    """Only allow article-like pages that can substantively support a verdict."""
    if any(
        domain_matches(result.domain, domain)
        for domain in (
            "facebook.com",
            "x.com",
            "twitter.com",
            "reddit.com",
            "threads.com",
            "tiktok.com",
            "instagram.com",
            "youtube.com",
            "youtu.be",
        )
    ):
        return False
    parsed = urlparse(result.url)
    path = parsed.path.casefold().rstrip("/")
    if not path:
        return False
    return not re.match(
        r"^/(?:author|authors|archive|archives|category|categories|hub|page|search|"
        r"tag|tags|topic|topics)(?:/|$)",
        path,
    )


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


def _canonical_quote_tokens(value: str | list[str]) -> list[str]:
    tokens = tokenize(value) if isinstance(value, str) else value
    aliases = {
        "n'yo": "ninyo",
        "nyo": "ninyo",
        "'yung": "yung",
    }
    return [aliases.get(token.lower(), token.lower().lstrip("'")) for token in tokens]


def _longest_common_token_run(left: list[str], right: list[str]) -> int:
    """Return the longest ordered, contiguous token match using bounded memory."""
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    longest = 0
    for left_token in left:
        current = [0] * (len(right) + 1)
        for index, right_token in enumerate(right, start=1):
            if left_token == right_token:
                current[index] = previous[index - 1] + 1
                longest = max(longest, current[index])
        previous = current
    return longest


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

    def canonical(value: str) -> str:
        lowered = value.casefold()
        if lowered == "pilipinas" or lowered.startswith("pilipinas,"):
            return "philippines"
        if lowered == "philippines" or lowered.startswith("philippines,"):
            return "philippines"
        return value

    return not any(
        _fuzzy_ratio(canonical(left_location), canonical(right_location)) >= 0.82
        for left_location in left
        for right_location in right
    )


def _is_near_identical_location_variant(
    *,
    entity_overlap: float,
    keyword_overlap: float,
    headline_similarity: float,
) -> bool:
    """Identify a matching story whose principal changed fact is its location.

    A location conflict normally means two separate events. Exceptionally high
    headline, entity, and keyword agreement indicates a more useful case: a real
    report has likely been copied with its location replaced.
    """
    return entity_overlap >= 0.60 and keyword_overlap >= 0.75 and headline_similarity >= 0.85


def _location_change_explanation(claim: ClaimFeatures, report: ClaimFeatures) -> str:
    claimed_location = ", ".join(claim.locations[:2]) or "a different location"
    # A venue or event name (for example "US Open" after "at the") can look
    # like a location to the conservative extractor. Do not present a proper
    # noun already shared by both stories as the changed geographic fact.
    reported_locations = [
        location
        for location in report.locations
        if not any(
            _fuzzy_ratio(location, entity) >= 0.90
            for entity in claim.entities
            if not any(
                _fuzzy_ratio(entity, claim_location) >= 0.90 for claim_location in claim.locations
            )
        )
    ]
    reported_location = ", ".join(reported_locations[:2]) or "another location"
    return (
        "A closely matching real report names "
        f"{reported_location} as the location, while the submitted claim says "
        f"{claimed_location}. This changes a critical fact of the story."
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
    # Compare like with like. ``search_text`` has already had stopwords and
    # punctuation removed; normalizing candidates avoids suppressing an
    # otherwise near-identical headline.
    title_score = _fuzzy_ratio(search_text, normalize_search_text(result.title))
    snippet_score = _fuzzy_ratio(search_text, normalize_search_text(result.snippet))
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
    quoted_query_phrases = re.findall(r'"([^"\n]{3,160})"', result.query)
    for phrase in quoted_query_phrases:
        phrase_tokens = _canonical_quote_tokens(phrase)
        if len(phrase_tokens) < 3:
            continue
        candidate_tokens = _canonical_quote_tokens(combined)
        if _longest_common_token_run(phrase_tokens, candidate_tokens) == len(phrase_tokens):
            # The provider returned this page for a verbatim phrase and the
            # phrase is actually present in its title/snippet. Keep the result
            # eligible for article inspection even if copied UI noise weakens
            # entity and whole-paragraph similarity scores.
            score = max(score, 55)
            break
    location_variant = _is_near_identical_location_variant(
        entity_overlap=entity_score,
        keyword_overlap=keyword_score,
        headline_similarity=title_score,
    )
    if _locations_conflict(claim.locations, candidate.locations) and not location_variant:
        # A shared subject and event must not make a story from a different
        # place eligible as evidence for the submitted claim. Preserve only
        # near-identical headlines so changed-location misinformation can be
        # shown to the user as related evidence.
        score = min(score, 25)
    policy_agreement, _ = _policy_evidence_agreement(claim, combined, discovery=True)
    if not policy_agreement:
        # Shared names such as Marcos and Facebook are not evidence unless the
        # result also matches the claimed policy action/state and attribution.
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
                    entry.get("src") for entry in collection if isinstance(entry, dict)
                )
        metatags = pagemap.get("metatags")
        if isinstance(metatags, list):
            for metadata in metatags:
                if not isinstance(metadata, dict):
                    continue
                candidates.extend(
                    metadata.get(key) for key in ("og:image", "twitter:image", "twitter:image:src")
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
    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.news_search_timeout_seconds),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self._request_slots = asyncio.Semaphore(
            getattr(settings, "news_max_concurrent_search_requests", 4)
        )

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
        client = self._client
        for provider in self.settings.news_search_provider_list:
            if not self._provider_is_configured(provider):
                continue
            providers_used.append(provider)
            provider_succeeded = False

            async def run_query(
                query_index: int,
                base_query: str,
                provider_name: str = provider,
            ):
                query = self._restrict_query(base_query, restricted_domains)
                try:
                    async with self._request_slots:
                        batch = await self._search_provider(client, provider_name, query)
                    return query_index, batch
                except (SearchProviderError, httpx.HTTPError, ValueError):
                    logger.warning("News search provider %s query failed", provider_name)
                    return query_index, None

            # Run the strongest query views together, then spend quota on the
            # remaining views only if the first bounded wave is insufficient.
            initial_count = min(3, query_limit)
            batches = await asyncio.gather(
                *(run_query(index, query) for index, query in enumerate(queries[:initial_count]))
            )
            for _, batch in batches:
                if batch is None:
                    continue
                any_success = provider_succeeded = True
                collected.extend(batch)
            collected = deduplicate_results(collected)
            useful_results = (
                [item for item in collected if result_filter(item)] if result_filter else collected
            )
            if len(useful_results) < self.settings.news_min_relevant_results:
                extra_batches = await asyncio.gather(
                    *(
                        run_query(index, queries[index])
                        for index in range(initial_count, query_limit)
                    )
                )
                for _, batch in extra_batches:
                    if batch is None:
                        continue
                    any_success = provider_succeeded = True
                    collected.extend(batch)
                collected = deduplicate_results(collected)
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

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

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
    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.news_scrape_timeout_seconds),
            headers={
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
            },
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self._request_slots = asyncio.Semaphore(getattr(settings, "news_max_concurrent_scrapes", 4))

    async def scrape(self, value: str) -> Article | None:
        current_url = normalize_url(value)
        if not current_url:
            return None
        async with self._request_slots:
            for redirect_count in range(self.settings.news_max_redirects + 1):
                await _validate_public_url(current_url)
                try:
                    async with self._client.stream(
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

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

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
    if any(
        domain_matches(domain, item) for item in getattr(settings, "fact_check_domain_list", [])
    ):
        return 1
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


def _publisher_identity(result: SearchResult, article: Article | None, settings: Settings) -> str:
    configured_domains = {
        *settings.philippine_news_domain_list,
        *settings.trusted_news_domain_list,
        *settings.news_tier_2_domain_list,
        *PUBLISHER_NAMES,
    }
    matches = [domain for domain in configured_domains if domain_matches(result.domain, domain)]
    if matches:
        return max(matches, key=len)
    publisher = _publisher_name(result, article)
    normalized_publisher = normalize_search_text(publisher)
    return normalized_publisher or result.domain.removeprefix("www.")


def _detect_syndication_source(article: Article | None, snippet: str) -> str | None:
    """Detect if this article is derived from a wire service or another outlet."""
    text = (article.article_text[:3000] if article else snippet).casefold()
    for pattern in SYNDICATION_PATTERNS:
        match = pattern.search(text if article else snippet)
        if match:
            matched = match.group(0).casefold()
            if "reuters" in matched:
                return "reuters.com"
            if "associated press" in matched or "(ap)" in matched or "— ap" in matched:
                return "apnews.com"
            if "afp" in matched or "agence france" in matched:
                return "afp.com"
    return None


def _source_quality_weight(domain: str, settings: Settings) -> float:
    """Return a quality weight for a domain based on source registries."""
    # Primary official sources
    for group_domains in PRIMARY_SOURCE_DOMAINS.values():
        if any(domain_matches(domain, d) for d in group_domains):
            return SOURCE_WEIGHTS["primary_official"]
    # Wire services
    if any(domain_matches(domain, ws) for ws in WIRE_SERVICES):
        wire = next(ws for ws in WIRE_SERVICES if domain_matches(domain, ws))
        return SOURCE_WEIGHTS.get(wire.split(".")[0], 0.95)
    # Fact-check organizations
    if any(domain_matches(domain, fc) for fc in FACT_CHECK_ORGS):
        return SOURCE_WEIGHTS["fact_check_org"]
    # Trusted national news
    if any(domain_matches(domain, d) for d in settings.trusted_news_domain_list):
        return SOURCE_WEIGHTS["major_national_news"]
    # Tier 2 news
    if any(domain_matches(domain, d) for d in settings.news_tier_2_domain_list):
        return SOURCE_WEIGHTS["established_local_news"]
    # Social media
    if any(name in domain for name in ("facebook.com", "tiktok.com", "x.com", "twitter.com")):
        return SOURCE_WEIGHTS["social_post"]
    # Unknown
    return SOURCE_WEIGHTS["unknown_news_site"]


def _is_fact_check_source(domain: str) -> bool:
    """Return True if the domain is a known fact-checking organization."""
    return any(domain_matches(domain, fc) for fc in FACT_CHECK_ORGS)


def _likely_shared_reporting(left: EvidenceAnalysis, right: EvidenceAnalysis) -> bool:
    """Detect if two evidence items share the same underlying reporting.

    Checks headline/body similarity AND syndication chain attribution.
    """
    left_title = (
        left.article.headline if left.article and left.article.headline else left.result.title
    )
    right_title = (
        right.article.headline if right.article and right.article.headline else right.result.title
    )
    if (
        min(len(left_title), len(right_title)) >= 20
        and _fuzzy_ratio(left_title, right_title) >= 0.92
    ):
        return True
    left_body = left.article.article_text[:1200] if left.article else left.evidence_text
    right_body = right.article.article_text[:1200] if right.article else right.evidence_text
    if (
        min(len(left_body), len(right_body)) >= 200
        and _fuzzy_ratio(left_body, right_body) >= 0.90
    ):
        return True
    # Check if both derive from the same wire service
    left_source = _detect_syndication_source(left.article, left.result.snippet)
    right_source = _detect_syndication_source(right.article, right.result.snippet)
    if left_source and right_source and left_source == right_source:
        # Both cite the same wire service AND neither IS the wire service
        left_is_wire = any(domain_matches(left.result.domain, ws) for ws in WIRE_SERVICES)
        right_is_wire = any(domain_matches(right.result.domain, ws) for ws in WIRE_SERVICES)
        if not left_is_wire and not right_is_wire:
            return True
    return False


def _independent_representatives(
    items: list[EvidenceAnalysis], settings: Settings
) -> list[EvidenceAnalysis]:
    """Select independently-sourced evidence, collapsing syndication chains.

    If multiple outlets all derive from the same wire service, only the
    highest-scoring representative (preferably the wire service itself)
    counts as independent evidence.
    """
    representatives: list[EvidenceAnalysis] = []
    syndication_groups: dict[str, EvidenceAnalysis] = {}  # wire_source -> best representative

    for item in sorted(items, key=lambda candidate: candidate.evidence_score, reverse=True):
        identity = _publisher_identity(item.result, item.article, settings)
        # Check if this item derives from a wire service
        wire_source = _detect_syndication_source(item.article, item.result.snippet)
        is_wire = any(domain_matches(item.result.domain, ws) for ws in WIRE_SERVICES)

        # If this IS the wire service, it's the primary representative
        if is_wire:
            if item.result.domain not in syndication_groups:
                syndication_groups[item.result.domain] = item
            continue

        # If it cites a wire service, group it
        if wire_source:
            if wire_source not in syndication_groups:
                syndication_groups[wire_source] = item
            continue

        # Otherwise check normal identity and shared-reporting dedup
        if any(
            identity == _publisher_identity(existing.result, existing.article, settings)
            or _likely_shared_reporting(item, existing)
            for existing in representatives
        ):
            continue
        representatives.append(item)

    # Add one representative per syndication group
    for wire, best_item in syndication_groups.items():
        if not any(
            _publisher_identity(best_item.result, best_item.article, settings)
            == _publisher_identity(existing.result, existing.article, settings)
            for existing in representatives
        ):
            representatives.append(best_item)

    return sorted(representatives, key=lambda item: item.evidence_score, reverse=True)



def _recency_score(date_value: str | None, now: datetime) -> int:
    published = _parse_published_date(date_value, now)
    if published is None:
        # Unknown dates must not receive a neutral freshness assumption.
        return 35
    age_days = max(0, (now - published).days)
    if age_days <= 7:
        return 100
    if age_days <= 30:
        return 85
    if age_days <= 365:
        return 65
    return 35


def _negates_category(document: str, category: str) -> bool:
    if category == "TRIAL":
        # A loose four-word window is unsafe for trial coverage: ordinary
        # sentences such as "without sacrificing the prosecution's effort" or
        # "not the merits, but the prosecution" do not deny that a trial is
        # taking place. Only accept a direct grammatical negation here.
        return bool(
            re.search(
                r"\b(?:no|not|without)\s+"
                r"(?:(?:an?|the|any|current|ongoing|impeachment)\s+){0,2}"
                r"(?:trial|impeachment|hearing|prosecution)\b",
                document,
                flags=re.IGNORECASE,
            )
            or re.search(
                r"\b(?:denies?|denied)\s+(?:(?:an?|the|any)\s+){0,2}"
                r"(?:trial|impeachment|hearing|prosecution)\b",
                document,
                flags=re.IGNORECASE,
            )
        )
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


PERSON_TITLE_TOKENS = {
    "atty",
    "attorney",
    "gov",
    "governor",
    "mayor",
    "president",
    "sec",
    "secretary",
    "sen",
    "senator",
    "sir",
    "vice",
    "vp",
}


def _death_subject_aliases(claim: ClaimFeatures) -> list[str]:
    """Return full named subjects that a death predicate must describe.

    General entity overlap intentionally tolerates partial name matches for
    discovery. That is unsafe for death claims: Sara Duterte and Rodrigo
    Duterte are different subjects even though they share a surname.
    """
    aliases: list[str] = []
    for entity in claim.entities:
        parts = tokenize(entity)
        while parts and parts[0] in PERSON_TITLE_TOKENS:
            parts.pop(0)
        if len(parts) < 2:
            continue
        alias = " ".join(parts)
        if alias not in aliases:
            aliases.append(alias)
    return aliases


def _death_subject_status(claim: ClaimFeatures, document: str) -> str | None:
    """Identify a literal death assertion or denial about the claimed person.

    This deliberately uses close grammatical patterns instead of checking
    whether a person's name and a word such as ``dead`` occur somewhere in the
    same article. It therefore rejects phrases such as "Sara Duterte's
    impeachment is dead" and reports about somebody else's death.
    """
    aliases = _death_subject_aliases(claim)
    if "DEATH" not in claim.event_categories or not aliases:
        return None

    title = r"(?:vice\s+president|vp|president|senator|sen\.?|mayor|governor|gov\.?)"
    for alias in aliases:
        name = r"\s+".join(re.escape(part) for part in alias.split())
        subject = rf"(?:{title}\s+)?{name}"
        denied_patterns = (
            rf"\b{subject}\s+(?:is|was|remains?|reportedly\s+is)\s+"
            rf"(?:still\s+)?(?:alive|not\s+dead)\b",
            rf"\b{subject}\s+(?:did|does|has|had)\s+not\s+"
            rf"(?:die|died|pass(?:ed)?\s+away)\b",
            rf"\b(?:false|fake|untrue|denied|denies|debunked)\b[^.!?\n]{{0,80}}"
            rf"\b{subject}\b[^.!?\n]{{0,35}}\b(?:dead|died|death)\b",
            rf"\b{subject}\b[^.!?\n]{{0,35}}\b(?:death|dead|died)\b"
            rf"[^.!?\n]{{0,80}}\b(?:false|fake|untrue|denied|debunked)\b",
            rf"\b(?:no|not)\s+(?:reported|confirmed|verified)?\s*"
            rf"(?:death\s+of|report\s+that)\s+(?:{title}\s+)?{name}\b",
        )
        if any(re.search(pattern, document, re.IGNORECASE) for pattern in denied_patterns):
            return "DENIED"

        affirmed_patterns = (
            rf"\b{subject}\s+(?:(?:has|had|is|was)\s+)?"
            rf"(?:reportedly\s+|allegedly\s+)?(?:died|dies|dead|passed\s+away)\b",
            rf"\b{subject}\s+(?:was|is|has\s+been)\s+(?:reportedly\s+)?killed\b",
            rf"\b(?:death|killing)\s+of\s+{subject}\b",
            rf"\b(?:namatay|pumanaw)\s+(?:na\s+)?(?:si\s+)?{subject}\b",
            rf"\bpatay\s+na\s+(?:si\s+)?{subject}\b",
        )
        if any(re.search(pattern, document, re.IGNORECASE) for pattern in affirmed_patterns):
            return "AFFIRMED"
    return None


def _attributed_speaker(features: ClaimFeatures) -> str:
    return next(
        (
            entity
            for entity in features.entities
            if re.match(
                r"^(?:Sir|Atty\.?|Gov\.?|Mayor|President|Sen\.?|Senator|Sec\.?|"
                r"Secretary|VP)\s+",
                entity,
                re.IGNORECASE,
            )
        ),
        "",
    )


def _speaker_appears_in_document(speaker: str, document: str) -> bool:
    if not speaker:
        return True
    titles = {
        "atty",
        "gov",
        "mayor",
        "president",
        "sec",
        "secretary",
        "sen",
        "senator",
        "sir",
        "vp",
    }
    speaker_tokens = [token for token in tokenize(speaker) if token not in titles]
    document_tokens = tokenize(document[:30_000])
    return bool(speaker_tokens) and (
        _longest_common_token_run(speaker_tokens, document_tokens) == len(speaker_tokens)
    )


POLICY_EVENT_STATES = {
    "POLICY_CONSIDERATION",
    "POLICY_PROPOSAL",
    "POLICY_APPROVED",
}
POLICY_ACTION_PATTERN = re.compile(
    r"\b(?:ban|bans|banned|banning|pagbabawal|ipagbawal|ipinagbawal|"
    r"restrict|restriction|restrictions|restricted|remove|removal|matanggal)\b",
    re.IGNORECASE,
)


def _policy_evidence_agreement(
    claim: ClaimFeatures,
    document: str,
    *,
    discovery: bool = False,
) -> tuple[bool, list[str]]:
    """Require the policy subject, action, state, and attribution to agree."""
    if not POLICY_EVENT_STATES.intersection(claim.event_categories):
        return True, []

    claim_text = " ".join(claim.tokens).casefold()
    if not POLICY_ACTION_PATTERN.search(claim_text):
        return True, []
    document_text = document[:30_000].casefold()
    document_features = extract_claim_features(clean_claim_text(document[:30_000]))
    missing: list[str] = []

    if "marcos" in claim_text and not re.search(
        r"\b(?:marcos|president|pangulo|palace|malaca.ang)\b", document_text
    ):
        missing.append("President Marcos")
    if "facebook" in claim_text and not re.search(r"\b(?:facebook|meta)\b", document_text):
        missing.append("Facebook")
    if (
        not discovery
        and re.search(r"\b(?:pilipinas|philippines)\b", claim_text)
        and not re.search(
            r"\b(?:pilipinas|philippines|philippine|filipino|palace|malaca.ang)\b",
            document_text,
        )
    ):
        missing.append("Philippines")
    if claim.attributed_entity and not discovery:
        attribution_tokens = tokenize(claim.attributed_entity)
        surname_matches = bool(
            attribution_tokens
            and re.search(rf"\b{re.escape(attribution_tokens[-1])}\b", document_text)
        )
        if not surname_matches:
            missing.append(f"attribution to {claim.attributed_entity}")
    if POLICY_ACTION_PATTERN.search(claim_text) and not POLICY_ACTION_PATTERN.search(document_text):
        missing.append("policy action")
    if not POLICY_EVENT_STATES.intersection(document_features.event_categories):
        missing.append("policy state")
    return not missing, missing


def _policy_state_relationship(
    claim: ClaimFeatures,
    document: str,
) -> tuple[Relationship, list[str], str | None] | None:
    claim_states = POLICY_EVENT_STATES.intersection(claim.event_categories)
    if not claim_states:
        return None
    if not POLICY_ACTION_PATTERN.search(" ".join(claim.tokens)):
        return None
    agrees, missing = _policy_evidence_agreement(claim, document)
    if not agrees:
        return (
            "IRRELEVANT",
            ["The report does not agree on " + ", ".join(missing) + "."],
            None,
        )

    document_states = POLICY_EVENT_STATES.intersection(
        extract_claim_features(clean_claim_text(document[:30_000])).event_categories
    )
    opening_states = POLICY_EVENT_STATES.intersection(
        extract_claim_features(clean_claim_text(document[:600])).event_categories
    )
    if "POLICY_CONSIDERATION" in claim_states:
        if "POLICY_APPROVED" in opening_states:
            transformation = (
                "An ordered or implemented ban is a different policy state from being open "
                "to studying a possible ban."
            )
            return "RELATED", [transformation], transformation
        if "POLICY_CONSIDERATION" in document_states:
            return (
                "SUPPORTS",
                [
                    "The source matches the entities and attribution and describes only policy "
                    "consideration, not an ordered or implemented ban."
                ],
                None,
            )
        transformation = (
            "A proposal is related but is not the same as the government's stated openness "
            "to studying it."
        )
        return "RELATED", [transformation], transformation

    if "POLICY_APPROVED" in claim_states:
        if "POLICY_APPROVED" in document_states:
            return "SUPPORTS", ["The source reports the same approved policy action."], None
        transformation = (
            "A proposal or policy under study is not an order, approval, or implementation."
        )
        return "RELATED", [transformation], transformation

    if "POLICY_PROPOSAL" in claim_states:
        if "POLICY_PROPOSAL" in document_states:
            return "SUPPORTS", ["The source reports the same policy proposal."], None
        transformation = "The source describes a different stage of the policy process."
        return "RELATED", [transformation], transformation
    return None


def _relationship(
    claim: ClaimFeatures,
    document: str,
    similarity: int,
    *,
    support_scopes: list[str] | None = None,
) -> tuple[Relationship, list[str], str | None]:
    lowered = document.lower()
    document_features = extract_claim_features(clean_claim_text(document[:30_000]))
    opening_features = extract_claim_features(clean_claim_text(document[:2_000]))
    entity_overlap = _entity_overlap(claim.entities, document_features.entities)
    keyword_overlap = _set_overlap(claim.keywords, document_features.keywords)
    location_conflict = _locations_conflict(claim.locations, opening_features.locations)
    if location_conflict:
        if _is_near_identical_location_variant(
            entity_overlap=entity_overlap,
            keyword_overlap=keyword_overlap,
            headline_similarity=_fuzzy_ratio(
                " ".join(claim.keywords),
                " ".join(opening_features.keywords),
            ),
        ):
            transformation = _location_change_explanation(claim, opening_features)
            return "RELATED", [transformation], transformation
        return "IRRELEVANT", ["The report names a different location."], None
    relevant_context = entity_overlap > 0 or keyword_overlap >= 0.2 or similarity >= 45
    rule_matches: list[str] = []
    attributed_speaker = _attributed_speaker(claim)
    speaker_present = _speaker_appears_in_document(attributed_speaker, document)
    death_subjects = _death_subject_aliases(claim)
    death_statuses = (
        [
            _death_subject_status(claim, scope)
            for scope in (support_scopes or [document[:2_000]])
            if scope.strip()
        ]
        if death_subjects
        else []
    )
    death_status = (
        "DENIED"
        if "DENIED" in death_statuses
        else "AFFIRMED"
        if "AFFIRMED" in death_statuses
        else None
    )

    policy_relationship = _policy_state_relationship(claim, document)
    if policy_relationship is not None:
        return policy_relationship

    # Quote cards often abbreviate spoken Filipino (n'yo) while publishers use
    # the expanded transcript spelling (ninyo). A long matching passage in the
    # article body, together with the same attributed speaker, is direct
    # support even when the story headline describes the wider interview.
    quote_run = _longest_common_token_run(
        _canonical_quote_tokens(claim.tokens),
        _canonical_quote_tokens(document[:30_000]),
    )
    attribution_cue = bool(
        re.search(
            r"\b(?:according to|ayon kay|said|says|shared|stated|told|wrote)\b",
            document[:30_000],
            flags=re.IGNORECASE,
        )
    )
    if entity_overlap > 0 and quote_run >= 6 and speaker_present and attribution_cue:
        rule_matches.append(
            f"The article contains a matching attributed quote ({quote_run} words)."
        )
        return "SUPPORTS", rule_matches, None

    nuclear_preparation_match = (
        "NUCLEAR_PREPARATION" in claim.event_categories
        and "NUCLEAR_PREPARATION" in document_features.event_categories
        and relevant_context
        and similarity >= 35
        and keyword_overlap >= 0.25
    )
    if nuclear_preparation_match and not _negates_category(document, "NUCLEAR_PREPARATION"):
        rule_matches.append(
            "The source describes advancing Philippine nuclear-energy preparations."
        )
        return "SUPPORTS", rule_matches, None

    # Article extractors can retain unrelated-story links near the footer. Limit
    # debunk rules to the headline, snippet, and opening article context.
    debunk_scope = lowered[:2000]
    strong_debunk_match = similarity >= 55
    explicit_fact_check = bool(
        re.match(r"\s*(?:fact[ -]?check|debunk(?:ed)?|false claim)\b", debunk_scope)
    )
    if (
        relevant_context
        and strong_debunk_match
        and explicit_fact_check
        and any(phrase in debunk_scope for phrase in DEBUNK_PHRASES)
        and (
            "DEATH" not in claim.event_categories or not death_subjects or death_status == "DENIED"
        )
    ):
        rule_matches.append("Explicit fact-check or debunk language matched the claim context.")
        return "DEBUNKS", rule_matches, None

    for category in claim.event_categories:
        if category == "DEATH" and death_subjects:
            if death_status == "DENIED" and relevant_context:
                rule_matches.append("DEATH: the named person is reported alive")
                return "CONTRADICTS", rule_matches, None
            # Do not let a negated death involving another person, or a
            # metaphor such as "the impeachment is dead," decide this claim.
            continue
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

    if attributed_speaker and not speaker_present and relevant_context:
        rule_matches.append(
            f"The source does not mention the attributed speaker, {attributed_speaker}."
        )
        return "RELATED", rule_matches, None

    claim_events = set(claim.event_categories)

    # Search snippets sometimes describe a related link rather than the result
    # page, while the article body can mention another person's illness. Do not
    # combine those disconnected facts into support for one compound claim.
    # Each source scope must independently contain the claimed entities and
    # events.
    scopes = support_scopes or [document[:2_000]]

    def scope_agrees(scope: str) -> bool:
        scope_features = extract_claim_features(clean_claim_text(scope[:2_000]))
        scope_entity_overlap = _entity_overlap(claim.entities, scope_features.entities)
        entity_agreement = not claim.entities or scope_entity_overlap >= (
            0.7 if len(claim.entities) >= 2 else 0.5
        )
        event_agreement = claim_events.issubset(scope_features.event_categories)
        if "DEATH" in claim_events and death_subjects:
            event_agreement = event_agreement and _death_subject_status(claim, scope) == "AFFIRMED"
        return entity_agreement and event_agreement

    support_facts_align = any(scope_agrees(scope) for scope in scopes if scope.strip())
    same_event = bool(claim_events & set(document_features.event_categories))
    if relevant_context and support_facts_align and (
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
    location_variant = _is_near_identical_location_variant(
        entity_overlap=entity / 100,
        keyword_overlap=keyword / 100,
        headline_similarity=fuzzy / 100,
    )
    if location == 0 and not location_variant:
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
        if rule_matches:
            return rule_matches[0]
        return "This report directly matches the claim's entities and reported event."
    if relationship == "RELATED":
        return "This report covers a closely related event but does not confirm the exact claim."
    return "The result is not sufficiently related to the claim."


def _extract_evidence_text(claim: ClaimFeatures, document: str) -> str:
    """Select a relevant source passage without generating or paraphrasing it."""
    sentences = [
        " ".join(sentence.split())
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", document)
        if len(sentence.split()) >= 5
    ]
    if not sentences:
        return " ".join(document.split())[:500]

    def relevance(sentence: str) -> tuple[float, float]:
        sentence_features = extract_claim_features(sentence)
        return (
            _set_overlap(claim.keywords, sentence_features.keywords),
            _entity_overlap(claim.entities, sentence_features.entities),
        )

    selected = max(sentences, key=relevance)
    return selected[:497] + "..." if len(selected) > 500 else selected


def _claim_context_warnings(features: ClaimFeatures) -> list[str]:
    warnings: list[str] = []
    if "POLICY_CONSIDERATION" in features.event_categories:
        claim_text = " ".join(features.tokens).casefold()
        if "facebook" in claim_text and "marcos" in claim_text:
            warnings.append(
                "The government was only open to studying the possibility; no ban was ordered."
            )
        else:
            warnings.append(
                "The reported action was only under consideration; it was not approved, ordered, "
                "or implemented."
            )
    # Warn when the input is very short (headline-only) so the user knows the
    # verification has limited context to work with.
    word_count = len(features.tokens)
    if word_count <= 15 and not warnings:
        warnings.append(
            "This input looks like a short headline. For more accurate verification, "
            "try including more text from the article."
        )
    return warnings


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
    score = round(prefix_similarity * 45 + headline_coverage * 35 + claim_coverage * 20)

    # Only call this a mutation when a substantial real headline matches the
    # beginning of the submitted text and meaningful words were added. This is
    # intentionally stricter than general fuzzy similarity.
    visibly_truncated = headline.rstrip().endswith(("...", "…"))
    if (
        not visibly_truncated
        and len(headline_terms) >= 5
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
                f"“{added_words}.” The linked report does not confirm that added wording.",
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

    async def aclose(self) -> None:
        for service in (self.search_client, self.scraper):
            close = getattr(service, "aclose", None)
            if close is not None:
                await close()

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
        fact_check_domains = getattr(self.settings, "fact_check_domain_list", [])
        quote_source_domains = getattr(self.settings, "quote_source_domain_list", [])
        fact_check_queries = generate_fact_check_queries(cleaned, fact_check_domains)
        quote_like = bool(
            re.search(r"(?:^|\W)(?:ako|akin|ko|kami|namin|i|me|my|we|our)(?:\W|$)", cleaned, re.I)
            or re.search(r"^[\"'‘’“”]", cleaned)
        )
        quote_queries = (
            generate_quote_source_queries(cleaned, features)
            if quote_like and quote_source_domains
            else []
        )
        policy_source_domains = [
            domain
            for domain in ("pco.gov.ph", "gmanetwork.com", "inquirer.net")
            if domain in outlet_domains
        ]
        policy_discovery = bool(
            POLICY_EVENT_STATES.intersection(features.event_categories)
            and POLICY_ACTION_PATTERN.search(cleaned)
            and policy_source_domains
        )
        # Generate contradiction and primary-source queries
        contradiction_queries = generate_contradiction_queries(cleaned, features)
        primary_source_queries = generate_primary_source_queries(cleaned, features)
        reported_queries = list(dict.fromkeys(
            [*queries, *fact_check_queries, *quote_queries,
             *contradiction_queries, *primary_source_queries]
        ))
        search_specs: list[tuple[str, list[str], list[str]]] = []
        if fact_check_domains:
            search_specs.append(("fact_check", fact_check_queries, fact_check_domains))
        if quote_queries:
            search_specs.extend(
                ("quote", quote_queries, [domain]) for domain in quote_source_domains
            )
        if policy_discovery:
            search_specs.append(("policy", queries, policy_source_domains))
        # Contradiction search: use unrestricted domains for maximum coverage
        if contradiction_queries:
            search_specs.append(("contradiction", contradiction_queries, outlet_domains))
        # Primary source search: unrestricted to reach .gov and international orgs
        if primary_source_queries:
            search_specs.append(("primary", primary_source_queries, []))
        search_specs.append(("outlets", queries, outlet_domains))
        outcomes = await asyncio.gather(
            *(
                self.search_client.search(
                    spec_queries,
                    restricted_domains=domains,
                    result_filter=relevance_filter,
                )
                for _, spec_queries, domains in search_specs
            )
        )
        results = deduplicate_results(
            [
                result
                for outcome in outcomes
                for result in outcome.results
                if any(
                    domain_matches(result.domain, domain)
                    for domain in [
                        *fact_check_domains,
                        *quote_source_domains,
                        *outlet_domains,
                    ]
                )
            ]
        )
        providers_used = list(
            dict.fromkeys(provider for outcome in outcomes for provider in outcome.providers_used)
        )
        any_provider_succeeded = any(outcome.any_provider_succeeded for outcome in outcomes)

        initial_relevant_count = sum(
            1
            for result in results
            if score_initial_relevance(features, search_text, result)
            >= self.settings.news_relevance_threshold
        )
        if (
            self.settings.news_unrestricted_fallback
            and initial_relevant_count < self.settings.news_min_relevant_results
        ):
            fallback_outcome = await self.search_client.search(
                queries,
                restricted_domains=None,
                result_filter=relevance_filter,
            )
            results = deduplicate_results([*results, *fallback_outcome.results])
            providers_used = list(
                dict.fromkeys([*providers_used, *fallback_outcome.providers_used])
            )
            any_provider_succeeded = (
                any_provider_succeeded or fallback_outcome.any_provider_succeeded
            )

        results = [result for result in results if _is_evidence_page(result)]

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
                queries=reported_queries,
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
            headline_candidates = [result.title]
            if article and article.headline:
                headline_candidates.append(article.headline)
            support_scopes = [f"{headline_candidates[0]} {result.snippet}"]
            if article:
                support_scopes.append(f"{article.headline} {article.article_text[:2_000]}")
            relationship, rules, transformation = _relationship(
                features,
                document,
                similarity,
                support_scopes=support_scopes,
            )
            headline_matches = [
                _headline_match_and_mutation(cleaned, headline) for headline in headline_candidates
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
                    evidence_text=_extract_evidence_text(
                        features,
                        article.article_text if article else result.snippet,
                    ),
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
            queries=reported_queries,
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
        # Check for satire/parody content early.
        if "SATIRE" in features.event_categories:
            return (
                "SATIRE",
                85,
                "This content appears to be satire or parody. It is not intended as literal "
                "factual reporting.",
            )

        credible = [item for item in analyses if item.source_tier <= 2]
        supports = [item for item in credible if item.relationship == "SUPPORTS"]
        contradicts = [item for item in credible if item.relationship == "CONTRADICTS"]
        debunks = [item for item in credible if item.relationship == "DEBUNKS"]
        transformations = [item for item in credible if item.transformation]
        independent_supporters = _independent_representatives(supports, self.settings)
        independent_contradictions = _independent_representatives(
            [*contradicts, *debunks], self.settings
        )

        # --- Temporal verification ---
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
        recent_support = [
            item
            for item in supports
            if item not in old_matches
            and (
                not has_relative_date
                or _parse_published_date(
                    (item.article.published_date if item.article else None)
                    or item.result.published_date,
                    now,
                )
                is not None
            )
        ]
        if has_relative_date:
            supports = recent_support
            independent_supporters = _independent_representatives(supports, self.settings)

        # --- Identify fact-check debunks (highest authority) ---
        fact_check_debunks = [
            item for item in debunks
            if _is_fact_check_source(item.result.domain)
        ]

        # --- Identify primary-source contradictions ---
        primary_contradictions = [
            item for item in [*contradicts, *debunks]
            if any(
                domain_matches(item.result.domain, d)
                for group in PRIMARY_SOURCE_DOMAINS.values()
                for d in group
            )
        ]

        # === VERDICT DECISION TREE ===

        # 1. Fact-check debunks ALWAYS take priority.
        #    If a recognized fact-check org (VERA Files, Rappler, Tsek.ph) explicitly
        #    labels this claim as false, that verdict stands regardless of how many
        #    other sites repeat the viral claim. Those "supporting" sites are typically
        #    just syndicated copies or the original viral content itself.
        if fact_check_debunks:
            confidence = min(99, 90 + len(fact_check_debunks) * 3)
            publishers = self._publisher_summary(fact_check_debunks)
            return (
                "FALSE",
                confidence,
                f"Credible fact-checking from {publishers} explicitly labels this claim "
                "as false or misleading.",
            )

        # 2. All debunks (even non-fact-check-org) take priority over support.
        if debunks:
            truly_independent_support = [
                item for item in independent_supporters
                if not _is_fact_check_source(item.result.domain)
                and item.source_tier <= 2
                and _source_quality_weight(item.result.domain, self.settings) >= 0.75
            ]
            if len(truly_independent_support) >= 3:
                return (
                    "UNVERIFIED",
                    65,
                    (
                        "Credible sources conflict about the claim. Fact-check organizations "
                        "dispute it, but multiple independent credible outlets report it. "
                        "The available evidence does not support a definitive verdict yet."
                    ),
                )
            confidence = min(99, 88 + len(independent_contradictions) * 4)
            publishers = self._publisher_summary(debunks)
            return (
                "FALSE",
                confidence,
                f"Credible fact-checking from {publishers} explicitly rejects this claim.",
            )

        # 3. Primary-source contradictions have disproportionate weight.
        if primary_contradictions:
            publishers = self._publisher_summary(primary_contradictions)
            return (
                "FALSE",
                min(98, 88 + len(primary_contradictions) * 4),
                (
                    f"Official primary sources from {publishers} directly contradict "
                    "the claim's central facts."
                ),
            )

        # 4. Multiple independent credible contradictions.
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

        # 5. Outdated content presented as current.
        if old_matches and not recent_support:
            return (
                "MISLEADING",
                min(94, 72 + max(item.evidence_score for item in old_matches) // 5),
                (
                    "A related real story was found, but its publication date does not "
                    "match the claim's current framing. The information may have been "
                    "true at the time but is being presented as current news."
                ),
            )

        # 6. Transformations (real event, changed context).
        if transformations and not supports:
            closest = transformations[0]
            return (
                "MISLEADING",
                min(94, 65 + closest.evidence_score // 4),
                closest.transformation
                or "A related real event appears to have been presented with changed context.",
            )

        # 7. Single credible contradiction.
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

        # 8. Strong support: multiple independent credible sources.
        if len(independent_supporters) >= 2:
            has_primary = any(
                any(
                    domain_matches(item.result.domain, d)
                    for group in PRIMARY_SOURCE_DOMAINS.values()
                    for d in group
                )
                for item in independent_supporters
            )
            base_confidence = 80 + len(independent_supporters) * 4
            if has_primary:
                base_confidence += 5
            publishers = self._publisher_summary(supports)
            return (
                "VERIFIED",
                min(98, base_confidence),
                (
                    f"Multiple independent credible reports from {publishers} support "
                    "the claim's central event and entities."
                ),
            )

        # 9. Limited support: single credible source.
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

        # 10. Related but not directly supporting.
        related = [item for item in credible if item.relationship == "RELATED"]
        if related:
            return (
                "UNVERIFIED",
                min(60, 30 + related[0].evidence_score // 5),
                (
                    "Reliable sources report related stories, but none directly support or "
                    "contradict the exact claim. It remains unverified."
                ),
            )

        # 11. Some results found but none credible enough.
        if analyses:
            return (
                "UNVERIFIED",
                min(55, 25 + analyses[0].evidence_score // 4),
                (
                    "We found related coverage, but not enough direct evidence from "
                    "credible sources to confirm or refute the exact claim."
                ),
            )

        # 12. No results at all.
        return (
            "UNVERIFIED",
            30,
            (
                "No matching coverage was found from credible sources. "
                "That does not mean the claim is false; it may simply "
                "not have been reported yet."
            ),
        )

    def _publisher_summary(self, items: list[EvidenceAnalysis]) -> str:
        names = [
            _publisher_name(item.result, item.article)
            for item in _independent_representatives(items, self.settings)
        ]
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
            "evidence_text": analysis.evidence_text,
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
        displayed: dict[str, list[EvidenceAnalysis]] = {}
        for relationship in group_names:
            displayed[relationship] = _independent_representatives(
                [item for item in analyses if item.relationship == relationship],
                self.settings,
            )
        remaining = getattr(self.settings, "news_max_evidence_items", 8)
        evidence_order = (
            ("DEBUNKS", "CONTRADICTS")
            if verdict in {"FALSE", "LIKELY_FALSE"}
            else ("DEBUNKS", "CONTRADICTS", "SUPPORTS", "RELATED")
        )
        for relationship in evidence_order:
            group = group_names[relationship]
            group_limit = remaining
            if relationship == "RELATED":
                group_limit = min(
                    group_limit,
                    getattr(self.settings, "news_max_related_evidence", 3),
                )
            selected = displayed[relationship][:group_limit]
            groups[group].extend(self._evidence_item(item) for item in selected)
            remaining -= len(selected)
            if remaining <= 0:
                break

        closest_relationships = (
            {"CONTRADICTS", "DEBUNKS"}
            if verdict in {"FALSE", "LIKELY_FALSE"}
            else {"RELATED", "CONTRADICTS", "DEBUNKS"}
        )
        closest_candidates = [
            item for item in analyses if item.relationship in closest_relationships
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
            "context_warnings": _claim_context_warnings(features),
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
