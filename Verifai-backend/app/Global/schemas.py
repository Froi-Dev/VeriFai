import re
import unicodedata
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.Global.security import password_policy_errors

NAME_PATTERN = re.compile(r"^[^<>\x00-\x1f\x7f]{1,50}$")


class StrictRequest(BaseModel):
    # Passwords must never be trimmed or otherwise transformed implicitly.
    model_config = ConfigDict(extra="forbid")


class TextDetectionRequest(StrictRequest):
    text: str = Field(min_length=20, max_length=10_000)

    @field_validator("text", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class TextDetectionResponse(BaseModel):
    classification: Literal["Likely AI-generated", "Likely human-written", "Review recommended"]
    confidence: float = Field(ge=0.0, le=1.0)
    ai_probability: float = Field(ge=0.0, le=1.0)
    human_probability: float = Field(ge=0.0, le=1.0)
    chunks_analyzed: int = Field(ge=1)
    score_is_calibrated: bool
    score_interpretation: str
    model_name: str | None = None
    signals: list[str] = Field(default_factory=list)
    inference_time_ms: float | None = None
    cached: bool = False


class ImageDetectionResponse(BaseModel):
    classification: Literal[
        "Likely AI-generated",
        "Likely authentic/camera-captured",
        "Manipulation suspected",
        "Inconclusive",
    ]
    confidence: int = Field(ge=0, le=100)
    ai_probability: int = Field(ge=0, le=100)
    authentic_probability: int = Field(ge=0, le=100)
    summary: str
    signals: list[str] = Field(max_length=6)
    limitations: str
    model: str


class NewsVerificationRequest(StrictRequest):
    text: str = Field(min_length=5, max_length=10_000)

    @field_validator("text", mode="before")
    @classmethod
    def trim_news_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class NewsDetectedFeatures(BaseModel):
    entities: list[str]
    keywords: list[str]
    event_categories: list[str]
    dates: list[str]
    claim_type: str = "FACT"
    negation_detected: bool = False
    modality: str = "ASSERTED"
    quantities: list[str] = []
    locations: list[str] = []


class NewsEvidenceItem(BaseModel):
    title: str
    publisher: str
    url: str
    domain: str
    published_date: str | None
    image_url: str
    relationship: Literal["SUPPORTS", "CONTRADICTS", "RELATED", "DEBUNKS", "IRRELEVANT"]
    similarity: int = Field(ge=0, le=100)
    evidence_score: int = Field(ge=0, le=100)
    source_tier: int = Field(ge=1, le=4)
    source_type: str = "news"
    reliability: float = Field(default=0.85, ge=0.0, le=1.0)
    explanation: str
    evidence_text: str


class NewsEvidenceGroups(BaseModel):
    supporting: list[NewsEvidenceItem]
    contradicting: list[NewsEvidenceItem]
    related: list[NewsEvidenceItem]
    debunks: list[NewsEvidenceItem]


class ClosestRealStory(BaseModel):
    found: bool
    title: str
    publisher: str
    url: str
    date: str
    similarity: int = Field(ge=0, le=100)
    explanation: str
    image_url: str


class NewsSearchMetadata(BaseModel):
    queries: list[str]
    providers_used: list[str]
    outlet_domains_searched: list[str]
    total_results: int = Field(ge=0)
    articles_scraped: int = Field(ge=0)


class NewsDebugData(BaseModel):
    enabled: bool
    similarity_scores: list[dict[str, object]]
    rule_matches: list[str]


class NewsEvidenceAnalysisItem(BaseModel):
    url: str
    relationship: Literal["SUPPORTS", "CONTRADICTS", "DEBUNKS", "RELATED", "IRRELEVANT"]
    reasoning: str


class NewsVerificationResponse(BaseModel):
    status: Literal["SUCCESS", "SEARCH_UNAVAILABLE"]
    original_text: str
    cleaned_text: str
    search_text: str
    detected: NewsDetectedFeatures
    verdict: Literal[
        "VERIFIED",
        "LIKELY_TRUE",
        "MISLEADING",
        "UNVERIFIED",
        "LIKELY_FALSE",
        "FALSE",
        "SATIRE",
        "OUTDATED",
    ]
    confidence: int = Field(ge=0, le=100)
    explanation: str
    is_satire_or_opinion: bool = False
    context_warnings: list[str]
    evidence: NewsEvidenceGroups
    evidence_analysis: list[NewsEvidenceAnalysisItem] = []
    unresolved_numeric_claims: list[str] = []
    atomic_claims: list[str] = []
    numerical_analysis: dict[str, object] | None = None
    closest_real_story: ClosestRealStory
    search: NewsSearchMetadata
    debug: NewsDebugData
    adjudication_source: Literal["llm", "rules"] = "rules"


class ImageOcrBlock(BaseModel):
    text: str
    type: Literal["headline", "body", "caption", "label", "watermark", "ui_element", "other"]


class ImageOcrResult(BaseModel):
    raw_text: str
    cleaned_text: str
    blocks: list[ImageOcrBlock] = []
    confidence: float | None = None
    provider: Literal["gemini", "paddleocr", "none"] = "gemini"
    fallback_used: bool = False


class ImageVerificationTiming(BaseModel):
    image_processing_ms: float = 0.0
    gemini_ocr_ms: float = 0.0
    cleanup_ms: float = 0.0
    verification_ms: float = 0.0
    total_ms: float = 0.0
    paddleocr_ms: float | None = None


class ImageVerificationMetadata(BaseModel):
    ocr_provider: str
    verification_engine: str = "NewsVerifier"
    timing: ImageVerificationTiming


class ImageVerificationResponse(BaseModel):
    """Unified image verification response.

    Wraps the NewsVerifier result with OCR metadata and timing instrumentation.
    The ``verification`` field contains the full, unmodified NewsVerifier result
    so the same evidence, verdict, and explanation are available regardless of
    whether the input was text or image.
    """

    input_type: Literal["image"] = "image"
    status: Literal["success", "insufficient_text", "ocr_failed", "verification_error"]

    # OCR extraction result
    ocr: ImageOcrResult

    # Full NewsVerifier result (None when status != "success")
    verification: dict[str, Any] | None = None

    # Pipeline metadata and timing
    metadata: ImageVerificationMetadata

    # Top-level convenience fields (derived from verification)
    classification: str
    confidence: int = Field(ge=0, le=100, default=0)
    overall_verdict: str = "UNVERIFIABLE"
    overall_confidence: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    reasoning_summary: str = ""
    user_explanation: str = ""
    recommendation: str = ""

    # Compatibility fields for frontend / existing clients
    summary: str = ""
    claims: list[dict[str, Any]] = []
    extracted: dict[str, Any] = Field(default_factory=lambda: {
        "headline": "",
        "body_text": "",
        "publisher": "",
        "speaker": "",
        "quote": "",
        "date": "",
        "entities": [],
    })
    quote_verification: dict[str, Any] = Field(default_factory=lambda: {
        "is_quote": False,
        "speaker": "",
        "attribution": "UNVERIFIED",
        "context": "UNKNOWN",
    })
    date_analysis: dict[str, Any] = Field(default_factory=lambda: {
        "post_date": "",
        "event_date": "",
        "source_dates": [],
        "consistent": True,
        "notes": "",
    })
    primary_source_found: bool = False
    independent_corroboration_count: int = 0
    credible_contradiction_found: bool = False
    key_context: list[str] = []
    closest_real_story: dict[str, Any] | None = None


# Backward-compatible alias for the image verification response schema
PhilippineImageFactCheckResponse = ImageVerificationResponse


class RegisterRequest(StrictRequest):
    name: str = Field(min_length=1, max_length=50)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(unicodedata.normalize("NFKC", value).split())
        if not NAME_PATTERN.fullmatch(cleaned):
            raise ValueError("Name contains unsupported characters")
        return cleaned

    @model_validator(mode="after")
    def strong_password(self) -> "RegisterRequest":
        errors = password_policy_errors(self.password, email=str(self.email), name=self.name)
        if errors:
            raise ValueError(". ".join(errors))
        return self


class LoginRequest(StrictRequest):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(StrictRequest):
    email: EmailStr


class PasswordResetConfirmRequest(StrictRequest):
    token: str = Field(min_length=40, max_length=256)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        errors = password_policy_errors(value)
        if errors:
            raise ValueError(". ".join(errors))
        return value


class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: Literal["user", "moderator", "admin"]

    model_config = ConfigDict(from_attributes=True)


class AuthResponse(BaseModel):
    user: UserResponse


class MessageResponse(BaseModel):
    message: str


class SessionResponse(BaseModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool


class AdminUserResponse(UserResponse):
    active: bool
