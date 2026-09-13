import re
import unicodedata
from datetime import datetime
from typing import Literal

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


class NewsEvidenceItem(BaseModel):
    title: str
    publisher: str
    url: str
    domain: str
    published_date: str | None
    image_url: str
    relationship: Literal["SUPPORTS", "CONTRADICTS", "RELATED", "DEBUNKS"]
    similarity: int = Field(ge=0, le=100)
    evidence_score: int = Field(ge=0, le=100)
    source_tier: int = Field(ge=1, le=4)
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
    context_warnings: list[str]
    evidence: NewsEvidenceGroups
    closest_real_story: ClosestRealStory
    search: NewsSearchMetadata
    debug: NewsDebugData


class OcrSegmentResponse(BaseModel):
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    bounding_box: list[list[float]]
    engine: Literal["paddleocr"] = "paddleocr"


class OcrConflictResponse(BaseModel):
    status: Literal["OCR_CONFLICT"] = "OCR_CONFLICT"
    candidates: list[str]
    requires_review: bool = True


class OcrCorrectionResponse(BaseModel):
    original: str
    corrected: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]


class ImageOcrResponse(BaseModel):
    primary_engine: Literal["Gemini Vision"] = "Gemini Vision"
    fallback_engine: Literal["PaddleOCR"] = "PaddleOCR"
    gemini_used: bool
    raw_paddle_text: str
    paddle_confidence: float = Field(ge=0.0, le=1.0)
    paddle_segments: list[OcrSegmentResponse]
    gemini_transcription: str
    normalized_text: str
    normalized_values: list[dict[str, object]]
    ocr_quality: Literal["HIGH", "MEDIUM", "LOW"]
    uncertain_sections: list[dict[str, object]]
    ocr_conflicts: list[OcrConflictResponse]
    corrections: list[OcrCorrectionResponse]


class FactCheckEntity(BaseModel):
    type: Literal["PERSON", "ORGANIZATION", "AGENCY", "LOCATION", "MONEY", "DATE", "OTHER"]
    value: str
    normalized_value: str


class FactCheckEvidence(BaseModel):
    source: str
    source_type: Literal["PRIMARY", "MAJOR_NEWS", "SECONDARY", "SOCIAL"]
    url: str
    publication_date: str
    relationship: Literal["SUPPORTS", "CONTRADICTS", "PARTIAL", "UNRELATED"]
    reason: str


class NumericalAnalysisResponse(BaseModel):
    required: bool
    calculation: str
    result: str
    math_status: Literal["CONSISTENT", "INCONSISTENT", "APPROXIMATELY_CONSISTENT", "NOT_APPLICABLE"]
    source_status: Literal["VERIFIED", "ESTIMATE", "UNVERIFIED", "NOT_APPLICABLE"]


class FactCheckClaim(BaseModel):
    claim: str
    verdict: Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "UNVERIFIED"]
    confidence: int = Field(ge=0, le=100)
    evidence: list[FactCheckEvidence]

    # These fields keep useful diagnostics available to the UI without changing
    # the public REAL / QUOTE / FAKE contract.
    claim_id: str
    original_claim: str
    normalized_claim: str
    claim_type: Literal["FACT", "MONEY", "STATISTIC", "QUOTE", "EVENT", "POLICY", "OTHER"]
    ocr_confidence: Literal["HIGH", "MEDIUM", "LOW"]
    search_queries: list[str]
    numerical_analysis: NumericalAnalysisResponse
    context_warnings: list[str]
    explanation: str


class SourceIndependenceResponse(BaseModel):
    unique_primary_sources: int = Field(ge=0)
    unique_secondary_sources: int = Field(ge=0)
    duplicate_evidence_chains_detected: list[str]
    assessment: str


class ImageProvenanceResponse(BaseModel):
    status: Literal["VERIFIED", "PARTIALLY_VERIFIED", "UNKNOWN", "SUSPICIOUS"]
    original_source_found: bool
    notes: str


class ImageExtractedContent(BaseModel):
    headline: str
    body_text: str
    publisher: str
    speaker: str
    quote: str
    date: str
    entities: list[str]


class QuoteVerificationResponse(BaseModel):
    is_quote: bool
    speaker: str
    attribution: Literal["VERIFIED", "FALSE", "UNVERIFIED"]
    context: Literal["ACCURATE", "PARTIAL", "MISLEADING", "ALTERED", "UNKNOWN"]


class ImageDateAnalysisResponse(BaseModel):
    post_date: str
    event_date: str
    source_dates: list[str]
    consistent: bool
    notes: str


class PhilippineImageFactCheckResponse(BaseModel):
    analysis_type: Literal["philippine_news_image_fact_check"]
    classification: Literal["REAL", "QUOTE", "FAKE", "INSUFFICIENT_EVIDENCE"]
    confidence: int = Field(ge=0, le=100)
    content_type: Literal[
        "FACTUAL_NEWS",
        "DIRECT_QUOTE",
        "ATTRIBUTED_QUOTE",
        "PREDICTION",
        "OPINION",
        "ANNOUNCEMENT",
        "SATIRE",
        "OTHER",
    ]
    extracted: ImageExtractedContent
    ocr: ImageOcrResponse
    entities: list[FactCheckEntity]
    claims: list[FactCheckClaim]
    quote_verification: QuoteVerificationResponse
    date_analysis: ImageDateAnalysisResponse
    primary_source_found: bool
    independent_corroboration_count: int = Field(ge=0)
    credible_contradiction_found: bool
    reasoning_summary: str
    user_explanation: str
    source_independence: SourceIndependenceResponse
    image_provenance: ImageProvenanceResponse
    overall_verdict: Literal[
        "SUPPORTED",
        "MOSTLY_SUPPORTED",
        "PARTLY_TRUE",
        "NEEDS_CONTEXT",
        "MISLEADING",
        "MOSTLY_FALSE",
        "FALSE",
        "UNVERIFIABLE",
    ]
    overall_confidence: Literal["HIGH", "MEDIUM", "LOW"]
    summary: str
    key_context: list[str]
    recommendation: str


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
