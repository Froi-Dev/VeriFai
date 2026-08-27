import re
import unicodedata
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.security import password_policy_errors

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
    ]
    confidence: int = Field(ge=0, le=100)
    explanation: str
    evidence: NewsEvidenceGroups
    closest_real_story: ClosestRealStory
    search: NewsSearchMetadata
    debug: NewsDebugData


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
